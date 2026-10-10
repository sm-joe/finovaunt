from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

import src.agent as agent_module


def _run_git(repo: Path, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    git_env = os.environ.copy()
    git_env.update(
        {
            "GIT_AUTHOR_NAME": "FinOps Test",
            "GIT_AUTHOR_EMAIL": "finops-test@example.invalid",
            "GIT_COMMITTER_NAME": "FinOps Test",
            "GIT_COMMITTER_EMAIL": "finops-test@example.invalid",
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    if env:
        git_env.update(env)
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
        env=git_env,
    )


def _git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()

    initialized = subprocess.run(
        ["git", "init", "-b", "main"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if initialized.returncode != 0:
        # Compatibility with older Git versions that do not support `init -b`.
        subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
        _run_git(repo, "checkout", "-b", "main")

    (repo / "README.md").write_text("baseline\n", encoding="utf-8")
    output = repo / "artifacts"
    output.mkdir()
    (output / "keep.txt").write_text("preserve this artifact\n", encoding="utf-8")

    assert _run_git(repo, "add", "--all").returncode == 0
    assert _run_git(repo, "commit", "-m", "initial commit").returncode == 0
    assert _run_git(repo, "status", "--porcelain").stdout.strip() == ""
    return repo


def _state() -> dict:
    return {
        "run_id": "rollback-regression",
        "approved": True,
        "approval_reason": "test approval",
        "proposals": [{"resource_id": "i-test", "action": "review_only"}],
        "generated_hcl": "# test proposal\n",
        "risk_summary": [],
        "billing_summary": {"status": "unavailable"},
        "events": [],
    }


def _configure(monkeypatch: pytest.MonkeyPatch, repo: Path) -> str:
    monkeypatch.setenv("FINOPS_GIT_REPO", str(repo))
    monkeypatch.setenv("FINOPS_OUTPUT_DIR", "artifacts")
    monkeypatch.setenv("FINOPS_GIT_BRANCH_PREFIX", "finops/test")
    monkeypatch.setenv("FINOPS_GIT_AUTHOR_NAME", "FinOps Test")
    monkeypatch.setenv("FINOPS_GIT_AUTHOR_EMAIL", "finops-test@example.invalid")
    return "finops/test/rollback-regression"


def _inject_failure(
    monkeypatch: pytest.MonkeyPatch,
    failing_command: str,
) -> None:
    real_run = agent_module.subprocess.run
    injected = False

    def run_with_one_failure(*args, **kwargs):
        nonlocal injected
        command = args[0] if args else kwargs.get("args", [])
        if (
            not injected
            and isinstance(command, (list, tuple))
            and len(command) >= 2
            and command[0] == "git"
            and command[1] == failing_command
        ):
            injected = True
            return subprocess.CompletedProcess(
                args=command,
                returncode=1,
                stdout="",
                stderr=f"injected {failing_command} failure",
            )
        return real_run(*args, **kwargs)

    monkeypatch.setattr(agent_module.subprocess, "run", run_with_one_failure)


def _assert_rolled_back(repo: Path, branch: str) -> None:
    current = _run_git(repo, "branch", "--show-current")
    assert current.returncode == 0
    assert current.stdout.strip() == "main"

    branch_lookup = _run_git(repo, "branch", "--list", branch)
    assert branch_lookup.returncode == 0
    assert branch_lookup.stdout.strip() == ""

    status = _run_git(repo, "status", "--porcelain")
    assert status.returncode == 0
    assert status.stdout.strip() == ""

    output = repo / "artifacts"
    assert (output / "keep.txt").read_text(encoding="utf-8") == "preserve this artifact\n"
    assert not (output / "proposal.json").exists()
    assert not (output / "manifest.json").exists()


@pytest.mark.parametrize("failing_command", ["add", "commit"])
def test_git_add_or_commit_failure_rolls_back_branch_and_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failing_command: str,
) -> None:
    repo = _git_repo(tmp_path)
    branch = _configure(monkeypatch, repo)
    _inject_failure(monkeypatch, failing_command)

    result = agent_module.write_branch(_state())

    assert result["status"] == "write_failed"
    assert any("rollback completed" in event.lower() for event in result["events"])
    _assert_rolled_back(repo, branch)
