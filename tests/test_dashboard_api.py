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


def test_recommendation_decisions_are_not_public(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FINOVAUNT_BOOTSTRAP_PASSWORD", "initial-test-password-2026")
    monkeypatch.setenv("FINOVAUNT_CONTROL_FILE", str(tmp_path / "control-plane.json"))
    server = ThreadingHTTPServer(("127.0.0.1", 0), dashboard_api.DashboardHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            urlopen(f"{base}/api/recommendation-decisions", timeout=2)
            raise AssertionError("Review decisions must be private")
        except HTTPError as exc:
            assert exc.code == 401
        request = Request(
            f"{base}/api/recommendation-decisions",
            method="POST",
            data=json.dumps({
                "run_id": "old-run", "resource_id": "i-test",
                "decision": "approved", "note": "Test note for human approval",
            }).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            urlopen(request, timeout=2)
            raise AssertionError("Anonymous reviews must not be accepted")
        except HTTPError as exc:
            assert exc.code == 401
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_browser_cookie_session_survives_first_login_password_rotation(tmp_path, monkeypatch) -> None:
    """A successful login must retain its cookie and rotation must replace it."""
    from http.cookiejar import CookieJar
    from urllib.request import build_opener, HTTPCookieProcessor

    monkeypatch.setenv("FINOVAUNT_BOOTSTRAP_PASSWORD", "initial-test-password-2026")
    monkeypatch.setenv("FINOVAUNT_CONTROL_FILE", str(tmp_path / "control-plane.json"))
    monkeypatch.delenv("FINOVAUNT_SECURE_COOKIES", raising=False)
    server = ThreadingHTTPServer(("127.0.0.1", 0), dashboard_api.DashboardHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    jar = CookieJar()
    browser = build_opener(HTTPCookieProcessor(jar))

    def get_session():
        with browser.open(f"{base}/api/auth/session", timeout=3) as response:
            return json.loads(response.read())

    def post(path, payload):
        request = Request(
            f"{base}{path}",
            method="POST",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        with browser.open(request, timeout=3) as response:
            return json.loads(response.read()), response.headers.get("Set-Cookie", "")

    try:
        assert get_session()["authenticated"] is False
        login, first_cookie = post("/api/auth/login", {
            "username": "admin", "password": "initial-test-password-2026",
        })
        assert login["authenticated"] is True
        assert login["must_change_password"] is True
        assert "finovaunt_session=" in first_cookie
        assert "HttpOnly" in first_cookie
        assert len(list(jar)) == 1, f"Browser rejected cookie: {first_cookie!r}"
        assert list(jar)[0].value in dashboard_api.access_control._SESSIONS
        probe = Request(f"{base}/api/auth/session")
        jar.add_cookie_header(probe)
        assert "finovaunt_session=" in (probe.get_header("Cookie") or ""), f"Cookie path mismatch: {list(jar)[0].path!r}"
        assert dashboard_api.access_control.session(list(jar)[0].value) is not None
        assert get_session()["authenticated"] is True

        changed, rotated_cookie = post("/api/auth/password", {
            "current_password": "initial-test-password-2026",
            "new_password": "replacement-test-password-2026",
        })
        assert changed["status"] == "password_changed"
        assert changed["authenticated"] is True
        assert "finovaunt_session=" in rotated_cookie
        assert first_cookie != rotated_cookie
        active = get_session()
        assert active["authenticated"] is True
        assert active["must_change_password"] is False
        assert active["username"] == "admin"

        # The old token is invalid after rotation even though the fresh one works.
        old_token = first_cookie.split("finovaunt_session=", 1)[1].split(";", 1)[0]
        request = Request(f"{base}/api/auth/session", headers={"Cookie": f"finovaunt_session={old_token}"})
        with urlopen(request, timeout=3) as response:
            assert json.loads(response.read())["authenticated"] is False
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_live_dashboard_never_depends_on_scan_artifact_or_invents_spend(tmp_path, monkeypatch) -> None:
    """A real onboarded account with no collected AWS evidence has null spend."""
    from http.cookiejar import CookieJar
    from urllib.request import build_opener, HTTPCookieProcessor
    from scripts import access_control
    monkeypatch.setenv("FINOVAUNT_BOOTSTRAP_PASSWORD", "initial-test-password-2026")
    monkeypatch.setenv("FINOVAUNT_CONTROL_FILE", str(tmp_path / "control-plane.json"))
    monkeypatch.delenv("FINOVAUNT_SECURE_COOKIES", raising=False)
    monkeypatch.setenv("FINOPS_OUTPUT_DIR", "nonexistent-evidence-path")

    account = access_control.add_account(
        "Test AWS account", "aws", "123456789012",
        "arn:aws:iam::123456789012:role/FinovauntReadOnly", "ap-south-1"
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), dashboard_api.DashboardHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    browser = build_opener(HTTPCookieProcessor(CookieJar()))
    try:
        with __import__("pytest").raises(HTTPError) as unauthorized:
            browser.open(f"{base}/api/live-dashboard?account_id=123456789012", timeout=3)
        assert unauthorized.value.code == 401

        login = Request(
            f"{base}/api/auth/login", method="POST",
            data=json.dumps({"username":"admin","password":"initial-test-password-2026"}).encode(),
            headers={"Content-Type":"application/json"},
        )
        with browser.open(login, timeout=3) as response:
            assert json.loads(response.read())["authenticated"] is True

        # Fresh installs must rotate the bootstrap secret before viewing billing.
        rotate = Request(
            f"{base}/api/auth/password", method="POST",
            data=json.dumps({
                "current_password": "initial-test-password-2026",
                "new_password": "rotated-test-password-2026",
            }).encode(),
            headers={"Content-Type":"application/json"},
        )
        with browser.open(rotate, timeout=3) as response:
            assert json.loads(response.read())["authenticated"] is True

        with browser.open(f"{base}/api/live-dashboard?account_id=123456789012", timeout=3) as response:
            payload = json.loads(response.read())
        assert payload["source"] == "aws_collected"
        assert payload["account"]["id"] == account["id"]
        assert payload["billing"] is None
        assert payload["inventory"] is None
        assert payload["estimated_savings"] is None
        assert payload["realized_savings"] is None
        assert payload["review_candidates"] == []
        assert payload["billing_status"] == "not_collected"

        # Saving genuine collectors' responses is the only path to dashboard values.
        access_control.save_billing_scan("123456789012", {
            "scanned_at": "2026-11-23T10:00:00+00:00", "status": "success",
            "period_start": "2026-11-01", "period_end_exclusive": "2026-11-24",
            "total_cost": 17.25, "total_cost_exact": "17.25", "currency": "USD",
            "services": [{"service":"Amazon EC2", "amount":17.25, "currency":"USD"}],
            "is_final": False,
        })
        with browser.open(f"{base}/api/live-dashboard?account_id=123456789012", timeout=3) as response:
            payload = json.loads(response.read())
        assert payload["billing"]["total_cost"] == 17.25
        assert payload["inventory"] is None
        assert payload["estimated_savings"] is None
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_json_disconnected_client_is_not_reported_as_aws_scan_failure():
    """An already disconnected frontend cannot accept a second HTTP error."""
    from io import BytesIO
    from unittest.mock import Mock

    handler = object.__new__(dashboard_api.DashboardHandler)
    handler.headers = {}
    handler.send_response = Mock()
    handler.send_header = Mock()
    handler.end_headers = Mock()
    handler.wfile = Mock()
    handler.wfile.write.side_effect = BrokenPipeError(32, "Broken pipe")
    handler.close_connection = False

    # The inventory collector may already have persisted its results when
    # nginx times out. Serializing the response must not raise.
    handler._json(200, {"status": "success", "asset_count": 8})
    assert handler.close_connection is True
    assert handler.send_response.call_count == 1
    handler.wfile.write.assert_called_once()


def test_json_connection_reset_is_handled_without_retrying_response():
    from unittest.mock import Mock
    handler = object.__new__(dashboard_api.DashboardHandler)
    handler.headers = {}
    handler.send_response = Mock()
    handler.send_header = Mock()
    handler.end_headers = Mock(side_effect=ConnectionResetError(104, "Peer reset"))
    handler.wfile = Mock()
    handler.close_connection = False
    handler._json(200, {"status": "success"})
    assert handler.close_connection is True
    assert handler.send_response.call_count == 1
