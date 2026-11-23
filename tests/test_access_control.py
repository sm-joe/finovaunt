import json

from scripts import access_control


def test_default_admin_must_change_password_and_account_registry_is_persistent(tmp_path, monkeypatch):
    state_path = tmp_path / "control-plane.json"
    monkeypatch.setenv("FINOVAUNT_BOOTSTRAP_PASSWORD", "initial-test-password-2026")
    monkeypatch.setenv("FINOVAUNT_CONTROL_FILE", str(state_path))

    first_login = access_control.login("admin", "initial-test-password-2026")
    assert first_login is not None
    assert first_login["must_change_password"] is True
    assert access_control.change_password(first_login["token"], "initial-test-password-2026", "a-long-test-password-2026")
    assert access_control.session(first_login["token"]) is None  # Password rotation revokes sessions.
    assert access_control.login("admin", "initial-test-password-2026") is None
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


def test_initial_password_recovery_rejects_stale_hash(tmp_path, monkeypatch):
    monkeypatch.setenv("FINOVAUNT_BOOTSTRAP_PASSWORD", "initial-test-password-2026")
    monkeypatch.setenv("FINOVAUNT_CONTROL_FILE", str(tmp_path / "control-plane.json"))
    first = access_control.login("admin", "initial-test-password-2026")
    assert first is not None
    state_path = tmp_path / "control-plane.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["user"]["password"] = {"salt": "c3RhbGUtc2FsdA==", "hash": "c3RhbGUtaGFzaA=="}
    state_path.write_text(json.dumps(state), encoding="utf-8")
    assert not access_control.change_password(first["token"], "initial-test-password-2026", "new-secure-password-2026")
    assert access_control.login("admin", "new-secure-password-2026") is None


def test_expired_session_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("FINOVAUNT_BOOTSTRAP_PASSWORD", "initial-test-password-2026")
    monkeypatch.setenv("FINOVAUNT_CONTROL_FILE", str(tmp_path / "control-plane.json"))
    first = access_control.login("admin", "initial-test-password-2026")
    assert first is not None
    token = first["token"]
    username, _ = access_control._SESSIONS[token]
    access_control._SESSIONS[token] = (username, 0)
    assert access_control.session(token) is None
    assert not access_control.change_password(token, "initial-test-password-2026", "new-secure-password-2026")


def test_account_role_must_match_account_and_removal_purges_history(tmp_path, monkeypatch):
    import pytest
    monkeypatch.setenv("FINOVAUNT_BOOTSTRAP_PASSWORD", "initial-test-password-2026")
    monkeypatch.setenv("FINOVAUNT_CONTROL_FILE", str(tmp_path / "control-plane.json"))
    with pytest.raises(ValueError, match="onboarded AWS account"):
        access_control.add_account(
            "Invalid", "aws", "123456789012",
            "arn:aws:iam::999999999999:role/ReadOnly", "us-east-1",
        )
    account = access_control.add_account(
        "Production", "aws", "123456789012",
        "arn:aws:iam::123456789012:role/ReadOnly", "us-east-1",
    )
    access_control.save_billing_scan(account["account_id"], {"total_cost": 23.4})
    assert len(access_control.billing_history("123456789012")) == 1
    assert access_control.delete_account("123456789012")
    assert not access_control.delete_account("123456789012")
    assert access_control.list_accounts() == []
    assert access_control.billing_history("123456789012") == []


