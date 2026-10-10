
"""LangGraph FinOps workflow: collect, optimize, assess, approve, branch."""

import json
import os
import re
import subprocess
import uuid
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from src.tools.cloud_metrics import (
    collect_aws_metrics,
    collect_mock_metrics,
)
from src.utils.guardrails import (
    OptimizationProposal,
    ResourceMetric,
    scrub_sensitive_text,
    validate_hcl_locally,
)


class AgentState(TypedDict, total=False):
    """Serializable workflow state. Never store credentials here."""

    run_id: str
    metrics: list[dict[str, Any]]
    proposals: list[dict[str, Any]]
    generated_hcl: str
    validation_error: str
    risk_summary: list[str]
    approved: bool
    approval_reason: str
    output_path: str
    git_branch: str
    status: str
    events: list[str]


def _event(state: AgentState, message: str) -> list[str]:
    """Append a sanitized event to the workflow history."""
    return [
        *state.get("events", []),
        scrub_sensitive_text(message),
    ]


def collect_data(state: AgentState) -> AgentState:
    """Collect mock or live AWS metrics according to configuration."""
    run_id = state.get("run_id") or uuid.uuid4().hex[:12]
    mode = os.getenv("FINOPS_DISCOVERY_MODE", "mock").strip().lower()

    if mode == "mock":
        metrics = collect_mock_metrics()
        warnings: list[str] = []

    elif mode == "aws":
        try:
            metrics, warnings = collect_aws_metrics()
        except Exception as exc:
            # Fail closed: collection errors must not reach optimization.
            safe_error = scrub_sensitive_text(str(exc))
            return {
                "run_id": run_id,
                "metrics": [],
                "validation_error": (
                    f"AWS collection failed: {safe_error}"
                ),
                "events": _event(
                    state,
                    "AWS collection failed; optimization blocked",
                ),
                "status": "collection_failed",
            }

    else:
        return {
            "run_id": run_id,
            "metrics": [],
            "validation_error": (
                "Unsupported FINOPS_DISCOVERY_MODE. "
                "Allowed values are 'mock' and 'aws'."
            ),
            "events": _event(
                state,
                "Unsupported discovery mode; workflow stopped",
            ),
            "status": "collection_failed",
        }

    events = _event(
        state,
        f"Collected {len(metrics)} {mode} metrics",
    )
    events.extend(
        scrub_sensitive_text(warning)
        for warning in warnings
    )

    # Do not produce recommendations from an empty live scan.
    if mode == "aws" and not metrics:
        return {
            "run_id": run_id,
            "metrics": [],
            "validation_error": (
                "AWS discovery returned no resources with usable CPU "
                "telemetry. Optimization and artifact writing were blocked."
            ),
            "events": events,
            "status": "collection_failed",
        }

    return {
        "run_id": run_id,
        "metrics": [
            metric.model_dump(mode="json")
            for metric in metrics
        ],
        "events": events,
        "status": "data_collected",
    }


def optimize(state: AgentState) -> AgentState:
    """Generate conservative, deterministic optimization proposals."""
    proposals: list[dict[str, Any]] = []

    for raw_metric in state.get("metrics", []):
        metric = ResourceMetric.model_validate(raw_metric)

        eligible = (
            metric.resource_type == "compute"
            and metric.environment in {"dev", "test"}
            and metric.avg_cpu_percent < 10
            and metric.peak_cpu_percent < 35
            and not metric.production_critical
        )

        if eligible and metric.monthly_cost_usd <= 0:
            # Live discovery currently has no billing integration.
            # Never manufacture a dollar savings estimate.
            proposal = OptimizationProposal(
                resource_id=metric.resource_id,
                provider=metric.provider,
                action="review_only",
                rationale=(
                    f"Non-production compute averages "
                    f"{metric.avg_cpu_percent:.1f}% CPU and peaks at "
                    f"{metric.peak_cpu_percent:.1f}%. Billing data is "
                    "unavailable, so savings cannot be estimated. "
                    "Review utilization and actual costs before resizing."
                ),
                estimated_monthly_savings_usd=0,
                risk="medium",
            )

        elif eligible:
            # This estimate is only as reliable as the supplied cost data.
            proposal = OptimizationProposal(
                resource_id=metric.resource_id,
                provider=metric.provider,
                action="rightsize",
                rationale=(
                    f"Non-production compute averages "
                    f"{metric.avg_cpu_percent:.1f}% CPU and peaks at "
                    f"{metric.peak_cpu_percent:.1f}%. Review a one-step "
                    "reduction after checking workload requirements."
                ),
                estimated_monthly_savings_usd=round(
                    metric.monthly_cost_usd * 0.30,
                    2,
                ),
                risk="medium",
                proposed_instance_type=(
                    "smaller-compatible-size; verify provider catalog"
                ),
            )

        else:
            hot = (
                metric.peak_cpu_percent >= 80
                or metric.production_critical
            )

            proposal = OptimizationProposal(
                resource_id=metric.resource_id,
                provider=metric.provider,
                action="no_change" if hot else "review_only",
                rationale=(
                    f"Peak CPU is {metric.peak_cpu_percent:.1f}%. "
                    "The conservative policy blocks automatic rightsizing."
                ),
                estimated_monthly_savings_usd=0,
                risk="critical" if hot else "high",
            )

        # Important: persist every proposal in the workflow state.
        proposals.append(proposal.model_dump(mode="json"))

    # Valid Terraform metadata only; this does not change cloud resources.
    generated_hcl = """# Proposal metadata only; no cloud changes.
terraform {
  required_version = ">= 1.5.0"
}

output "finops_review" {
  description = "Human review metadata; this proposal does not change cloud resources."
  value = {
    owner  = "platform"
    status = "requires-human-review"
  }
}
"""

    return {
        "proposals": proposals,
        "generated_hcl": generated_hcl,
        "events": _event(
            state,
            f"Generated {len(proposals)} proposals",
        ),
        "status": "optimized",
    }


