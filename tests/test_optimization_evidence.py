from __future__ import annotations

from src.agent import optimize
from src.utils.guardrails import ResourceMetric


def _metric(**overrides):
    values = {
        "provider": "aws",
        "resource_id": "aws:ec2:eu-central-1:i-abc123",
        "resource_type": "compute",
        "name": "worker",
        "region": "eu-central-1",
        "environment": "dev",
        "monthly_cost_usd": 100,
        "avg_cpu_percent": 5,
        "peak_cpu_percent": 20,
        "avg_memory_percent": 35,
        "metadata": {
            "discovery": "aws-live",
            "cost_status": "verified_monthly_cost",
            "cost_currency": "USD",
            "telemetry_window_hours": "336",
            "workload_stability": "stable",
        },
    }
    values.update(overrides)
    return ResourceMetric(**values)


def test_live_rightsizing_requires_memory_history_workload_and_cost_evidence():
    metric = _metric(avg_memory_percent=None, metadata={"discovery": "aws-live"})
    proposal = optimize({"metrics": [metric.model_dump(mode="json")]})["proposals"][0]

    assert proposal["action"] == "review_only"
    assert proposal["estimated_monthly_savings_usd"] == 0
    assert proposal["savings_basis"] == "unavailable"
    assert proposal["optimization_confidence"] == "low"
    assert "average memory utilization telemetry" in proposal["missing_evidence"]
    assert "at least 7 days of utilization history" in proposal["missing_evidence"]
    assert "workload stability/seasonality evidence" in proposal["missing_evidence"]
    assert "verified monthly resource-level USD cost" in proposal["missing_evidence"]
    assert "evidence is incomplete" in proposal["rationale"]


def test_live_rightsizing_can_be_recommended_only_when_all_evidence_is_present():
    metric = _metric()
    proposal = optimize({"metrics": [metric.model_dump(mode="json")]})["proposals"][0]

    assert proposal["action"] == "rightsize"
    assert proposal["optimization_confidence"] == "high"
    assert proposal["missing_evidence"] == []
    assert proposal["estimated_monthly_savings_usd"] == 30
    assert proposal["savings_basis"] == "verified_monthly_cost_estimate"


def test_high_memory_blocks_rightsizing_without_lowering_operational_risk_fields():
    metric = _metric(avg_memory_percent=82)
    proposal = optimize({"metrics": [metric.model_dump(mode="json")]})["proposals"][0]

    assert proposal["action"] == "review_only"
    assert proposal["optimization_confidence"] == "low"
    assert "memory utilization below the conservative 70% threshold" in proposal["missing_evidence"]


def test_production_critical_resource_keeps_critical_risk_separate_from_confidence():
    metric = _metric(environment="prod", production_critical=True)
    proposal = optimize({"metrics": [metric.model_dump(mode="json")]})["proposals"][0]

    assert proposal["action"] == "no_change"
    assert proposal["risk"] == "critical"
    assert proposal["optimization_confidence"] == "medium"
    assert proposal["missing_evidence"] == []
