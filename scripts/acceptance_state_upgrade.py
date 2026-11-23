"""Integration-only Docker Compose upgrade acceptance; no AWS access required.

Invoked by CI before and after a container recreation to prove that
credential rotation, AWS account configuration and local audit evidence persist.
"""
from __future__ import annotations

import argparse
from http.cookiejar import CookieJar
import json
import time
from urllib.error import URLError
from urllib.request import build_opener, HTTPCookieProcessor, Request


BASE = "http://127.0.0.1:8787"
INITIAL = "ci-runtime-bootstrap-pass-2026"
ROTATED = "ci-runtime-rotated-credential-2026"
ACCOUNT = "123456789012"
ROLE = "arn:aws:iam::123456789012:role/FinovauntCollectorTest"


class Client:
    def __init__(self):
        self.http = build_opener(HTTPCookieProcessor(CookieJar()))

    def request(self, endpoint: str, payload: dict | None = None) -> dict:
        request = Request(BASE + endpoint, headers={"Accept": "application/json", **(
            {"Content-Type": "application/json"} if payload is not None else {})},
            data=json.dumps(payload).encode("utf-8") if payload is not None else None,
            method="POST" if payload is not None else "GET")
        with self.http.open(request, timeout=10) as response:
            assert response.status in (200, 201), (endpoint, response.status)
            return json.load(response)

    def login(self, password: str) -> None:
        result = self.request("/api/auth/login", {
            "username": "admin", "password": password
        })
        assert result["authenticated"]


def ready() -> None:
    for attempt in range(60):
        try:
            with build_opener().open(BASE + "/api/health", timeout=3) as response:
                if json.load(response).get("status") == "ok":
                    return
        except (URLError, TimeoutError, ConnectionError):
            pass
        time.sleep(2)
    raise RuntimeError("Finovaunt API did not become healthy")


def prepare() -> None:
    ready()
    client = Client()
    client.login(INITIAL)
    changed = client.request("/api/auth/password", {
        "current_password": INITIAL, "new_password": ROTATED,
    })
    assert changed["authenticated"]
    created = client.request("/api/cloud-accounts", {
        "name": "Test Account", "provider": "aws", "account_id": ACCOUNT,
        "role_arn": ROLE, "region": "us-east-1",
    })
    assert created["config_revision"] == 1
    updated = client.request(f"/api/cloud-accounts/{ACCOUNT}/configuration", {
        "name": "Updated Account", "role_arn": ROLE,
        "region": "eu-west-1", "reason": "Verify safe configuration changes survive upgrades.",
    })
    assert updated["config_revision"] == 2
    assert updated["region"] == "eu-west-1"


def verify() -> None:
    ready()
    client = Client()
    client.login(ROTATED)
    accounts = client.request("/api/cloud-accounts")["items"]
    assert len(accounts) == 1, accounts
    assert accounts[0]["region"] == "eu-west-1"
    assert accounts[0]["name"] == "Updated Account"
    assert accounts[0]["config_revision"] == 2
    dashboard = client.request(f"/api/live-dashboard?account_id={ACCOUNT}")
    assert len(dashboard["account_config_audit"]) == 1
    assert dashboard["billing"] is None
    assert dashboard["inventory"] is None
    assert dashboard["realized_savings"] is None


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["prepare", "verify"])
    argument = parser.parse_args()
    if argument.phase == "prepare":
        prepare()
    else:
        verify()
    print(f"PASS: {argument.phase} persisted-state acceptance without AWS mutations")
