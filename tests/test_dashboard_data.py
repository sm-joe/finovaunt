from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.utils.dashboard_data import (
    DashboardDataError,
    build_assets,
    build_opportunities,
    build_overview,
    build_scan_detail,
    build_scans,
    load_artifacts,
)


@pytest.fixture
def artifacts() -> dict:
    evidence = {
        "schema_version": "1.0",
        "run_id": "run-current",
        "generated_at": "2026-10-10T10:00:00Z",
        "account_billing_context": {
            "status": "available",
            "total_cost": 1000.0,
            "currency": "USD",
            "period_start": "2026-09-01",
            "period_end_exclusive": "2026-10-01",
            "resource_attribution": "not_available",
        },
        "resources": [
            {
                "resource_id": "i-123",
                "name": "dev-app",
                "provider": "aws",
                "resource_type": "compute",
                "region": "eu-central-1",
                "environment": "dev",
                "production_critical": False,
                "utilization": {"avg_cpu_percent": 8.0, "peak_cpu_percent": 20.0, "avg_memory_percent": 30.0},
                "cost_evidence": {"status": "verified_monthly_cost", "amount": 200.0, "currency": "USD", "monthly_cost_usd": 200.0, "period": {"basis": "monthly"}, "source": "fixture"},
                "recommendation": {"action": "rightsize", "rationale": "Low utilization", "risk": "medium", "requires_human_approval": True, "proposed_instance_type": "smaller"},
                "savings_evidence": {"estimated_monthly_savings_usd": 60.0, "basis": "verified_monthly_cost_estimate", "classification": "estimated_from_monthly_resource_cost", "assumptions": [], "realized_savings": {"status": "not_verified", "amount_usd": None}},
                "data_quality_warnings": [],
            },
            {
                "resource_id": "i-456",
                "name": "mock-app",
                "provider": "aws",
                "resource_type": "compute",
                "region": "eu-central-1",
                "environment": "test",
                "production_critical": False,
                "utilization": {"avg_cpu_percent": 3.0, "peak_cpu_percent": 8.0, "avg_memory_percent": 10.0},
                "cost_evidence": {"status": "simulated_monthly_cost", "amount": 100.0, "currency": "USD", "monthly_cost_usd": None, "period": {"basis": "monthly_simulation"}, "source": "mock"},
                "recommendation": {"action": "rightsize", "rationale": "Mock estimate", "risk": "low", "requires_human_approval": True},
                "savings_evidence": {"estimated_monthly_savings_usd": 30.0, "basis": "simulated_estimate", "classification": "simulated_estimate", "assumptions": ["Mock"], "realized_savings": {"status": "not_verified", "amount_usd": None}},
                "data_quality_warnings": ["Mock data"],
            },
            {
                "resource_id": "i-789",
                "name": "unknown-cost",
                "provider": "aws",
                "resource_type": "compute",
                "region": "eu-central-1",
                "environment": "prod",
                "production_critical": True,
                "utilization": {"avg_cpu_percent": 40.0, "peak_cpu_percent": 80.0, "avg_memory_percent": None},
                "cost_evidence": {"status": "cost_unavailable", "amount": None, "currency": "unknown", "monthly_cost_usd": None, "period": {}, "source": "unknown"},
                "recommendation": {"action": "review_only", "rationale": "Evidence missing", "risk": "high", "requires_human_approval": True},
                "savings_evidence": {"estimated_monthly_savings_usd": 0, "basis": "unavailable", "classification": "not_estimable_from_available_evidence", "assumptions": ["Missing cost"], "realized_savings": {"status": "not_verified", "amount_usd": None}},
                "data_quality_warnings": ["No resource cost"],
            },
        ],
    }
    proposal = {
        "run_id": "run-current",
        "proposals": [
            {"resource_id": "i-123", "optimization_confidence": "high", "missing_evidence": []},
            {"resource_id": "i-456", "optimization_confidence": "low", "missing_evidence": ["mock inputs"]},
            {"resource_id": "i-789", "optimization_confidence": "low", "missing_evidence": ["verified monthly cost"]},
        ],
    }
    history = {
        "latest_run_id": "run-current",
        "runs": [
            {"run_id": "run-old", "generated_at": "2026-10-09T10:00:00Z", "resource_count": 2, "resources": []},
            {"run_id": "run-current", "generated_at": "2026-10-10T10:00:00Z", "resource_count": 3, "resources": [
                {"recommendation": {"action": "rightsize"}},
                {"recommendation": {"action": "rightsize"}},
                {"recommendation": {"action": "review_only"}},
            ]},
        ],
    }
    return {"evidence": evidence, "proposal": proposal, "billing": {}, "history": history}


