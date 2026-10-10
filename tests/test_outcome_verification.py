from __future__ import annotations

from datetime import UTC, datetime

from src.utils.outcome_verification import build_outcome_verification

STAMP = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)


def _report(run_id: str, generated_at: str, amount: float, start: str | None, end: str | None):
    return {
        "run_id": run_id,
        "generated_at": generated_at,
        "account_billing_context": {"total_cost": 999999},
        "resources": [{
            "provider": "aws",
            "region": "eu-central-1",
            "resource_id": "i-abc123",
            "cost_evidence": {
                "status": "verified_monthly_cost",
                "currency": "USD",
                "monthly_cost_usd": amount,
                "period": {"start": start, "end_exclusive": end, "basis": "verified_billing_period"},
            },
        }],
    }


def _change(*, approval="approved", deployment="applied", deployed_at="2026-09-16T00:00:00Z", evidence_ref="terraform-run-42"):
    return {
        "change_id": "CHG-42",
        "approval": {"status": approval, "approved_at": "2026-09-15T12:00:00Z"},
        "deployment": {"status": deployment, "deployed_at": deployed_at, "evidence_ref": evidence_ref},
        "resources": [{"provider": "aws", "region": "eu-central-1", "resource_id": "i-abc123"}],
    }


def test_verifies_cost_reduction_only_with_approval_deployment_and_comparable_periods():
    before = _report("before", "2026-09-15T00:00:00Z", 100, "2026-08-16T00:00:00Z", "2026-09-15T00:00:00Z")
    after = _report("after", "2026-10-17T00:00:00Z", 70, "2026-09-16T00:00:00Z", "2026-10-16T00:00:00Z")
    result = build_outcome_verification(before, after, _change(), generated_at=STAMP)
    item = result["resources"][0]
    assert item["verification_status"] == "verified_monthly_cost_reduction"
    assert item["realized_savings"] == {
        "status": "verified", "amount_usd": 30.0,
        "basis": "comparable_verified_monthly_resource_cost",
        "attribution": "temporally_associated_with_change; causal attribution is not proven by cost comparison alone",
    }
    assert result["summary"]["realized_savings_usd"] == 30
    assert result["summary"]["causal_attribution_proven"] is False


def test_current_monthly_cost_estimate_without_dated_window_is_not_verified():
    before = _report("before", "2026-09-15T00:00:00Z", 100, None, None)
    after = _report("after", "2026-10-16T00:00:00Z", 70, None, None)
    item = build_outcome_verification(before, after, _change(), generated_at=STAMP)["resources"][0]
    assert item["verification_status"] == "not_verified"
    assert item["realized_savings"]["amount_usd"] is None
    assert any("dated billing windows" in reason for reason in item["limitations"])


def test_unapproved_change_fails_closed():
    before = _report("before", "2026-09-15T00:00:00Z", 100, "2026-08-16T00:00:00Z", "2026-09-15T00:00:00Z")
    after = _report("after", "2026-10-17T00:00:00Z", 70, "2026-09-16T00:00:00Z", "2026-10-16T00:00:00Z")
    item = build_outcome_verification(before, after, _change(approval="pending"), generated_at=STAMP)["resources"][0]
    assert item["verification_status"] == "not_verified"
    assert item["realized_savings"]["amount_usd"] is None


def test_missing_deployment_reference_fails_closed():
    before = _report("before", "2026-09-15T00:00:00Z", 100, "2026-08-16T00:00:00Z", "2026-09-15T00:00:00Z")
    after = _report("after", "2026-10-17T00:00:00Z", 70, "2026-09-16T00:00:00Z", "2026-10-16T00:00:00Z")
    item = build_outcome_verification(before, after, _change(evidence_ref=""), generated_at=STAMP)["resources"][0]
    assert item["verification_status"] == "not_verified"


