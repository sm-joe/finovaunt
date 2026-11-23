from __future__ import annotations

import json
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import scripts.dashboard_api as dashboard_api


def test_health_endpoint_and_read_only_rejection() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), dashboard_api.DashboardHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(f"{base}/api/health", timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
            assert response.status == 200
            assert payload["read_only"] is True

        request = Request(f"{base}/api/overview", data=b"{}", method="POST")
        try:
            urlopen(request, timeout=2)
            raise AssertionError("POST should be rejected by the read-only API")
        except Exception as exc:
            assert getattr(exc, "code", None) == 405
            payload = json.loads(exc.read().decode("utf-8"))
            assert payload["error"] == "method_not_allowed"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_scan_data_requires_login_and_cross_origin_mutations_are_blocked(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FINOVAUNT_BOOTSTRAP_PASSWORD", "initial-test-password-2026")
    monkeypatch.setenv("FINOVAUNT_CONTROL_FILE", str(tmp_path / "control-plane.json"))
    server = ThreadingHTTPServer(("127.0.0.1", 0), dashboard_api.DashboardHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        for path in ("/api/overview", "/api/assets", "/api/opportunities", "/api/scans", "/api/scans/latest", "/api/sync-status"):
            try:
                urlopen(f"{base}{path}", timeout=2)
                raise AssertionError(f"{path} leaked without authentication")
            except HTTPError as exc:
                assert exc.code == 401, path

        request = Request(
            f"{base}/api/auth/login",
            data=json.dumps({"username": "admin", "password": "initial-test-password-2026"}).encode(),
            headers={"Content-Type": "application/json", "Origin": "https://evil.example"},
            method="POST",
        )
        try:
            urlopen(request, timeout=2)
            raise AssertionError("Cross-origin login should be rejected")
        except HTTPError as exc:
            assert exc.code == 403
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_cloud_account_delete_requires_authentication(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FINOVAUNT_BOOTSTRAP_PASSWORD", "initial-test-password-2026")
    monkeypatch.setenv("FINOVAUNT_CONTROL_FILE", str(tmp_path / "control-plane.json"))
    server = ThreadingHTTPServer(("127.0.0.1", 0), dashboard_api.DashboardHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        request = Request(
            f"{base}/api/cloud-accounts/123456789012",
            method="DELETE",
        )
        try:
            urlopen(request, timeout=2)
            raise AssertionError("Account removal must require authentication.")
        except HTTPError as exc:
            assert exc.code == 401
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
