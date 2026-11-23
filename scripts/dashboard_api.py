"""Read-only HTTP API for the Finovaunt dashboard (Python standard library only)."""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import sys
import threading
import time
from typing import Any
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.scan_artifact_sync import SyncError, sync_latest_scan  # noqa: E402
from scripts import access_control  # noqa: E402
from src.utils.dashboard_data import (  # noqa: E402
    DashboardDataError,
    build_assets,
    build_opportunities,
    build_overview,
    build_scan_detail,
    build_scans,
    load_artifacts,
)

_SYNC_LOCK = threading.Lock()
_SYNC_STATUS: dict[str, Any] = {
    "enabled": False,
    "status": "disabled",
    "message": "Configure FINOVAUNT_GITHUB_TOKEN or GH_TOKEN to sync GitHub scan artifacts automatically.",
    "last_checked_at": None,
    "last_success_at": None,
    "github_run_id": None,
    "scan_run_id": None,
}

_ALLOWED_ORIGINS = {
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
}


def _artifact_dir() -> Path:
    name = os.getenv("FINOPS_OUTPUT_DIR", "artifacts-live").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
        raise DashboardDataError("FINOPS_OUTPUT_DIR must be a single directory name.")
    directory = (ROOT / name).resolve()
    if directory.parent != ROOT:
        raise DashboardDataError("Artifact directory must be directly under the repository root.")
    return directory


