from __future__ import annotations

from datetime import UTC, datetime

from src.utils.proposal_history import build_proposal_history

STAMP = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)


def _resource(*, cpu=10, monthly_cost=100, cost_status="verified_monthly_cost", estimate=20, action="rightsize"):
    return {
        "resource_id": "aws:ec2:eu-central-1:i-abc123",
        "provider": "aws",
        "resource_type": "compute",
        "name": "worker",
        "region": "eu-central-1",
        "environment": "dev",
        "utilization": {"avg_cpu_percent": cpu, "peak_cpu_percent": cpu + 5, "avg_memory_percent": 40},
        "cost_evidence": {
            "status": cost_status,
            "evidence_kind": "verified_monthly_resource_cost" if cost_status == "verified_monthly_cost" else "simulation",
            "amount": monthly_cost,
            "currency": "USD",
            "monthly_cost_usd": monthly_cost if cost_status == "verified_monthly_cost" else None,
            "period": {"start": None, "end_exclusive": None, "basis": "monthly" if cost_status == "verified_monthly_cost" else ("observed_period_not_monthly" if cost_status == "observed_period_cost_only" else "monthly_simulation")},
        },
        "recommendation": {"action": action, "risk": "medium", "requires_human_approval": True, "proposed_instance_type": "t3.small"},
        "savings_evidence": {
            "estimated_monthly_savings_usd": estimate,
            "basis": "verified_monthly_cost_estimate",
            "classification": "estimated_from_monthly_resource_cost",
            "realized_savings": {"status": "not_verified", "amount_usd": None},
        },
    }


def _report(run_id, resource):
    return {"run_id": run_id, "generated_at": "2026-10-10T12:00:00Z", "resources": [resource], "account_billing_context": {"total_cost": 999}}


def test_first_run_has_no_baseline_and_never_claims_realized_savings():
    history = build_proposal_history(_report("r1", _resource()), generated_at=STAMP)
    record = history["runs"][0]["resources"][0]
    assert history["run_count"] == 1
    assert record["changes_since_previous"]["baseline"] == "no_previous_snapshot"
    assert record["changes_since_previous"]["realized_savings"]["status"] == "not_verified"
    assert record["savings"]["realized_savings_usd"] is None


def test_compares_utilization_and_verified_monthly_resource_cost_only():
    first = build_proposal_history(_report("r1", _resource(cpu=10, monthly_cost=100)), generated_at=STAMP)
    second = build_proposal_history(_report("r2", _resource(cpu=16, monthly_cost=85)), first, generated_at=STAMP)
    delta = second["runs"][-1]["resources"][0]["changes_since_previous"]
    assert delta["utilization_delta_percentage_points"]["avg_cpu_percent"] == 6
    assert delta["monthly_resource_cost_delta_usd"] == -15
    assert delta["cost_comparison_status"] == "comparable_verified_monthly_resource_cost"
    assert delta["proposed_monthly_savings_delta_usd"] == 0
    assert delta["realized_savings"]["status"] == "not_verified"


def test_never_compares_observed_period_or_simulated_cost_as_verified_monthly_cost():
    first = build_proposal_history(_report("r1", _resource(cost_status="observed_period_cost_only", monthly_cost=100)), generated_at=STAMP)
    second = build_proposal_history(_report("r2", _resource(cost_status="observed_period_cost_only", monthly_cost=80)), first, generated_at=STAMP)
    delta = second["runs"][-1]["resources"][0]["changes_since_previous"]
    assert delta["monthly_resource_cost_delta_usd"] is None
    assert delta["cost_comparison_status"] == "observed_period_cost_not_compared_as_monthly"


def test_account_level_total_is_not_promoted_to_resource_cost():
    history = build_proposal_history(_report("r1", _resource(cost_status="cost_unavailable", monthly_cost=999)), generated_at=STAMP)
    record = history["runs"][0]["resources"][0]
    assert record["cost"]["monthly_cost_usd"] is None
    assert "total_cost" not in record["cost"]
    assert history["runs"][0]["account_billing_context"]["total_cost"] == 999


def test_same_run_retry_replaces_snapshot_instead_of_double_counting():
    first = build_proposal_history(_report("r1", _resource(cpu=10)), generated_at=STAMP)
    retry = build_proposal_history(_report("r1", _resource(cpu=12)), first, generated_at=STAMP)
    assert retry["run_count"] == 1
    assert retry["runs"][0]["resources"][0]["utilization"]["avg_cpu_percent"] == 12


def test_resource_key_keeps_region_identity_separate():
    first = build_proposal_history(_report("r1", _resource()), generated_at=STAMP)
    different_region = _resource()
    different_region["region"] = "us-east-1"
    second = build_proposal_history(_report("r2", different_region), first, generated_at=STAMP)
    delta = second["runs"][-1]["resources"][0]["changes_since_previous"]
    assert delta["baseline"] == "no_previous_snapshot"


def test_simulated_monthly_cost_is_never_reported_as_verified_cost_delta():
    first = build_proposal_history(
        _report("r1", _resource(cost_status="simulated_monthly_cost", monthly_cost=100)),
        generated_at=STAMP,
    )
    second = build_proposal_history(
        _report("r2", _resource(cost_status="simulated_monthly_cost", monthly_cost=80)),
        first,
        generated_at=STAMP,
    )
    delta = second["runs"][-1]["resources"][0]["changes_since_previous"]
    assert delta["monthly_resource_cost_delta_usd"] is None
    assert delta["cost_comparison_status"] == "simulated_cost_not_production_evidence"
