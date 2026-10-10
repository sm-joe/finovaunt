from __future__ import annotations

from datetime import UTC, datetime

from src.utils.cost_evidence import build_cost_evidence_report


STAMP = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)


def _metric(*, metadata=None, monthly_cost_usd=0.0):
    return {
        "provider": "aws",
        "resource_id": "aws:ec2:eu-central-1:i-abc123",
        "resource_type": "compute",
        "name": "worker",
        "region": "eu-central-1",
        "environment": "dev",
        "production_critical": False,
        "monthly_cost_usd": monthly_cost_usd,
        "avg_cpu_percent": 3.2,
        "peak_cpu_percent": 12.0,
        "avg_memory_percent": 41.0,
        "metadata": metadata or {"discovery": "aws-live", "cost_status": "not_collected"},
    }


def _proposal(*, amount=0.0, basis="unavailable", action="review_only"):
    return {
        "resource_id": "aws:ec2:eu-central-1:i-abc123",
        "provider": "aws",
        "action": action,
        "rationale": "Resource cost evidence requires review before optimization.",
        "estimated_monthly_savings_usd": amount,
        "savings_basis": basis,
        "risk": "medium",
        "requires_human_approval": True,
        "proposed_instance_type": None,
    }


def test_missing_resource_cost_is_explicit_and_savings_not_estimable():
    report = build_cost_evidence_report(
        {"run_id": "run-1", "metrics": [_metric()], "proposals": [_proposal()]},
        generated_at=STAMP,
    )
    record = report["resources"][0]
    assert record["cost_evidence"]["status"] == "cost_unavailable"
    assert record["savings_evidence"]["classification"] == "not_estimable_from_available_evidence"
    assert record["savings_evidence"]["estimated_monthly_savings_usd"] == 0
    assert record["savings_evidence"]["realized_savings"]["status"] == "not_verified"
    assert report["generated_at"] == "2026-10-10T12:00:00Z"


def test_observed_14_day_cost_is_not_monthly_cost_or_monthly_savings_basis():
    metric = _metric(metadata={
        "discovery": "aws-live",
        "cost_status": "observed_14_day_cost",
        "cost_source": "aws_cost_explorer_resource_id",
        "observed_cost_period_amount": "12.34",
        "observed_cost_currency": "USD",
        "observed_cost_period_start": "2026-09-26",
        "observed_cost_period_end_exclusive": "2026-10-10",
    })
    report = build_cost_evidence_report(
        {"metrics": [metric], "proposals": [_proposal()]}, generated_at=STAMP
    )
    cost = report["resources"][0]["cost_evidence"]
    savings = report["resources"][0]["savings_evidence"]
    assert cost["status"] == "observed_period_cost_only"
    assert cost["amount"] == 12.34
    assert cost["period"]["basis"] == "observed_period_not_monthly"
    assert cost["monthly_cost_usd"] is None
    assert savings["classification"] == "not_estimable_from_available_evidence"


def test_mock_estimate_is_labeled_simulated():
    metric = _metric(
        monthly_cost_usd=100,
        metadata={"discovery": "mock", "cost_status": "simulated_monthly_cost", "cost_currency": "USD"},
    )
    proposal = _proposal(amount=30, basis="simulated_estimate", action="rightsize")
    report = build_cost_evidence_report(
        {"metrics": [metric], "proposals": [proposal]}, generated_at=STAMP
    )
    record = report["resources"][0]
    assert record["cost_evidence"]["status"] == "simulated_monthly_cost"
    assert record["cost_evidence"]["amount"] == 100
    assert record["savings_evidence"]["classification"] == "simulated_estimate"
    assert "not a production forecast" in record["savings_evidence"]["assumptions"][0]


def test_verified_monthly_cost_estimate_has_explicit_assumption_and_no_realized_savings():
    metric = _metric(
        monthly_cost_usd=100,
        metadata={"discovery": "aws-live", "cost_status": "verified_monthly_cost", "cost_currency": "USD", "cost_source": "approved_monthly_resource_source"},
    )
    proposal = _proposal(amount=30, basis="verified_monthly_cost_estimate", action="rightsize")
    report = build_cost_evidence_report(
        {"metrics": [metric], "proposals": [proposal]}, generated_at=STAMP
    )
    record = report["resources"][0]
    assert record["cost_evidence"]["monthly_cost_usd"] == 100
    assert record["savings_evidence"]["classification"] == "estimated_from_monthly_resource_cost"
    assert record["savings_evidence"]["realized_savings"]["amount_usd"] is None


def test_account_level_total_is_context_only_not_copied_to_resource():
    report = build_cost_evidence_report(
        {
            "metrics": [_metric()],
            "proposals": [_proposal()],
            "billing_summary": {
                "status": "available",
                "period_start": "2026-09-01",
                "period_end_exclusive": "2026-10-01",
                "currency": "USD",
                "total_cost": 15.2449304707,
                "resource_attribution": "not_available",
            },
        },
        generated_at=STAMP,
    )
    assert report["account_billing_context"]["total_cost"] == 15.2449304707
    record = report["resources"][0]
    assert record["cost_evidence"]["amount"] is None
    assert record["savings_evidence"]["estimated_monthly_savings_usd"] == 0
    assert "total_cost" not in record


def test_resource_without_matching_proposal_is_still_reported():
    report = build_cost_evidence_report(
        {"metrics": [_metric()], "proposals": []}, generated_at=STAMP
    )
    assert report["summary"]["resource_count"] == 1
    assert report["resources"][0]["recommendation"]["action"] == "not_proposed"
    assert any("No proposal matched" in item for item in report["resources"][0]["data_quality_warnings"])


def test_invalid_non_finite_cost_is_not_serialized_as_a_number():
    metric = _metric(
        monthly_cost_usd=float("nan"),
        metadata={"discovery": "mock", "cost_status": "simulated_monthly_cost", "cost_currency": "USD"},
    )
    report = build_cost_evidence_report({"metrics": [metric], "proposals": []}, generated_at=STAMP)
    assert report["resources"][0]["cost_evidence"]["status"] == "simulated_monthly_cost"
    assert report["resources"][0]["cost_evidence"]["amount"] is None
