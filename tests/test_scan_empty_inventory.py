"""Regression coverage for safe no-op scans and collector failures."""
import json

import scripts.run_readonly_scan as scan


def test_empty_aws_inventory_is_reported_without_fabricating_recommendations(tmp_path, monkeypatch):
    monkeypatch.setattr(scan, "ROOT", tmp_path)
    monkeypatch.setenv("FINOPS_OUTPUT_DIR", "test-output")
    monkeypatch.setenv("FINOPS_DISCOVERY_MODE", "aws")
    monkeypatch.setattr(scan, "collect_data", lambda state: {
        "status": "collection_failed",
        "metrics": [],
        "collection_warnings": ["No running EC2 or RDS instances were discovered in eu-central-1."],
        "events": [],
        "validation_error": "No CPU telemetry",
    })
    assert scan.main() == 0
    output = tmp_path / "test-output"
    status = json.loads((output / "scan_status.json").read_text())
    assert status["status"] == "empty_inventory"
    assert status["estimated_monthly_savings_usd"] == 0
    assert not (output / "proposal.json").exists()
    assert not (output / "main.tf").exists()


def test_missing_cpu_telemetry_is_not_misreported_as_empty_inventory(tmp_path, monkeypatch):
    monkeypatch.setattr(scan, "ROOT", tmp_path)
    monkeypatch.setenv("FINOPS_OUTPUT_DIR", "test-output")
    monkeypatch.setenv("FINOPS_DISCOVERY_MODE", "aws")
    monkeypatch.setattr(scan, "collect_data", lambda state: {
        "status": "collection_failed",
        "metrics": [],
        "collection_warnings": ["Running EC2 instance excluded: no usable CPU metrics."],
        "events": [],
        "validation_error": "No CPU telemetry",
    })
    assert scan.main() == 1
    assert not (tmp_path / "test-output" / "scan_status.json").exists()