def assess_risk(state: AgentState) -> AgentState:
    """Assess production risks and validate generated Terraform locally."""
    risks: list[str] = []

    metrics = {
        raw_metric["resource_id"]: ResourceMetric.model_validate(raw_metric)
        for raw_metric in state.get("metrics", [])
    }

    for raw_proposal in state.get("proposals", []):
        proposal = OptimizationProposal.model_validate(raw_proposal)
        metric = metrics.get(proposal.resource_id)

        if metric is None:
            return {
                "validation_error": (
                    "A proposal references a resource absent from the "
                    "collected metrics; artifact writing was blocked."
                ),
                "risk_summary": risks,
                "events": _event(
                    state,
                    "Proposal-to-resource consistency check failed",
                ),
                "status": "validation_failed",
            }

        if metric.environment == "prod" or metric.production_critical:
            risks.append(
                f"{proposal.resource_id}: production requires review"
            )

        if proposal.risk in {"high", "critical"}:
            risks.append(
                f"{proposal.resource_id}: {proposal.risk} risk"
            )

    try:
        validated_hcl = validate_hcl_locally(
            state.get("generated_hcl", "")
        )
    except (
        ValueError,
        RuntimeError,
        subprocess.TimeoutExpired,
    ) as exc:
        return {
            "validation_error": scrub_sensitive_text(str(exc)),
            "risk_summary": risks + [
                "HCL validation failed; branch writing blocked"
            ],
            "events": _event(state, "HCL validation failed"),
            "status": "validation_failed",
        }

    return {
        "generated_hcl": validated_hcl,
        "risk_summary": risks,
        "events": _event(
            state,
            f"Risk assessment complete: {len(risks)} flags",
        ),
        "status": "ready_for_approval",
    }


def route_assessment(state: AgentState) -> str:
    """Route failed validation directly to the rejection node."""
    return (
        "reject"
        if state.get("validation_error")
        else "approval"
    )


def route_collection(state: AgentState) -> str:
    """Do not optimize when collection has failed."""
    return (
        "reject"
        if state.get("validation_error")
        else "optimize"
    )


def approval(state: AgentState) -> AgentState:
    """Require explicit interactive approval before local Git operations."""
    print("\n=== Human approval gate ===")

    total_savings = sum(
        proposal["estimated_monthly_savings_usd"]
        for proposal in state.get("proposals", [])
    )

    print(
        f"Run {state.get('run_id')} | "
        f"estimated savings ${total_savings:.2f}/month"
    )

    for proposal in state.get("proposals", []):
        print(
            f"- {proposal['provider']} "
            f"{proposal['resource_id']}: "
            f"{proposal['action']} "
            f"({proposal['risk']}; "
            f"${proposal['estimated_monthly_savings_usd']:.2f}/mo)"
        )

    for risk in state.get("risk_summary", []):
        print(f"REVIEW: {risk}")

    try:
        answer = input(
            "Type 'approve' to create the local proposal branch; "
            "anything else rejects: "
        ).strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = "reject"

    approved = answer == "approve"

    return {
        "approved": approved,
        "approval_reason": (
            "interactive approval" if approved else "not approved"
        ),
        "status": "approved" if approved else "rejected",
    }


def route_approval(state: AgentState) -> str:
    """Only an explicit approval can reach the artifact writer."""
    return "write" if state.get("approved") else "reject"


def _write_artifacts(directory: Path, state: AgentState) -> None:
    """Write the proposal, Terraform metadata, and audit trail."""
    directory.mkdir(parents=True, exist_ok=True)

    proposal_document = {
        "run_id": state.get("run_id"),
        "proposals": state.get("proposals", []),
        "risk_summary": state.get("risk_summary", []),
    }

    audit_document = {
        "events": state.get("events", []),
    }

    (directory / "proposal.json").write_text(
        json.dumps(proposal_document, indent=2) + "\n",
        encoding="utf-8",
    )

    (directory / "main.tf").write_text(
        state.get("generated_hcl", ""),
        encoding="utf-8",
    )

    (directory / "audit.json").write_text(
        json.dumps(audit_document, indent=2) + "\n",
        encoding="utf-8",
    )