def test_overlapping_or_unequal_periods_are_not_verified():
    before = _report("before", "2026-09-15T00:00:00Z", 100, "2026-08-16T00:00:00Z", "2026-09-15T00:00:00Z")
    after = _report("after", "2026-10-17T00:00:00Z", 70, "2026-09-10T00:00:00Z", "2026-10-10T00:00:00Z")
    item = build_outcome_verification(before, after, _change(), generated_at=STAMP)["resources"][0]
    assert item["verification_status"] == "not_verified"
    assert any("at or after deployment" in reason for reason in item["limitations"])


def test_cost_increase_is_reported_not_counted_as_savings():
    before = _report("before", "2026-09-15T00:00:00Z", 70, "2026-08-16T00:00:00Z", "2026-09-15T00:00:00Z")
    after = _report("after", "2026-10-17T00:00:00Z", 90, "2026-09-16T00:00:00Z", "2026-10-16T00:00:00Z")
    item = build_outcome_verification(before, after, _change(), generated_at=STAMP)["resources"][0]
    assert item["verification_status"] == "monthly_cost_increased"
    assert item["realized_savings"]["status"] == "verified_negative_outcome"
    assert item["realized_savings"]["amount_usd"] == -20


def test_simulated_costs_are_not_used_even_when_amounts_and_periods_exist():
    before = _report("before", "2026-09-15T00:00:00Z", 100, "2026-08-16T00:00:00Z", "2026-09-15T00:00:00Z")
    after = _report("after", "2026-10-17T00:00:00Z", 70, "2026-09-16T00:00:00Z", "2026-10-16T00:00:00Z")
    before["resources"][0]["cost_evidence"]["status"] = "simulated_monthly_cost"
    item = build_outcome_verification(before, after, _change(), generated_at=STAMP)["resources"][0]
    assert item["verification_status"] == "not_verified"
    assert item["baseline_cost_usd"] is None


def test_account_level_total_never_affects_resource_savings():
    before = _report("before", "2026-09-15T00:00:00Z", 100, "2026-08-16T00:00:00Z", "2026-09-15T00:00:00Z")
    after = _report("after", "2026-10-17T00:00:00Z", 100, "2026-09-16T00:00:00Z", "2026-10-16T00:00:00Z")
    result = build_outcome_verification(before, after, _change(), generated_at=STAMP)
    assert result["summary"]["realized_savings_usd"] == 0
    assert result["resources"][0]["verification_status"] == "no_cost_reduction_observed"


def test_observed_period_cost_reduction_is_reported_without_claiming_monthly_savings():
    before = _report("before", "2026-09-15T00:00:00Z", 100, "2026-08-16T00:00:00Z", "2026-09-15T00:00:00Z")
    after = _report("after", "2026-10-17T00:00:00Z", 70, "2026-09-16T00:00:00Z", "2026-10-16T00:00:00Z")
    for report, amount in ((before, 100), (after, 70)):
        cost = report["resources"][0]["cost_evidence"]
        cost["status"] = "observed_period_cost_only"
        cost["amount"] = amount
        cost["monthly_cost_usd"] = None
        cost["period"]["basis"] = "observed_period_not_monthly"
    result = build_outcome_verification(before, after, _change(), generated_at=STAMP)
    item = result["resources"][0]
    assert item["verification_status"] == "verified_observed_period_cost_reduction"
    assert item["cost_reduction_usd"] == 30
    assert item["realized_savings"]["status"] == "not_verified"
    assert item["realized_monthly_savings_usd"] is None


def test_missing_resource_in_after_report_is_not_verified():
    before = _report("before", "2026-09-15T00:00:00Z", 100, "2026-08-16T00:00:00Z", "2026-09-15T00:00:00Z")
    after = _report("after", "2026-10-17T00:00:00Z", 70, "2026-09-16T00:00:00Z", "2026-10-16T00:00:00Z")
    after["resources"] = []
    item = build_outcome_verification(before, after, _change(), generated_at=STAMP)["resources"][0]
    assert item["verification_status"] == "not_verified"
    assert any("absent from the post-change" in reason for reason in item["limitations"])
