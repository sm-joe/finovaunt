"""Safety tests for the Autonomous FinOps agent workflow."""

import hashlib
import json
import subprocess

import pytest

import src.agent as agent_module
from src.agent import (
    _write_artifacts,
    reject,
    route_approval,
    route_assessment,
    route_collection,
    write_branch,
)


def test_collection_failure_routes_to_reject() -> None:
    state = {
        "status": "collection_failed",
        "validation_error": "No usable resource telemetry",
    }

    assert route_collection(state) == "reject"


def test_successful_collection_routes_to_optimization() -> None:
    state = {
        "status": "data_collected",
        "metrics": [],
    }

    assert route_collection(state) == "optimize"


def test_validation_failure_routes_to_reject() -> None:
    state = {
        "status": "validation_failed",
        "validation_error": "Terraform validation failed",
    }

    assert route_assessment(state) == "reject"


def test_successful_assessment_routes_to_approval() -> None:
    state = {
        "status": "ready_for_approval",
        "risk_summary": [],
    }

    assert route_assessment(state) == "approval"


def test_only_approved_state_routes_to_write() -> None:
    assert route_approval({"approved": True}) == "write"
    assert route_approval({"approved": False}) == "reject"
    assert route_approval({}) == "reject"


def test_collection_failure_is_preserved_by_reject() -> None:
    result = reject(
        {
            "status": "collection_failed",
            "events": [],
        }
    )

    assert result["status"] == "collection_failed"


def test_validation_failure_is_preserved_by_reject() -> None:
    result = reject(
        {
            "status": "validation_failed",
            "validation_error": "Invalid Terraform",
            "events": [],
        }
    )

    assert result["status"] == "validation_failed"


def test_human_rejection_stops_without_writing_artifacts() -> None:
    result = reject(
        {
            "status": "rejected",
            "events": [],
        }
    )

    assert result["status"] == "rejected"
    assert any(
        "without writing artifacts" in event
        for event in result["events"]
    )


def test_artifact_writer_creates_local_proposal_files(
    tmp_path,
) -> None:
    state = {
        "run_id": "test-run-001",
        "proposals": [
            {
                "resource_id": "test-resource",
                "action": "review_only",
                "estimated_monthly_savings_usd": 0,
            }
        ],
        "risk_summary": ["Human review required"],
        "generated_hcl": (
            "# Proposal metadata only; no cloud changes.\n"
        ),
        "events": ["Test workflow"],
        "billing_summary": {
            "status": "available",
            "total_cost": 15.2449304707,
            "currency": "USD",
        },
    }

    _write_artifacts(tmp_path, state)

    proposal_path = tmp_path / "proposal.json"
    terraform_path = tmp_path / "main.tf"
    audit_path = tmp_path / "audit.json"
    billing_path = tmp_path / "billing.json"

    assert proposal_path.is_file()
    assert terraform_path.is_file()
    assert audit_path.is_file()
    assert billing_path.is_file()

    proposal = json.loads(
        proposal_path.read_text(encoding="utf-8")
    )
    audit = json.loads(
        audit_path.read_text(encoding="utf-8")
    )
    billing = json.loads(
        billing_path.read_text(encoding="utf-8")
    )

    assert proposal["run_id"] == "test-run-001"
    assert len(proposal["proposals"]) == 1
    assert "Human review required" in proposal["risk_summary"]

    assert "Test workflow" in audit["events"]

    assert billing["status"] == "available"
    assert billing["currency"] == "USD"
    assert billing["total_cost"] == 15.2449304707

    assert "no cloud changes" in terraform_path.read_text(
        encoding="utf-8"
    )


