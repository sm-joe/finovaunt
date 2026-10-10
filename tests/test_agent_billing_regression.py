"""Regression tests for billing integration in the FinOps workflow."""

from types import SimpleNamespace

import src.agent as agent_module


def _fake_metric() -> SimpleNamespace:
    return SimpleNamespace(
        model_dump=lambda mode="python": {
            "resource_id": "test-instance",
            "provider": "aws",
            "resource_type": "compute",
            "environment": "dev",
            "avg_cpu_percent": 5.0,
            "peak_cpu_percent": 15.0,
            "monthly_cost_usd": 0.0,
            "production_critical": False,
        }
    )


def _available_billing() -> dict:
    return {
        "status": "available",
        "period_start": "2026-09-01",
        "period_end_exclusive": "2026-10-01",
        "metric": "UnblendedCost",
        "currency": "USD",
        "total_cost": 15.0,
        "group_by": ["SERVICE", "REGION"],
        "groups": [],
        "resource_attribution": "not_available",
    }


def test_aws_collection_includes_billing_summary(
    monkeypatch,
) -> None:
    monkeypatch.setenv("FINOPS_DISCOVERY_MODE", "aws")

    monkeypatch.setattr(
        agent_module,
        "collect_aws_metrics",
        lambda: ([_fake_metric()], []),
    )
    monkeypatch.setattr(
        agent_module,
        "collect_aws_cost_summary",
        _available_billing,
    )

    result = agent_module.collect_data({"run_id": "billing-success"})

    assert result["status"] == "data_collected"
    assert result["run_id"] == "billing-success"
    assert len(result["metrics"]) == 1
    assert result["billing_summary"]["status"] == "available"
    assert result["billing_summary"]["total_cost"] == 15.0
    assert (
        result["billing_summary"]["resource_attribution"]
        == "not_available"
    )


def test_billing_failure_does_not_fail_metrics_collection(
    monkeypatch,
) -> None:
    monkeypatch.setenv("FINOPS_DISCOVERY_MODE", "aws")

    monkeypatch.setattr(
        agent_module,
        "collect_aws_metrics",
        lambda: ([_fake_metric()], []),
    )

    def fail_billing():
        raise RuntimeError("billing service unavailable")

    monkeypatch.setattr(
        agent_module,
        "collect_aws_cost_summary",
        fail_billing,
    )

    result = agent_module.collect_data({"run_id": "billing-failure"})

    assert result["status"] == "data_collected"
    assert len(result["metrics"]) == 1
    assert result["billing_summary"]["status"] == "unavailable"
    assert (
        result["billing_summary"]["resource_attribution"]
        == "not_available"
    )
    assert any(
        "billing data unavailable" in event.lower()
        for event in result["events"]
    )


def test_aws_metrics_failure_blocks_collection(
    monkeypatch,
) -> None:
    monkeypatch.setenv("FINOPS_DISCOVERY_MODE", "aws")
    billing_called = False

    def fail_metrics():
        raise RuntimeError("metrics service unavailable")

    def collect_billing():
        nonlocal billing_called
        billing_called = True
        return _available_billing()

    monkeypatch.setattr(
        agent_module,
        "collect_aws_metrics",
        fail_metrics,
    )
    monkeypatch.setattr(
        agent_module,
        "collect_aws_cost_summary",
        collect_billing,
    )

    result = agent_module.collect_data({"run_id": "metrics-failure"})

    assert result["status"] == "collection_failed"
    assert result["metrics"] == []
    assert result["billing_summary"]["status"] == "not_attempted"
    assert billing_called is False


def test_mock_mode_does_not_call_live_billing(
    monkeypatch,
) -> None:
    monkeypatch.setenv("FINOPS_DISCOVERY_MODE", "mock")

    monkeypatch.setattr(
        agent_module,
        "collect_mock_metrics",
        lambda: [_fake_metric()],
    )

    def fail_if_called():
        raise AssertionError(
            "Live Cost Explorer must not run in mock mode."
        )

    monkeypatch.setattr(
        agent_module,
        "collect_aws_cost_summary",
        fail_if_called,
    )

    result = agent_module.collect_data({"run_id": "mock-run"})

    assert result["status"] == "data_collected"
    assert len(result["metrics"]) == 1
    assert result["billing_summary"]["status"] == "not_applicable"


def test_aws_collection_with_no_metrics_is_blocked(
    monkeypatch,
) -> None:
    monkeypatch.setenv("FINOPS_DISCOVERY_MODE", "aws")

    monkeypatch.setattr(
        agent_module,
        "collect_aws_metrics",
        lambda: ([], ["No usable CPU metrics"]),
    )
    monkeypatch.setattr(
        agent_module,
        "collect_aws_cost_summary",
        _available_billing,
    )

    result = agent_module.collect_data({"run_id": "empty-metrics"})

    assert result["status"] == "collection_failed"
    assert result["metrics"] == []
    assert result["validation_error"] == (
        "AWS discovery returned no resources with usable CPU telemetry. "
        "Optimization and artifact writing were blocked."
    )
    assert result["billing_summary"]["status"] == "available"