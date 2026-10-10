from __future__ import annotations

from src.agent import _attach_ec2_resource_costs, optimize
from src.utils.guardrails import ResourceMetric


def _live_metric(
    *,
    resource_id: str = "aws:ec2:eu-central-1:i-abc123",
    region: str = "eu-central-1",
    monthly_cost_usd: float = 0,
    metadata: dict[str, str] | None = None,
) -> ResourceMetric:
    return ResourceMetric(
        provider="aws",
        resource_id=resource_id,
        resource_type="compute",
        name="worker",
        region=region,
        environment="dev",
        monthly_cost_usd=monthly_cost_usd,
        avg_cpu_percent=3,
        peak_cpu_percent=12,
        metadata=metadata or {
            "discovery": "aws-live",
            "cost_status": "not_collected",
        },
    )


def test_ec2_cost_attaches_only_on_exact_resource_and_region_match() -> None:
    metric = _live_metric()
    result = _attach_ec2_resource_costs(
        [metric],
        {
            "status": "available",
            "period_start": "2026-09-26",
            "period_end_exclusive": "2026-10-10",
            "resources": [
                {
                    "resource_id": "i-abc123",
                    "region": "eu-central-1",
                    "amount": 12.34,
                    "currency": "USD",
                }
            ],
        },
    )

    assert result[0].metadata["cost_status"] == "observed_14_day_cost"
    assert result[0].metadata["observed_cost_period_amount"] == "12.34"
    assert result[0].metadata["observed_cost_currency"] == "USD"
    assert result[0].monthly_cost_usd == 0


def test_ec2_cost_with_wrong_region_is_not_attached() -> None:
    metric = _live_metric()
    _attach_ec2_resource_costs(
        [metric],
        {
            "status": "available",
            "resources": [
                {
                    "resource_id": "i-abc123",
                    "region": "us-east-1",
                    "amount": 12.34,
                    "currency": "USD",
                }
            ],
        },
    )

    assert "observed_cost_period_amount" not in metric.metadata
    assert metric.monthly_cost_usd == 0


def test_ambiguous_resource_cost_is_not_selected() -> None:
    metric = _live_metric()
    _attach_ec2_resource_costs(
        [metric],
        {
            "status": "available",
            "resources": [
                {
                    "resource_id": "i-abc123",
                    "region": "eu-central-1",
                    "amount": 12.34,
                    "currency": "USD",
                },
                {
                    "resource_id": "i-abc123",
                    "region": "eu-central-1",
                    "amount": 13.34,
                    "currency": "USD",
                },
            ],
        },
    )

    assert metric.metadata["cost_status"] == "ambiguous_resource_cost"
    assert "observed_cost_period_amount" not in metric.metadata


def test_observed_14_day_cost_does_not_create_monthly_savings() -> None:
    metric = _live_metric(
        metadata={
            "discovery": "aws-live",
            "cost_status": "observed_14_day_cost",
            "observed_cost_period_amount": "12.34",
            "observed_cost_currency": "USD",
        }
    )
    result = optimize({"metrics": [metric.model_dump(mode="json")]})
    proposal = result["proposals"][0]

    assert proposal["action"] == "review_only"
    assert proposal["estimated_monthly_savings_usd"] == 0
    assert proposal["savings_basis"] == "unavailable"


def test_mock_savings_are_explicitly_marked_as_simulated() -> None:
    metric = ResourceMetric(
        provider="aws",
        resource_id="aws:ec2:eu-central-1:worker-01",
        resource_type="compute",
        name="worker-01",
        region="eu-central-1",
        environment="dev",
        monthly_cost_usd=100,
        avg_cpu_percent=3,
        peak_cpu_percent=12,
        metadata={
            "discovery": "mock",
            "cost_status": "simulated_monthly_cost",
            "cost_currency": "USD",
        },
    )
    result = optimize({"metrics": [metric.model_dump(mode="json")]})
    proposal = result["proposals"][0]

    assert proposal["action"] == "rightsize"
    assert proposal["estimated_monthly_savings_usd"] == 30
    assert proposal["savings_basis"] == "simulated_estimate"
    assert "simulated estimate" in proposal["rationale"]
