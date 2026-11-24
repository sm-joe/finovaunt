"""Release security acceptance: login throttling and safe HTTP headers."""
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import json

from scripts import access_control, dashboard_api


def test_admin_login_throttling_and_recovery(tmp_path, monkeypatch):
    monkeypatch.setenv("FINOVAUNT_BOOTSTRAP_PASSWORD", "ci-bootstrap-release-password")
    monkeypatch.setenv("FINOVAUNT_CONTROL_FILE", str(tmp_path / "control-plane.json"))
    access_control.clear_login_failures()
    server = ThreadingHTTPServer(("127.0.0.1", 0), dashboard_api.DashboardHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/api/auth/login"
        def post(password):
            data = json.dumps({"username": "admin", "password": password}).encode()
            request = Request(url, data=data, headers={"Content-Type": "application/json"},
                              method="POST")
            try:
                with urlopen(request, timeout=5) as response:
                    return response.status, response.headers
            except HTTPError as exc:
                return exc.code, exc.headers

        for _ in range(access_control._LOGIN_FAILURE_LIMIT):
            assert post("incorrect-password")[0] == 401
        status, headers = post("ci-bootstrap-release-password")
        assert status == 429
        assert headers["Cache-Control"] == "no-store"
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert headers["Referrer-Policy"] == "no-referrer"

        # Time window expiry permits a new verified login.
        access_control._LOGIN_FAILURES[:] = [
            t - access_control._LOGIN_WINDOW_SECONDS - 1
            for t in access_control._LOGIN_FAILURES
        ]
        assert post("ci-bootstrap-release-password")[0] == 200
        assert not access_control.login_blocked()
    finally:
        access_control.clear_login_failures()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_invalid_origin_and_cross_site_attempts_still_fail(tmp_path, monkeypatch):
    monkeypatch.setenv("FINOVAUNT_BOOTSTRAP_PASSWORD", "ci-bootstrap-release-password")
    monkeypatch.setenv("FINOVAUNT_CONTROL_FILE", str(tmp_path / "control-plane.json"))
    server = ThreadingHTTPServer(("127.0.0.1", 0), dashboard_api.DashboardHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/api/auth/login"
        data = json.dumps({"username": "admin", "password": "ci-bootstrap-release-password"}).encode()
        for headers in (
            {"Content-Type": "application/json", "Origin": "https://untrusted.example"},
            {"Content-Type": "application/json", "Sec-Fetch-Site": "cross-site"},
        ):
            req = Request(url, method="POST", data=data, headers=headers)
            try:
                urlopen(req, timeout=5)
                raise AssertionError("Cross-origin sign-in must be rejected.")
            except HTTPError as exc:
                assert exc.code == 403
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