def test_write_branch_blocks_unapproved_state(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("FINOPS_GIT_REPO", str(tmp_path))
    monkeypatch.setenv("FINOPS_OUTPUT_DIR", "artifacts")

    result = write_branch(
        {
            "run_id": "unapproved-test",
            "approved": False,
            "events": [],
        }
    )

    assert result["status"] == "write_blocked"
    assert any(
        "approval is missing" in event
        for event in result["events"]
    )
    assert not (tmp_path / "artifacts").exists()


def test_write_branch_rolls_back_when_artifact_generation_fails(
    tmp_path,
    monkeypatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    def run_git(*args: str) -> None:
        subprocess.run(
            ["git", *args],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
        )

    run_git("init", "-b", "main")
    run_git("config", "user.name", "FinOps Test")
    run_git("config", "user.email", "finops-test@example.invalid")

    (repo / ".gitignore").write_text(
        "artifacts/\n",
        encoding="utf-8",
    )
    (repo / "README.md").write_text(
        "baseline\n",
        encoding="utf-8",
    )

    run_git("add", ".gitignore", "README.md")
    run_git("commit", "-m", "test: baseline")

    artifacts = repo / "artifacts"
    artifacts.mkdir()
    (artifacts / "previous.txt").write_text(
        "preserve this file\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("FINOPS_GIT_REPO", str(repo))
    monkeypatch.setenv("FINOPS_OUTPUT_DIR", "artifacts")
    monkeypatch.setenv(
        "FINOPS_GIT_BRANCH_PREFIX",
        "finops/optimization",
    )

    def fail_after_writing(output_path, state):
        output_path.mkdir(parents=True, exist_ok=True)
        (output_path / "partial.txt").write_text(
            "partial output\n",
            encoding="utf-8",
        )
        raise OSError("simulated artifact failure")

    monkeypatch.setattr(
        agent_module,
        "_write_artifacts",
        fail_after_writing,
    )

    result = write_branch(
        {
            "run_id": "rollback-test",
            "approved": True,
            "events": [],
        }
    )

    assert result["status"] == "write_failed"

    assert (artifacts / "previous.txt").read_text(
        encoding="utf-8"
    ) == "preserve this file\n"

    assert not (artifacts / "partial.txt").exists()

    current = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    assert current.stdout.strip() == "main"

    branch = subprocess.run(
        [
            "git",
            "branch",
            "--list",
            "finops/optimization/rollback-test",
        ],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    assert not branch.stdout.strip()

    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    assert not status.stdout.strip()


@pytest.mark.parametrize("failed_command", ["add", "commit"])
def test_write_branch_rolls_back_on_git_failure(
    tmp_path,
    monkeypatch,
    failed_command,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    real_run = subprocess.run

    def run_git(*args: str) -> None:
        real_run(
            ["git", *args],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
        )

    run_git("init", "-b", "main")
    run_git("config", "user.name", "FinOps Test")
    run_git("config", "user.email", "finops-test@example.invalid")

    (repo / "README.md").write_text(
        "baseline\n",
        encoding="utf-8",
    )
    run_git("add", "README.md")
    run_git("commit", "-m", "test: baseline")

    monkeypatch.setenv("FINOPS_GIT_REPO", str(repo))
    monkeypatch.setenv("FINOPS_OUTPUT_DIR", "artifacts")
    monkeypatch.setenv(
        "FINOPS_GIT_BRANCH_PREFIX",
        "finops/optimization",
    )

    def fail_selected_git_command(args, **kwargs):
        if (
            len(args) >= 2
            and args[0] == "git"
            and args[1] == failed_command
        ):
            return subprocess.CompletedProcess(
                args,
                1,
                stdout="",
                stderr=f"simulated git {failed_command} failure",
            )

        return real_run(args, **kwargs)

    monkeypatch.setattr(
        agent_module.subprocess,
        "run",
        fail_selected_git_command,
    )

    result = agent_module.write_branch(
        {
            "run_id": f"failure-{failed_command}",
            "approved": True,
            "generated_hcl": "# test proposal\n",
            "proposals": [],
            "risk_summary": [],
            "events": [],
        }
    )

    assert result["status"] == "write_failed"
    assert not (repo / "artifacts").exists()

    current = real_run(
        ["git", "branch", "--show-current"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    assert current.stdout.strip() == "main"

    branches = real_run(
        [
            "git",
            "branch",
            "--list",
            f"finops/optimization/failure-{failed_command}",
        ],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    assert not branches.stdout.strip()

    status = real_run(
        ["git", "status", "--porcelain"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    assert not status.stdout.strip()


def test_write_artifacts_creates_sha256_manifest(
    tmp_path,
) -> None:
    _write_artifacts(
        tmp_path,
        {
            "run_id": "manifest-test",
            "proposals": [],
            "risk_summary": [],
            "generated_hcl": "# review only\n",
            "events": [],
        },
    )

    manifest_path = tmp_path / "manifest.json"
    assert manifest_path.is_file()

    manifest = json.loads(
        manifest_path.read_text(encoding="utf-8")
    )

    assert manifest["run_id"] == "manifest-test"
    assert manifest["algorithm"] == "sha256"

    for filename, expected_hash in manifest["files"].items():
        actual_hash = hashlib.sha256(
            (tmp_path / filename).read_bytes()
        ).hexdigest()

        assert actual_hash == expected_hash

    assert "manifest.json" not in manifest["files"]
    assert "proposal.json" in manifest["files"]
    assert "main.tf" in manifest["files"]
    assert "audit.json" in manifest["files"]