def test_recommendation_decisions_are_auditable_and_never_apply_infrastructure(tmp_path, monkeypatch):
    import pytest
    monkeypatch.setenv("FINOVAUNT_BOOTSTRAP_PASSWORD", "initial-test-password-2026")
    monkeypatch.setenv("FINOVAUNT_CONTROL_FILE", str(tmp_path / "control-plane.json"))
    with pytest.raises(ValueError):
        access_control.record_recommendation_decision(
            run_id="scan1", resource_id="i-abc", action="approved", note="short", reviewed_by="admin"
        )
    with pytest.raises(ValueError):
        access_control.record_recommendation_decision(
            run_id="scan1", resource_id="i-abc", action="applied", note="This must be rejected.", reviewed_by="admin"
        )
    record = access_control.record_recommendation_decision(
        run_id="scan1", resource_id="i-abc", action="approved",
        note="Human reviewed the evidence and approved proposal preparation.",
        reviewed_by="admin",
    )
    assert record["infrastructure_applied"] is False
    assert record["reviewed_by"] == "admin"
    assert access_control.recommendation_decisions("scan1")[0]["id"] == record["id"]
    assert access_control.recommendation_decisions("other-run") == []


def test_collector_configuration_update_preserves_history_and_requires_fresh_evidence(tmp_path, monkeypatch):
    from scripts import access_control
    from src.utils.live_dashboard import account_dashboard
    monkeypatch.setenv("FINOVAUNT_BOOTSTRAP_PASSWORD", "initial-test-password-2026")
    monkeypatch.setenv("FINOVAUNT_CONTROL_FILE", str(tmp_path / "control-plane.json"))
    account = access_control.add_account(
        "Original", "aws", "123456789012",
        "arn:aws:iam::123456789012:role/OriginalRole", "us-east-1",
    )
    access_control.save_billing_scan(account["account_id"], {
        "scanned_at": "2026-11-23", "total_cost": 12.2, "status": "success",
    })
    scan = access_control.save_inventory_scan(account["account_id"], {
        "scanned_at": "2026-11-23", "region": "us-east-1",
        "status": "success", "truncated": False,
        "assets": [{"id": "vol-abc", "type": "ebs", "name": "legacy", "state": "available"}],
    })
    assert account_dashboard(account["account_id"])["billing"]["total_cost"] == 12.2
    assert len(account_dashboard(account["account_id"])["review_candidates"]) == 1
    updated = access_control.update_account_configuration(
        account_id=account["account_id"], name="Updated",
        role_arn="arn:aws:iam::123456789012:role/NewReadRole",
        region="eu-west-1", note="Switching collector scope after AWS account review.",
        reviewed_by="admin",
    )
    assert updated["config_revision"] == 2
    dashboard = account_dashboard(account["account_id"])
    assert dashboard["billing"] is None and dashboard["inventory"] is None
    assert dashboard["review_candidates"] == []
    assert dashboard["billing_status"] == "not_collected"
    assert access_control.billing_history(account["account_id"])[0]["total_cost"] == 12.2
    assert access_control.optimization_history(account["account_id"])[0]["resource_id"] == "vol-abc"
    assert len(dashboard["account_config_audit"]) == 1
    assert dashboard["account_config_audit"][0]["aws_resources_modified"] is False
    fresh = access_control.save_inventory_scan(account["account_id"], {
        "scanned_at": "2026-11-24", "region": "eu-west-1",
        "status": "empty_inventory", "truncated": False, "assets": [],
    })
    assert fresh["config_revision"] == 2
    assert account_dashboard(account["account_id"])["inventory"]["id"] == fresh["id"]
    assert scan["id"] != fresh["id"]


def test_collector_configuration_rejects_cross_account_roles(tmp_path, monkeypatch):
    from scripts import access_control
    monkeypatch.setenv("FINOVAUNT_BOOTSTRAP_PASSWORD", "initial-test-password-2026")
    monkeypatch.setenv("FINOVAUNT_CONTROL_FILE", str(tmp_path / "control-plane.json"))
    access_control.add_account(
        "Original", "aws", "123456789012",
        "arn:aws:iam::123456789012:role/OriginalRole", "us-east-1",
    )
    with pytest.raises(ValueError, match="onboarded AWS account"):
        access_control.update_account_configuration(
            account_id="123456789012", name="Invalid",
            role_arn="arn:aws:iam::999999999999:role/Other",
            region="us-east-1", note="Reviewing unauthorized cross-account role.",
            reviewed_by="admin",
        )
