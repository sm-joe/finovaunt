from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

import src.agent as agent_module
from src.utils.guardrails import ResourceMetric


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "FinOps Integration Test",
        "GIT_AUTHOR_EMAIL": "finops-integration@example.invalid",
        "GIT_COMMITTER_NAME": "FinOps Integration Test",
        "GIT_COMMITTER_EMAIL": "finops-integration@example.invalid",
        "GIT_TERMINAL_PROMPT": "0",
    }
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    init = subprocess.run(
        ["git", "init", "-b", "main"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if init.returncode != 0:
        subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
        assert _git(repo, "checkout", "-b", "main").returncode == 0

    (repo / "README.md").write_text("baseline\n", encoding="utf-8")
    assert _git(repo, "add", "--all").returncode == 0
    assert _git(repo, "commit", "-m", "initial commit").returncode == 0
    assert _git(repo, "status", "--porcelain").stdout.strip() == ""
    return repo


def _configure(
    monkeypatch: pytest.MonkeyPatch,
    repo: Path,
    *,
    discovery_mode: str = "mock",
) -> str:
    monkeypatch.setenv("FINOPS_DISCOVERY_MODE", discovery_mode)
    monkeypatch.setenv("FINOPS_GIT_REPO", str(repo))
    monkeypatch.setenv("FINOPS_OUTPUT_DIR", "artifacts")
    monkeypatch.setenv("FINOPS_GIT_BRANCH_PREFIX", "finops/integration")
    monkeypatch.setenv("FINOPS_GIT_AUTHOR_NAME", "FinOps Integration Test")
    monkeypatch.setenv(
        "FINOPS_GIT_AUTHOR_EMAIL", "finops-integration@example.invalid"
    )
    return "finops/integration/workflow-integration"


def _metric() -> ResourceMetric:
    return ResourceMetric(
        provider="aws",
        resource_id="aws:ec2:us-east-1:i-integration-test",
        resource_type="compute",
        name="integration-worker",
        region="us-east-1",
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


def _patch_workflow_prerequisites(
    monkeypatch: pytest.MonkeyPatch,
    *,
    approval_response: str,
) -> None:
    monkeypatch.setattr(
        agent_module,
        "collect_mock_metrics",
        lambda: [_metric()],
    )
    monkeypatch.setattr(
        agent_module,
        "validate_hcl_locally",
        lambda hcl: hcl.rstrip() + "\n",
    )
    monkeypatch.setattr("builtins.input", lambda _prompt: approval_response)


def test_full_workflow_approval_writes_auditable_artifacts_and_local_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _init_repo(tmp_path)
    branch = _configure(monkeypatch, repo)
    _patch_workflow_prerequisites(monkeypatch, approval_response="approve")

    # Build after monkeypatching so the graph uses the controlled test functions.
    graph = agent_module.build_graph()
    result = graph.invoke({"run_id": "workflow-integration"})

    assert result["status"] == "branch_committed"
    assert result["approved"] is True
    assert result["git_branch"] == branch
    assert _git(repo, "branch", "--show-current").stdout.strip() == branch
    assert _git(repo, "status", "--porcelain").stdout.strip() == ""
    assert _git(repo, "log", "-1", "--format=%s").stdout.strip() == (
        "chore(finops): proposal workflow-integration"
    )

    artifacts = repo / "artifacts"
    manifest = json.loads((artifacts / "manifest.json").read_text(encoding="utf-8"))
    assert set(manifest["files"]) == {
        "audit.json",
        "billing.json",
        "main.tf",
        "proposal.json",
    }
    for name, digest in manifest["files"].items():
        assert hashlib.sha256((artifacts / name).read_bytes()).hexdigest() == digest

    proposals = json.loads(
        (artifacts / "proposal.json").read_text(encoding="utf-8")
    )["proposals"]
    assert len(proposals) == 1
    assert proposals[0]["savings_basis"] == "simulated_estimate"
    assert proposals[0]["estimated_monthly_savings_usd"] == 30
    assert "requires-human-review" in (artifacts / "main.tf").read_text(
        encoding="utf-8"
    )


def test_full_workflow_rejection_creates_no_branch_or_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _init_repo(tmp_path)
    branch = _configure(monkeypatch, repo)
    _patch_workflow_prerequisites(monkeypatch, approval_response="reject")

    graph = agent_module.build_graph()
    result = graph.invoke({"run_id": "workflow-integration"})

    assert result["status"] == "rejected"
    assert result["approved"] is False
    assert _git(repo, "branch", "--show-current").stdout.strip() == "main"
    assert _git(repo, "branch", "--list", branch).stdout.strip() == ""
    assert not (repo / "artifacts").exists()
    assert _git(repo, "status", "--porcelain").stdout.strip() == ""


def test_live_collection_failure_stops_before_approval_and_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _init_repo(tmp_path)
    branch = _configure(monkeypatch, repo, discovery_mode="aws")

    def fail_live_collection():
        raise RuntimeError("injected AWS metrics failure")

    def approval_must_not_run(_state):
        pytest.fail("approval must not run after live collection failure")

    monkeypatch.setattr(agent_module, "collect_aws_metrics", fail_live_collection)
    monkeypatch.setattr(agent_module, "approval", approval_must_not_run)
    graph = agent_module.build_graph()
    result = graph.invoke({"run_id": "workflow-integration"})

    assert result["status"] == "collection_failed"
    assert result["metrics"] == []
    assert "AWS metrics collection failed" in result["validation_error"]
    assert _git(repo, "branch", "--show-current").stdout.strip() == "main"
    assert _git(repo, "branch", "--list", branch).stdout.strip() == ""
    assert not (repo / "artifacts").exists()
    assert _git(repo, "status", "--porcelain").stdout.strip() == ""
