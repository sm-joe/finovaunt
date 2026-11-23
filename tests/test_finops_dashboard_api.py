"""FinOps HTTP integration: auth, partial evidence, persistence and revision isolation."""
import json
from http.cookiejar import CookieJar
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

import pytest

from scripts import access_control, dashboard_api
from src.tools import finops_core


ACCOUNT = "123456789012"


def test_finops_endpoint_is_authenticated_and_revision_scoped(tmp_path, monkeypatch):
    monkeypatch.setenv("FINOVAUNT_BOOTSTRAP_PASSWORD", "ci-finops-bootstrap-password")
    monkeypatch.setenv("FINOVAUNT_CONTROL_FILE", str(tmp_path / "control-plane.json"))
    access_control.add_account("AWS", "aws", ACCOUNT,
        "arn:aws:iam::123456789012:role/FinovauntReadOnly", "us-east-1")
    calls = []
    def fake_assessment(account, *, external_id=""):
        calls.append({"account_id": account["account_id"], "external_id": external_id})
        return {"account_id": account["account_id"], "region": account["region"],
                "scanned_at": "2026-11-23T10:00:00+00:00",
                "status": "partial", "read_only": True,
                "automated_actions_performed": 0,
                "sections": {"cost_allocation": {"status": "not_assessed"},
                             "s3": {"status": "collected", "evidence": {
                                 "buckets": [], "source": "s3_inventory_cloudwatch"}}}}
    monkeypatch.setattr(finops_core, "assess_aws_finops", fake_assessment)
    server = ThreadingHTTPServer(("127.0.0.1", 0), dashboard_api.DashboardHandler)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    client = build_opener(HTTPCookieProcessor(CookieJar()))
    base = f"http://127.0.0.1:{server.server_port}"

    def request(path, body=None):
        req = Request(base + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json"} if body is not None else {},
            method="POST" if body is not None else "GET")
        with client.open(req, timeout=5) as response:
            return json.load(response)

    try:
        with pytest.raises(HTTPError) as unauthorized:
            request(f"/api/finops-assessments?account_id={ACCOUNT}")
        assert unauthorized.value.code == 401
        with pytest.raises(HTTPError) as unauthorized:
            request("/api/finops-assessments", {"account_id": ACCOUNT})
        assert unauthorized.value.code == 401
        assert calls == []
        assert request("/api/auth/login", {
            "username": "admin", "password": "ci-finops-bootstrap-password"})["authenticated"]
        with pytest.raises(HTTPError) as locked:
            request("/api/finops-assessments", {"account_id": ACCOUNT})
        assert locked.value.code == 403
        request("/api/auth/password", {
            "current_password": "ci-finops-bootstrap-password",
            "new_password": "ci-finops-new-password-2026"})
        evidence = request("/api/finops-assessments", {"account_id": ACCOUNT})
        assert evidence["status"] == "partial"
        assert evidence["config_revision"] == 1
        assert evidence["automated_actions_performed"] == 0
        assert len(calls) == 1
        assert request(f"/api/finops-assessments?account_id={ACCOUNT}")["latest"]["id"] == evidence["id"]

        access_control.update_account_configuration(
            account_id=ACCOUNT, name="AWS", role_arn="arn:aws:iam::123456789012:role/NewReadOnly",
            region="us-east-1", reviewed_by="admin",
            note="Switch to a different authorized role for new scan.")
        assert request(f"/api/finops-assessments?account_id={ACCOUNT}")["latest"] is None
        assert len(access_control._read()["finops_assessments"]) == 1
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)
