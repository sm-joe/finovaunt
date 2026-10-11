import json

from scripts import access_control


def test_default_admin_must_change_password_and_account_registry_is_persistent(tmp_path, monkeypatch):
    state_path = tmp_path / "control-plane.json"
    monkeypatch.setenv("FINOVAUNT_CONTROL_FILE", str(state_path))

    first_login = access_control.login("admin", "admin")
    assert first_login is not None
    assert first_login["must_change_password"] is True
    assert access_control.change_password(first_login["token"], "admin", "a-long-test-password-2026")
    assert access_control.session(first_login["token"])["must_change_password"] is False
    assert access_control.login("admin", "admin") is None
    assert access_control.login("admin", "a-long-test-password-2026") is not None

    account = access_control.add_account(
        "Production", "aws", "123456789012",
        "arn:aws:iam::123456789012:role/FinovauntBillingReadOnly", "us-east-1", "temporary-external-id"
    )
    assert account["account_id"] == "123456789012"
    assert "external_id" not in account
    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    assert "external_id" not in json.dumps(persisted)
    assert access_control.list_accounts()[0]["name"] == "Production"


def test_initial_password_recovery_is_limited_to_required_rotation(tmp_path, monkeypatch):
    monkeypatch.setenv("FINOVAUNT_CONTROL_FILE", str(tmp_path / "control-plane.json"))
    first = access_control.login("admin", "admin")
    assert first is not None
    # A stale bootstrap hash must not strand an authenticated first-login rotation.
    state_path = tmp_path / "control-plane.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["user"]["password"] = {"salt": "c3RhbGUtc2FsdA==", "hash": "c3RhbGUtaGFzaA=="}
    state_path.write_text(json.dumps(state), encoding="utf-8")
    assert access_control.change_password(first["token"], "admin", "new-secure-password-2026")
    assert access_control.login("admin", "new-secure-password-2026") is not None
    assert not access_control.change_password(first["token"], "admin", "another-secure-password-2026")