class DashboardHandler(BaseHTTPRequestHandler):
    server_version = "FinovauntDashboardAPI/1.0"

    def _json(self, status: int, payload: Any) -> None:
        encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        origin = self.headers.get("Origin")
        if origin in _ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.end_headers()
        self.wfile.write(encoded)

    def do_OPTIONS(self) -> None:
        origin = self.headers.get("Origin")
        self.send_response(204)
        if origin in _ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Credentials", "true")
        self.end_headers()

    def do_POST(self) -> None:
        route = urlparse(self.path).path.rstrip("/") or "/"
        if route not in ("/api/auth/login", "/api/auth/logout", "/api/auth/password", "/api/cloud-accounts", "/api/billing-scans", "/api/inventory-scans", "/api/recommendation-decisions"):
            self._json(405, {"error": "method_not_allowed", "message": "This API endpoint does not accept POST requests."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 65536: self._json(413, {"error":"payload_too_large","message":"Request body is too large."}); return
            body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
            if not isinstance(body, dict): raise ValueError("Request body must be a JSON object.")
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            self._json(400, {"error":"invalid_json","message":"Provide a valid JSON object."}); return
        # Cookie-authenticated mutations must not be accepted cross-origin.
        # Non-browser clients without an Origin still need an authenticated session.
        origin = self.headers.get("Origin")
        if origin and origin not in _ALLOWED_ORIGINS:
            self._json(403, {"error": "invalid_origin", "message": "Untrusted request origin."})
            return
        site = self.headers.get("Sec-Fetch-Site", "").lower()
        if site in {"cross-site", "same-site"} and not origin:
            self._json(403, {"error": "invalid_origin", "message": "Cross-origin changes are blocked."})
            return
        if route == "/api/auth/login":
            result = access_control.login(str(body.get("username", "")), str(body.get("password", "")))
            if not result: self._json(401, {"error":"invalid_credentials","message":"Username or password is incorrect."}); return
            self._auth_json(200, {"authenticated": True, **{k:v for k,v in result.items() if k != "token"}}, token=result["token"])
            return
        token = self._cookie_token()
        current = access_control.session(token)
        if route == "/api/auth/logout":
            access_control.logout(token); self._auth_json(200, {"status":"logged_out"}, clear=True); return
        if route == "/api/auth/password":
            if not current: self._json(401, {"error":"unauthorized","message":"Please log in."}); return
            if not access_control.change_password(token, str(body.get("current_password", "")), str(body.get("new_password", ""))):
                self._json(400, {"error":"password_change_rejected","message":"Current password is incorrect or the new password does not meet the 12-character minimum."}); return
            # Password changes invalidate every previous session. Immediately
            # authenticate with the new secret and issue a fresh HttpOnly
            # session cookie, so first-login rotation enters the dashboard
            # rather than silently returning the user to the sign-in page.
            refreshed = access_control.login(str(current["username"]), str(body.get("new_password", "")))
            if not refreshed:
                self._json(500, {"error": "session_refresh_failed", "message": "Password updated. Please sign in again."})
                return
            self._auth_json(
                200,
                {"status": "password_changed", "authenticated": True, "username": refreshed["username"], "must_change_password": False},
                token=refreshed["token"],
            )
            return
        if not current:
            self._json(401, {"error":"unauthorized","message":"Please log in."}); return
        if current.get("must_change_password"):
            self._json(403, {"error":"password_change_required","message":"Change the default password before continuing."}); return
        if route == "/api/cloud-accounts":
            try:
                item = access_control.add_account(str(body.get("name", "")), str(body.get("provider", "aws")), str(body.get("account_id", "")), str(body.get("role_arn", "")), str(body.get("region", "us-east-1")), str(body.get("external_id", "")))
                self._json(201, item)
            except ValueError as exc: self._json(400, {"error":"invalid_account","message":str(exc)})
            return
        if route == "/api/billing-scans":
            account_id = str(body.get("account_id", ""))
            account = access_control.get_account(account_id)
            if not account:
                self._json(404, {"error": "account_not_found", "message": "Onboard the AWS account first."})
                return
            try:
                from src.tools.billing_service import collect_billing
                evidence = collect_billing(account, external_id=str(body.get("external_id", "")))
                result = access_control.save_billing_scan(account_id, evidence)
                self._json(200, result)
            except Exception as exc:
                # Never expose role credentials, SDK exception messages, or account secrets.
                self._json(502, {
                    "error": "billing_scan_failed",
                    "message": f"AWS billing scan failed ({type(exc).__name__}). Check role trust and Cost Explorer read permissions.",
                })
            return
        if route == "/api/inventory-scans":
            account_id = str(body.get("account_id", ""))
            account = access_control.get_account(account_id)
            if not account:
                self._json(404, {"error": "account_not_found", "message": "Onboard the AWS account first."})
                return
            try:
                from src.tools.inventory_service import collect_inventory
                inventory = collect_inventory(account, external_id=str(body.get("external_id", "")))
                result = access_control.save_inventory_scan(account_id, inventory)
                self._json(200, result)
            except Exception as exc:
                self._json(502, {
                    "error": "inventory_scan_failed",
                    "message": f"AWS inventory scan failed ({type(exc).__name__}). Verify IAM read permissions and role trust.",
                })
            return
        if route == "/api/recommendation-decisions":
            run_id = str(body.get("run_id", "")).strip()
            resource_id = str(body.get("resource_id", "")).strip()
            decision = str(body.get("decision", "")).strip()
            note = str(body.get("note", "")).strip()
            try:
                evidence = load_artifacts(_artifact_dir())
                current_run = str(evidence.get("evidence", {}).get("run_id") or "")
                available = {
                    item["resource_id"]
                    for item in build_opportunities(evidence).get("items", [])
                }
            except DashboardDataError:
                self._json(503, {"error": "scan_unavailable", "message": "No current scan evidence is available."})
                return
            if not run_id or current_run != run_id:
                self._json(409, {"error": "stale_scan", "message": "Refresh the dashboard before reviewing recommendations."})
                return
            if resource_id not in available:
                self._json(404, {"error": "recommendation_not_found", "message": "Recommendation is not present in this scan."})
                return
            try:
                result = access_control.record_recommendation_decision(
                    run_id=run_id,
                    resource_id=resource_id,
                    action=decision,
                    note=note,
                    reviewed_by=str(current["username"]),
                )
            except ValueError as exc:
                self._json(400, {"error": "invalid_decision", "message": str(exc)})
                return
            self._json(201, result)
            return
        self._json(405, {"error":"method_not_allowed","message":"This API endpoint does not accept POST requests."})

    def _cookie_token(self) -> str | None:
        for part in self.headers.get("Cookie", "").split(";"):
            key, _, value = part.strip().partition("=")
            if key == "finovaunt_session": return value
        return None

    def _auth_json(self, status: int, payload: Any, token: str | None = None, clear: bool = False) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status); self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded))); self.send_header("Cache-Control", "no-store")
        self.send_header("Set-Cookie", f"finovaunt_session={'' if clear else token or ''}; HttpOnly; SameSite=Strict; Path=/${'; Secure' if os.getenv('FINOVAUNT_SECURE_COOKIES', 'false').lower() == 'true' else ''}; Max-Age={0 if clear else 43200}")
        self.end_headers(); self.wfile.write(encoded)

    def do_PUT(self) -> None:
        self._json(405, {"error": "method_not_allowed", "message": "This API is read-only."})

    def do_DELETE(self) -> None:
        route = urlparse(self.path).path.rstrip("/")
        if not route.startswith("/api/cloud-accounts/"):
            self._json(405, {"error": "method_not_allowed", "message": "Delete is not supported for this resource."})
            return
        origin = self.headers.get("Origin")
        if origin and origin not in _ALLOWED_ORIGINS:
            self._json(403, {"error": "invalid_origin", "message": "Untrusted request origin."})
            return
        if self.headers.get("Sec-Fetch-Site", "").lower() in {"cross-site", "same-site"} and not origin:
            self._json(403, {"error": "invalid_origin", "message": "Cross-origin changes are blocked."})
            return
        current = access_control.session(self._cookie_token())
        if not current:
            self._json(401, {"error": "unauthorized", "message": "Please log in."})
            return
        if current.get("must_change_password"):
            self._json(403, {"error": "password_change_required", "message": "Change your password first."})
            return
        account_id = route.removeprefix("/api/cloud-accounts/")
        if not re.fullmatch(r"[0-9]{12}", account_id):
            self._json(404, {"error": "not_found", "message": "Cloud account not found."})
            return
        if not access_control.delete_account(account_id):
            self._json(404, {"error": "not_found", "message": "Cloud account not found."})
            return
        self._json(200, {"status": "deleted", "account_id": account_id})

    def do_GET(self) -> None:
        route = urlparse(self.path).path.rstrip("/") or "/"
        if route == "/api/health":
            self._json(200, {"status": "ok", "service": "finovaunt-dashboard-api", "read_only": True})
            return
        if route == "/api/auth/session":
            current = access_control.session(self._cookie_token())
            self._json(200, {"authenticated": bool(current), **(current or {})})
            return
        if route == "/api/auth/verify":
            current = access_control.session(self._cookie_token())
            if not current or current.get("must_change_password"):
                self._json(401, {"error": "unauthorized", "message": "Login and password change required."})
            else:
                self._json(200, {"authorized": True})
            return
        if route == "/api/cloud-accounts":
            current = access_control.session(self._cookie_token())
            if not current: self._json(401, {"error":"unauthorized","message":"Please log in."}); return
            if current.get("must_change_password"): self._json(403, {"error":"password_change_required","message":"Change the default password before continuing."}); return
            self._json(200, {"items":access_control.list_accounts()}); return
        if route == "/api/recommendation-decisions":
            current = access_control.session(self._cookie_token())
            if not current or current.get("must_change_password"):
                self._json(401, {"error": "unauthorized", "message": "Please sign in."})
                return
            requested_run = parse_qs(urlparse(self.path).query).get("run_id", [""])[0]
            self._json(200, {"items": access_control.recommendation_decisions(requested_run or None)})
            return
        if route.startswith("/api/inventory-scans/"):
            current = access_control.session(self._cookie_token())
            if not current:
                self._json(401, {"error": "unauthorized", "message": "Please log in."})
                return
            if current.get("must_change_password"):
                self._json(403, {"error": "password_change_required", "message": "Change your password first."})
                return
            account_id = route.removeprefix("/api/inventory-scans/")
            if not re.fullmatch(r"[0-9]{12}", account_id):
                self._json(404, {"error": "not_found", "message": "Cloud account not found."})
                return
            self._json(200, {"latest": access_control.latest_inventory_scan(account_id)})
            return
        if route.startswith("/api/billing-scans/"):
            current = access_control.session(self._cookie_token())
            if not current: self._json(401, {"error":"unauthorized","message":"Please log in."}); return
            if current.get("must_change_password"): self._json(403, {"error":"password_change_required","message":"Change the default password before continuing."}); return
            account_id = route.removeprefix("/api/billing-scans/")
            self._json(200, {"items":access_control.billing_history(account_id)}); return
        # Scan artifacts contain cloud inventory and billing metadata. Never serve
        # them to an unauthenticated browser, even though AWS access is read-only.
        current = access_control.session(self._cookie_token())
        if not current:
            self._json(401, {"error": "unauthorized", "message": "Please log in."})
            return
        if current.get("must_change_password"):
            self._json(403, {"error": "password_change_required", "message": "Change your password before continuing."})
            return
        if route == "/api/sync-status":
            with _SYNC_LOCK:
                self._json(200, dict(_SYNC_STATUS))
            return
        try:
            artifacts = load_artifacts(_artifact_dir())
            if route == "/api/overview":
                payload = build_overview(artifacts)
            elif route == "/api/opportunities":
                payload = build_opportunities(artifacts)
            elif route == "/api/assets":
                payload = build_assets(artifacts)
            elif route == "/api/scans":
                payload = build_scans(artifacts)
            elif route == "/api/scans/latest":
                scans = build_scans(artifacts)["items"]
                payload = scans[-1] if scans else None
                if payload is None:
                    self._json(404, {"error": "not_found", "message": "No scan history is available."})
                    return
            elif route.startswith("/api/scans/"):
                run_id = route.removeprefix("/api/scans/")
                if not run_id or "/" in run_id:
                    self._json(404, {"error": "not_found", "message": "Scan not found."})
                    return
                payload = build_scan_detail(artifacts, run_id)
                if payload is None:
                    self._json(404, {"error": "not_found", "message": "Scan not found."})
                    return
            else:
                self._json(404, {"error": "not_found", "message": "Unknown API endpoint."})
                return
            self._json(200, payload)
        except DashboardDataError as exc:
            self._json(503, {"error": "dashboard_data_unavailable", "message": str(exc)})

    def log_message(self, format: str, *args: Any) -> None:
        # Keep request logs concise; no billing/resource payloads are logged.
        sys.stderr.write("Finovaunt API: " + (format % args) + "\n")