def test_overview_keeps_simulated_and_realized_savings_separate(artifacts: dict) -> None:
    result = build_overview(artifacts)
    assert result["resources_scanned"] == 3
    assert result["potential_monthly_savings_usd"] == 60.0
    assert result["simulated_monthly_savings_usd"] == 30.0
    assert result["realized_savings"]["status"] == "not_verified"
    assert result["realized_savings"]["amount_usd"] is None
    assert result["cloud_spend"]["amount"] == 1000.0
    assert result["cloud_spend"]["scope"] == "account_level_context_only"


def test_opportunities_include_actionable_details_and_sort_evidenced_first(artifacts: dict) -> None:
    result = build_opportunities(artifacts)
    assert result["count"] == 3
    assert result["items"][0]["resource_id"] == "i-123"
    assert result["items"][0]["recommendation"]["optimization_confidence"] == "high"
    assert result["items"][2]["savings"]["classification"] == "not_estimable_from_available_evidence"


def test_assets_preserve_null_telemetry_and_cost_evidence(artifacts: dict) -> None:
    result = build_assets(artifacts)
    assert result["count"] == 3
    assert result["items"][2]["utilization"]["avg_memory_percent"] is None
    assert result["items"][2]["cost"]["status"] == "cost_unavailable"


def test_scan_history_and_detail(artifacts: dict) -> None:
    scans = build_scans(artifacts)
    assert scans["count"] == 2
    assert scans["items"][-1]["run_id"] == "run-current"
    detail = build_scan_detail(artifacts, "run-old")
    assert detail is not None
    assert detail["run_id"] == "run-old"
    assert build_scan_detail(artifacts, "missing") is None


def test_load_artifacts_requires_cost_evidence(tmp_path: Path) -> None:
    with pytest.raises(DashboardDataError, match="cost_evidence.json"):
        load_artifacts(tmp_path)


def test_load_artifacts_reads_existing_artifact_names(tmp_path: Path) -> None:
    (tmp_path / "cost_evidence.json").write_text(json.dumps({"run_id": "r", "resources": []}), encoding="utf-8")
    (tmp_path / "proposal.json").write_text(json.dumps({"proposals": []}), encoding="utf-8")
    (tmp_path / "billing.json").write_text(json.dumps({"status": "available"}), encoding="utf-8")
    (tmp_path / "cost_history.json").write_text(json.dumps({"runs": []}), encoding="utf-8")
    result = load_artifacts(tmp_path)
    assert result["evidence"]["run_id"] == "r"
    assert result["history"]["runs"] == []


def test_empty_inventory_status_is_visible_without_stale_costs(tmp_path):
    import json
    from src.utils.dashboard_data import load_artifacts, build_overview, build_scans

    (tmp_path / "scan_status.json").write_text(json.dumps({
        "schema_version": 1,
        "run_id": "no-resources-1",
        "status": "empty_inventory",
        "scanned_at": "2026-11-23T00:00:00Z",
        "warnings": ["No running EC2 or RDS instances were discovered."],
        "recommendations": 0,
        "estimated_monthly_savings_usd": 0,
    }))
    # Prior artifacts must not bleed into an empty-inventory result.
    (tmp_path / "cost_evidence.json").write_text(json.dumps({
        "run_id": "old-run", "resources": [{"resource_id": "stale"}],
    }))
    artifacts = load_artifacts(tmp_path)
    assert artifacts["evidence"]["run_id"] == "no-resources-1"
    assert artifacts["evidence"]["resources"] == []
    assert artifacts["evidence"]["scan_provenance"]["status"] == "empty_inventory"
    assert build_scans(artifacts)["items"][0]["resource_count"] == 0
    assert build_overview(artifacts)["resources_scanned"] == 0