def write_branch(state: AgentState) -> AgentState:
    """Write artifacts and commit locally; never push or mutate cloud resources."""
    repo = Path(os.getenv("FINOPS_GIT_REPO", ".")).resolve()
    output_name = os.getenv("FINOPS_OUTPUT_DIR", "artifacts")

    # Keep artifacts at a simple path within the repository.
    if not re.fullmatch(r"[A-Za-z0-9_-]+", output_name):
        return {
            "status": "write_blocked",
            "events": _event(state, "Invalid output directory"),
        }

    def git(*args: str, env: dict[str, str] | None = None):
        git_env = {
            **os.environ,
            "GIT_TERMINAL_PROMPT": "0",
        }
        if env:
            git_env.update(env)

        return subprocess.run(
            ["git", *args],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=30,
            shell=False,
            check=False,
            env=git_env,
        )

    if not (repo / ".git").exists():
        output_path = Path(output_name).resolve()
        _write_artifacts(output_path, state)

        return {
            "output_path": str(output_path),
            "status": "artifacts_written",
            "events": _event(
                state,
                "Local artifacts written; no Git repository found",
            ),
        }

    dirty_result = git("status", "--porcelain")

    if dirty_result.returncode != 0 or dirty_result.stdout.strip():
        return {
            "status": "write_blocked",
            "events": _event(
                state,
                "Repository must be clean before branch operation",
            ),
        }

    prefix = re.sub(
        r"[^A-Za-z0-9/_-]",
        "-",
        os.getenv(
            "FINOPS_GIT_BRANCH_PREFIX",
            "finops/optimization",
        ),
    ).strip("/")

    if not prefix:
        return {
            "status": "write_blocked",
            "events": _event(
                state,
                "Invalid Git branch prefix",
            ),
        }

    branch = f"{prefix}/{state['run_id']}"

    current_branch = git("branch", "--show-current")

    if current_branch.returncode != 0 or not current_branch.stdout.strip():
        return {
            "status": "write_blocked",
            "events": _event(
                state,
                "Cannot determine current Git branch",
            ),
        }

    switch_result = git("switch", "-c", branch)

    if switch_result.returncode != 0:
        return {
            "status": "write_blocked",
            "events": _event(
                state,
                "Branch creation failed",
            ),
        }

    output_path = repo / output_name

    try:
        _write_artifacts(output_path, state)
    except OSError as exc:
        return {
            "status": "write_blocked",
            "git_branch": branch,
            "events": _event(
                state,
                f"Artifact writing failed: {exc}",
            ),
        }

    add_result = git("add", "--", output_name)

    if add_result.returncode != 0:
        return {
            "status": "write_blocked",
            "git_branch": branch,
            "events": _event(state, "Git add failed"),
        }

    author_name = os.getenv(
        "FINOPS_GIT_AUTHOR_NAME",
        "FinOps Optimization Agent",
    )
    author_email = os.getenv(
        "FINOPS_GIT_AUTHOR_EMAIL",
        "finops-agent@example.invalid",
    )

    commit_env = {
        "GIT_AUTHOR_NAME": author_name,
        "GIT_AUTHOR_EMAIL": author_email,
        "GIT_COMMITTER_NAME": author_name,
        "GIT_COMMITTER_EMAIL": author_email,
    }

    commit_result = git(
        "commit",
        "-m",
        f"chore(finops): proposal {state['run_id']}",
        env=commit_env,
    )

    if commit_result.returncode != 0:
        return {
            "status": "write_blocked",
            "git_branch": branch,
            "events": _event(state, "Git commit failed"),
        }

    return {
        "output_path": str(output_path),
        "git_branch": branch,
        "status": "branch_committed",
        "events": _event(
            state,
            f"Committed {branch}; no remote push",
        ),
    }


def reject(state: AgentState) -> AgentState:
    """Stop safely without writing artifacts after a rejection or failure."""
    if state.get("status") == "collection_failed":
        status = "collection_failed"
    elif state.get("validation_error"):
        status = "validation_failed"
    else:
        status = "rejected"

    return {
        "status": status,
        "events": _event(
            state,
            "Stopped without writing artifacts",
        ),
    }


def build_graph():
    """Construct and compile the FinOps workflow."""
    graph = StateGraph(AgentState)

    nodes = [
        ("collect_data", collect_data),
        ("optimize", optimize),
        ("assess_risk", assess_risk),
        ("approval", approval),
        ("write", write_branch),
        ("reject", reject),
    ]

    for name, function in nodes:
        graph.add_node(name, function)

    graph.add_edge(START, "collect_data")

    graph.add_conditional_edges(
        "collect_data",
        route_collection,
        {
            "optimize": "optimize",
            "reject": "reject",
        },
    )

    graph.add_edge("optimize", "assess_risk")

    graph.add_conditional_edges(
        "assess_risk",
        route_assessment,
        {
            "approval": "approval",
            "reject": "reject",
        },
    )

    graph.add_conditional_edges(
        "approval",
        route_approval,
        {
            "write": "write",
            "reject": "reject",
        },
    )

    graph.add_edge("write", END)
    graph.add_edge("reject", END)

    return graph.compile()


finops_graph = build_graph()