def _sync_worker() -> None:
    token = os.getenv("FINOVAUNT_GITHUB_TOKEN") or os.getenv("GH_TOKEN") or ""
    repository = os.getenv("FINOVAUNT_GITHUB_REPOSITORY", "sm-joe/finovaunt")
    workflow = os.getenv("FINOVAUNT_SCAN_WORKFLOW", "finovaunt-scan.yml")
    output_dir = _artifact_dir()
    interval = max(30, int(os.getenv("FINOVAUNT_SYNC_INTERVAL_SECONDS", "60")))
    with _SYNC_LOCK:
        _SYNC_STATUS.update({"enabled": True, "status": "starting", "message": "Waiting for the first GitHub artifact sync."})
    while True:
        try:
            result = sync_latest_scan(output_dir, token=token, repository=repository, workflow=workflow)
            now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            with _SYNC_LOCK:
                _SYNC_STATUS.update({
                    "enabled": True,
                    "status": result.get("status", "ok"),
                    "message": "Latest successful read-only scan artifact is available." if result.get("status") == "synced" else "Dashboard artifacts are already up to date.",
                    "last_checked_at": now,
                    "last_success_at": result.get("synced_at") or _SYNC_STATUS.get("last_success_at"),
                    "github_run_id": result.get("github_run_id"),
                    "scan_run_id": result.get("scan_run_id"),
                    "github_run_url": result.get("github_run_url"),
                    "error": None,
                })
        except Exception as exc:
            with _SYNC_LOCK:
                _SYNC_STATUS.update({
                    "enabled": True,
                    "status": "error",
                    "message": str(exc),
                    "last_checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "error": str(exc),
                })
            print(f"Finovaunt artifact sync warning: {exc}", file=sys.stderr)
        time.sleep(interval)


