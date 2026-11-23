"""Focused tests for validating downloaded read-only scan artifacts."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import zipfile

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "scan_artifact_sync.py"
spec = importlib.util.spec_from_file_location("scan_artifact_sync", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)


def _archive(tamper_hash: bool = False) -> bytes:
    evidence = json.dumps({"run_id": "scan-123", "resources": []}).encode()
    billing = json.dumps({"status": "available"}).encode()
    files = {"cost_evidence.json": evidence, "billing.json": billing}
    hashes = {name: hashlib.sha256(value).hexdigest() for name, value in files.items()}
    if tamper_hash:
        hashes["billing.json"] = "0" * 64
    files["manifest.json"] = json.dumps({"run_id": "scan-123", "algorithm": "sha256", "files": hashes}).encode()
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, value in files.items():
            archive.writestr(name, value)
    return stream.getvalue()


def test_validates_known_scan_artifact_files():
    files = module._validated_files(_archive())
    assert "cost_evidence.json" in files
    assert json.loads(files["cost_evidence.json"]) ["run_id"] == "scan-123"


def test_rejects_hash_mismatch():
    try:
        module._validated_files(_archive(tamper_hash=True))
    except module.SyncError as exc:
        assert "hash validation failed" in str(exc)
    else:
        raise AssertionError("Expected invalid artifact hash to be rejected")


def test_same_run_marker_does_not_skip_sync_when_evidence_is_missing(tmp_path, monkeypatch):
    """A stale marker must not prevent recovery of a deleted local snapshot."""
    run_id = 987654
    marker = {
        "github_run_id": run_id,
        "github_run_url": "https://github.com/sm-joe/finovaunt/actions/runs/987654",
        "scan_run_id": "scan-123",
        "synced_at": "2026-10-11T00:00:00Z",
    }
    (tmp_path / ".finovaunt-sync.json").write_text(json.dumps(marker), encoding="utf-8")
    archive = _archive()

    def fake_json_request(url, token):
        if url.endswith("/actions/workflows/finovaunt-scan.yml/runs?status=success&per_page=10"):
            return {"workflow_runs": [{"id": run_id, "html_url": marker["github_run_url"]}]}
        if url.endswith(f"/actions/runs/{run_id}/artifacts?per_page=100"):
            return {"artifacts": [{"id": 456, "name": "finovaunt-scan", "expired": False}]}
        raise AssertionError(f"Unexpected API URL: {url}")

    monkeypatch.setattr(module, "_json_request", fake_json_request)
    monkeypatch.setattr(module, "_request", lambda url, token, accept="application/vnd.github+json": archive)

    result = module.sync_latest_scan(
        tmp_path,
        token="test-token",
        repository="sm-joe/finovaunt",
        workflow="finovaunt-scan.yml",
    )

    assert result["status"] == "synced"
    assert (tmp_path / "cost_evidence.json").is_file()
    assert json.loads((tmp_path / "cost_evidence.json").read_text(encoding="utf-8"))["run_id"] == "scan-123"


def test_empty_inventory_artifact_replaces_stale_scan_evidence(tmp_path, monkeypatch):
    old = tmp_path / "cost_evidence.json"
    old.write_text(json.dumps({"run_id": "old", "resources": [{"resource_id": "old-resource"}]}))
    record = {
        "schema_version": 1,
        "run_id": "empty-123",
        "status": "empty_inventory",
        "scanned_at": "2026-11-23T00:00:00Z",
        "recommendations": 0,
        "estimated_monthly_savings_usd": 0,
        "warnings": ["No running EC2 or RDS instances were discovered."],
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("scan_status.json", json.dumps(record))
    content = buffer.getvalue()

    def fake_json_request(url, token):
        if "/actions/workflows/" in url:
            return {"workflow_runs": [{"id": 1234, "html_url": "https://github.com/sm-joe/finovaunt/actions/runs/1234"}]}
        if url.endswith("/actions/runs/1234/artifacts?per_page=100"):
            return {"artifacts": [{"id": 1235, "name": "finovaunt-scan", "expired": False}]}
        raise AssertionError(url)

    monkeypatch.setattr(module, "_json_request", fake_json_request)
    monkeypatch.setattr(module, "_request", lambda *args, **kwargs: content)
    result = module.sync_latest_scan(
        tmp_path, token="test-token", repository="sm-joe/finovaunt", workflow="finovaunt-scan.yml"
    )
    assert result["scan_status"] == "empty_inventory"
    assert json.loads((tmp_path / "scan_status.json").read_text())["run_id"] == "empty-123"
    assert not old.exists()
    assert json.loads((tmp_path / ".finovaunt-sync.json").read_text())["scan_run_id"] == "empty-123"


def test_rejects_invalid_empty_inventory_artifact():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("scan_status.json", json.dumps({
            "schema_version": 1, "run_id": "invalid", "status": "empty_inventory",
            "recommendations": 1, "estimated_monthly_savings_usd": 999,
        }))
    try:
        module._validated_files(buffer.getvalue())
    except module.SyncError:
        pass
    else:
        raise AssertionError("An empty scan must never contain invented savings")
