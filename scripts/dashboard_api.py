"""Read-only HTTP API for the Finovaunt dashboard (Python standard library only)."""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import sys
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.utils.dashboard_data import (  # noqa: E402
    DashboardDataError,
    build_assets,
    build_opportunities,
    build_overview,
    build_scan_detail,
    build_scans,
    load_artifacts,
)

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
            self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self) -> None:
        self._json(405, {"error": "method_not_allowed", "message": "This API is read-only."})

    def do_PUT(self) -> None:
        self._json(405, {"error": "method_not_allowed", "message": "This API is read-only."})

    def do_DELETE(self) -> None:
        self._json(405, {"error": "method_not_allowed", "message": "This API is read-only."})

    def do_GET(self) -> None:
        route = urlparse(self.path).path.rstrip("/") or "/"
        if route == "/api/health":
            self._json(200, {"status": "ok", "service": "finovaunt-dashboard-api", "read_only": True})
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
    server = ThreadingHTTPServer((host, port), DashboardHandler)
    print(f"Finovaunt read-only dashboard API listening on http://{host}:{port}")
    print(f"Artifact directory: {_artifact_dir()}")
    print("Endpoints: /api/health /api/overview /api/opportunities /api/assets /api/scans")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Finovaunt dashboard API.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