def main() -> int:
    host = os.getenv("FINOVAUNT_API_HOST", "127.0.0.1")
    try:
        port = int(os.getenv("FINOVAUNT_API_PORT", "8787"))
    except ValueError:
        print("ERROR: FINOVAUNT_API_PORT must be an integer.", file=sys.stderr)
        return 2
    if not 1 <= port <= 65535:
        print("ERROR: FINOVAUNT_API_PORT must be between 1 and 65535.", file=sys.stderr)
        return 2
    token = os.getenv("FINOVAUNT_GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    if token:
        with _SYNC_LOCK:
            _SYNC_STATUS.update({"enabled": True, "status": "starting", "message": "Automatic GitHub artifact sync is starting."})
        threading.Thread(target=_sync_worker, name="finovaunt-artifact-sync", daemon=True).start()
    else:
        print("Automatic artifact sync disabled: set FINOVAUNT_GITHUB_TOKEN or GH_TOKEN.", file=sys.stderr)
    server = ThreadingHTTPServer((host, port), DashboardHandler)
    print(f"Finovaunt read-only dashboard API listening on http://{host}:{port}")
    print(f"Artifact directory: {_artifact_dir()}")
    print("Endpoints: /api/health /api/sync-status /api/overview /api/opportunities /api/assets /api/scans")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Finovaunt dashboard API.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
