"""LangGraph FinOps workflow: collect, optimize, assess, approve, branch."""

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from src.tools.aws_costs import (
    collect_aws_cost_summary,
    collect_ec2_resource_costs,
)
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


from src.utils.cost_evidence import build_cost_evidence_report

from src.utils.proposal_history import build_proposal_history

class AgentState(TypedDict, total=False):
    """Serializable workflow state. Never store credentials here."""

    run_id: str
    metrics: list[dict[str, Any]]
    proposals: list[dict[str, Any]]
    generated_hcl: str
    validation_error: str
    risk_summary: list[str]
    billing_summary: dict[str, Any]
    approved: bool
    approval_reason: str
    output_path: str
    git_branch: str
    status: str
    events: list[str]


def _event(state: AgentState, message: str) -> list[str]:
    return [
        *state.get("events", []),
        scrub_sensitive_text(message),
    ]


def _attach_ec2_resource_costs(
    metrics: list[ResourceMetric],
    resource_costs: dict[str, Any],
) -> list[ResourceMetric]:
    """Attach recent costs only when EC2 resource ID and region match exactly.

    The observed 14-day amount is not converted into monthly cost.
    ResourceMetric.monthly_cost_usd remains unchanged.
    """
    if resource_costs.get("status") != "available":
        return metrics

    indexed: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in resource_costs.get("resources", []):
        if not isinstance(item, dict):
            continue
        resource_id = str(item.get("resource_id", "")).strip()
        region = str(item.get("region", "")).strip()
        if resource_id and region:
            indexed.setdefault((resource_id, region), []).append(item)

    for metric in metrics:
        if metric.provider != "aws" or metric.resource_type != "compute":
            continue
        parts = metric.resource_id.split(":", 3)
        if len(parts) != 4 or parts[0] != "aws" or parts[1] != "ec2":
            continue
        region, instance_id = parts[2], parts[3]
        if region != metric.region or not instance_id:
            continue

        matches = indexed.get((instance_id, region), [])
        if len(matches) > 1:
            metric.metadata["cost_status"] = "ambiguous_resource_cost"
            continue
        if not matches:
            continue

        item = matches[0]
        currency = str(item.get("currency", "")).upper()
        try:
            amount = float(item["amount"])
        except (KeyError, TypeError, ValueError):
            metric.metadata["cost_status"] = "invalid_resource_cost"
            continue
        if not (amount >= 0 and amount < float("inf")):
            metric.metadata["cost_status"] = "invalid_resource_cost"
            continue

        metric.metadata["observed_cost_period_amount"] = str(amount)
        metric.metadata["observed_cost_currency"] = currency or "unknown"
        metric.metadata["observed_cost_period_start"] = str(
            resource_costs.get("period_start", "")
        )
        metric.metadata["observed_cost_period_end_exclusive"] = str(
            resource_costs.get("period_end_exclusive", "")
        )
        metric.metadata["cost_source"] = "aws_cost_explorer_resource_id"
        metric.metadata["cost_status"] = (
            "observed_14_day_cost" if currency == "USD"
            else "observed_cost_non_usd"
        )
    return metrics


def collect_data(state: AgentState) -> AgentState:
    """Collect mock or live AWS metrics and a separate billing summary."""
    run_id = state.get("run_id") or uuid.uuid4().hex[:12]
    mode = os.getenv("FINOPS_DISCOVERY_MODE", "mock").strip().lower()

    billing_summary: dict[str, Any] = {
        "status": "not_applicable",
        "reason": "Billing collection is enabled only in AWS discovery mode.",
        "resource_attribution": "not_available",
    }

    if mode == "mock":
        metrics = collect_mock_metrics()
        warnings: list[str] = []

    elif mode == "aws":
        try:
            metrics, warnings = collect_aws_metrics()
        except Exception as exc:  # noqa: BLE001 — return a controlled failure when AWS metrics collection fails.
            return {
                "run_id": run_id,
                "metrics": [],
                "validation_error": (
                    "AWS metrics collection failed: "
                    + scrub_sensitive_text(str(exc))
                ),
                "billing_summary": {
                    "status": "not_attempted",
                    "resource_attribution": "not_available",
                },
                "events": _event(
                    state,
                    "AWS metrics collection failed; optimization blocked",
                ),
                "status": "collection_failed",
            }

        # Account-level billing and resource-level costs are separate
        # sources. Failure in either must not invalidate CPU telemetry.
        try:
            billing_summary = collect_aws_cost_summary()
        except Exception as exc:  # noqa: BLE001 — billing failure must not prevent metrics collection.
            billing_summary = {
                "status": "unavailable",
                "reason": scrub_sensitive_text(str(exc)),
                "resource_attribution": "not_available",
            }
            warnings.append(
                "AWS billing data unavailable (account-level billing); see billing.json."
            )

        try:
            resource_costs = collect_ec2_resource_costs()
        except Exception as exc:  # noqa: BLE001 — resource attribution is optional and must fail safely.
            resource_costs = {
                "status": "unavailable",
                "resource_type": "EC2",
                "reason": scrub_sensitive_text(str(exc)),
                "resources": [],
                "resource_attribution": "not_available",
            }

        # Scrub collector-provided error details before they enter workflow
        # state or billing.json. Keep account and resource costs separate.
        resource_reason = resource_costs.get("reason")
        if isinstance(resource_reason, str):
            resource_costs["reason"] = scrub_sensitive_text(resource_reason)

        billing_summary["ec2_resource_costs"] = resource_costs
        metrics = _attach_ec2_resource_costs(metrics, resource_costs)

        if resource_costs.get("status") != "available":
            warnings.append(
                "EC2 resource-level costs unavailable; no resource costs "
                "or savings will be inferred from account-level billing."
            )

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

    if mode == "aws" and not metrics:
        return {
            "run_id": run_id,
            "metrics": [],
            "validation_error": (
                "AWS discovery returned no resources with usable CPU "
                "telemetry. Optimization and artifact writing were blocked."
            ),
            "billing_summary": billing_summary,
            "events": events,
            "status": "collection_failed",
        }

    events.append(
        scrub_sensitive_text(
            f"Billing summary status: {billing_summary.get('status', 'unknown')}"
        )
    )

    return {
        "run_id": run_id,
        "metrics": [
            metric.model_dump(mode="json")
            for metric in metrics
        ],
        "billing_summary": billing_summary,
        "events": events,
        "status": "data_collected",
    }



def optimize(state: AgentState) -> AgentState:
    """Generate proposals with explicit evidence gaps and separate risk/confidence."""
    proposals: list[dict[str, Any]] = []

    for raw_metric in state.get("metrics", []):
        metric = ResourceMetric.model_validate(raw_metric)
        discovery = metric.metadata.get("discovery", "")
        cost_status = metric.metadata.get("cost_status", "not_collected")
        cost_currency = metric.metadata.get("cost_currency", "").upper()
        eligible = (
            metric.resource_type == "compute"
            and metric.environment in {"dev", "test"}
            and metric.avg_cpu_percent < 10
            and metric.peak_cpu_percent < 35
            and not metric.production_critical
        )

        # A live rightsizing recommendation requires all of these. Account-level
        # billing and a short observed cost period are not resource monthly cost.
        evidence_gaps: list[str] = []
        if metric.avg_memory_percent is None:
            evidence_gaps.append("average memory utilization telemetry")
        elif metric.avg_memory_percent > 70:
            evidence_gaps.append("memory utilization below the conservative 70% threshold")

        try:
            telemetry_hours = float(metric.metadata.get("telemetry_window_hours", "0"))
        except (TypeError, ValueError):
            telemetry_hours = 0
        if telemetry_hours < 168:
            evidence_gaps.append("at least 7 days of utilization history")

        workload_stability = metric.metadata.get("workload_stability", "").strip().lower()
        if workload_stability not in {"stable", "steady"}:
            evidence_gaps.append("workload stability/seasonality evidence")

        verified_monthly_cost = (
            cost_status == "verified_monthly_cost"
            and cost_currency == "USD"
            and metric.monthly_cost_usd > 0
        )
        if not verified_monthly_cost:
            evidence_gaps.append("verified monthly resource-level USD cost")

        # Mock-mode proposals are deliberately simulations, not live decisions.
        is_simulated_cost = (
            discovery == "mock"
            and cost_status == "simulated_monthly_cost"
            and cost_currency == "USD"
            and metric.monthly_cost_usd > 0
        )
        live_rightsize_evidence_complete = not evidence_gaps

        if not eligible:
            hot = metric.peak_cpu_percent >= 80 or metric.production_critical
            proposal = OptimizationProposal(
                resource_id=metric.resource_id,
                provider=metric.provider,
                action="no_change" if hot else "review_only",
                rationale=(
                    f"Peak CPU is {metric.peak_cpu_percent:.1f}%. "
                    "Automated rightsizing is withheld by the conservative policy."
                ),
                estimated_monthly_savings_usd=0,
                savings_basis="not_applicable",
                risk="critical" if hot else "high",
            )
        elif is_simulated_cost:
            proposal = OptimizationProposal(
                resource_id=metric.resource_id,
                provider=metric.provider,
                action="rightsize",
                rationale=(
                    f"Non-production mock compute averages {metric.avg_cpu_percent:.1f}% "
                    f"CPU and peaks at {metric.peak_cpu_percent:.1f}%. The 30% figure "
                    "is a simulated estimate, not a live recommendation or forecast."
                ),
                estimated_monthly_savings_usd=round(metric.monthly_cost_usd * 0.30, 2),
                savings_basis="simulated_estimate",
                risk="medium",
                proposed_instance_type="smaller-compatible-size; verify provider catalog",
            )
        elif eligible and verified_monthly_cost and live_rightsize_evidence_complete:
            proposal = OptimizationProposal(
                resource_id=metric.resource_id,
                provider=metric.provider,
                action="rightsize",
                rationale=(
                    f"Non-production compute averages {metric.avg_cpu_percent:.1f}% "
                    f"CPU, peaks at {metric.peak_cpu_percent:.1f}%, and has "
                    f"{metric.avg_memory_percent:.1f}% average memory utilization. "
                    "The 30% savings figure is an estimate from verified monthly "
                    "resource cost; verify compatibility and workload requirements."
                ),
                estimated_monthly_savings_usd=round(metric.monthly_cost_usd * 0.30, 2),
                savings_basis="verified_monthly_cost_estimate",
                risk="medium",
                proposed_instance_type="smaller-compatible-size; verify provider catalog",
            )
        else:
            detail = "; ".join(evidence_gaps)
            observed_cost_note = ""
            if cost_status == "observed_14_day_cost":
                observed_cost_note = (
                    " A recent 14-day Cost Explorer amount is evidence only and "
                    "is not converted into monthly cost."
                )
            elif cost_status == "observed_cost_non_usd":
                observed_cost_note = " A non-USD cost is not converted into USD savings."
            elif cost_status == "ambiguous_resource_cost":
                observed_cost_note = " Resource-cost matching was ambiguous; no amount was selected."
            proposal = OptimizationProposal(
                resource_id=metric.resource_id,
                provider=metric.provider,
                action="review_only",
                rationale=(
                    f"Non-production compute averages {metric.avg_cpu_percent:.1f}% "
                    f"CPU and peaks at {metric.peak_cpu_percent:.1f}%. Rightsizing "
                    f"was withheld because evidence is incomplete: {detail}. "
                    "No monthly savings are claimed."
                    + observed_cost_note
                ),
                estimated_monthly_savings_usd=0,
                savings_basis="unavailable",
                risk="medium",
            )

        proposal_data = proposal.model_dump(mode="json")
        # Confidence is evidence quality, not operational risk severity.
        if is_simulated_cost:
            confidence = "low"
        elif live_rightsize_evidence_complete and proposal_data["action"] == "rightsize":
            confidence = "high"
        elif not evidence_gaps and proposal_data["action"] != "rightsize":
            confidence = "medium"
        else:
            confidence = "low"

        proposal_data["optimization_confidence"] = confidence
        proposal_data["missing_evidence"] = evidence_gaps
        proposals.append(proposal_data)

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
        "events": _event(state, f"Generated {len(proposals)} proposals"),
        "status": "optimized",
    }



def assess_risk(state: AgentState) -> AgentState:
    """Assess production risks and validate generated Terraform locally."""
    risks: list[str] = []
    metrics = {
        item["resource_id"]: ResourceMetric.model_validate(item)
        for item in state.get("metrics", [])
    }

    for raw_proposal in state.get("proposals", []):
        proposal = OptimizationProposal.model_validate(raw_proposal)
        metric = metrics.get(proposal.resource_id)

        if metric is None:
            return {
                "validation_error": (
                    "A proposal references an unknown resource; "
                    "artifact writing was blocked."
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
    return (
        "reject"
        if state.get("validation_error")
        else "approval"
    )


def route_collection(state: AgentState) -> str:
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
        f"proposal savings estimate ${total_savings:.2f}/month (may include simulated mock estimates; not realized savings)"
    )

    billing = state.get("billing_summary", {})
    if billing.get("status") == "available":
        print(
            "AWS observed account cost for "
            f"{billing['period_start']} to "
            f"{billing['period_end_exclusive']} (exclusive): "
            f"{billing['currency']} {billing['total_cost']:.2f}"
        )
        print(
            "Note: account-level cost is not individual resource cost "
            "or realized savings."
        )
    elif billing.get("status") == "unavailable":
        print("AWS billing summary unavailable; see billing.json.")

    for proposal in state.get("proposals", []):
        print(
            f"- {proposal['provider']} {proposal['resource_id']}: "
            f"{proposal['action']} ({proposal['risk']}; "
            f"${proposal['estimated_monthly_savings_usd']:.2f}/mo)"
        )

    for risk in state.get("risk_summary", []):
        print("REVIEW:", risk)

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
    return "write" if state.get("approved") else "reject"


def _write_artifacts(directory: Path, state: AgentState) -> None:
    """Write proposals, HCL, audit trail, and separate billing data."""
    directory.mkdir(parents=True, exist_ok=True)

    proposal_document = {
        "run_id": state.get("run_id"),
        "proposals": state.get("proposals", []),
        "risk_summary": state.get("risk_summary", []),
    }

    evidence_report = build_cost_evidence_report(state)
    audit_events = [
        *state.get("events", []),
        f"Cost evidence report generated for {evidence_report['summary']['resource_count']} resources",
    ]
    audit_document = {
        "events": audit_events,
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

    (directory / "billing.json").write_text(
        json.dumps(
            state.get(
                "billing_summary",
                {
                    "status": "not_collected",
                    "resource_attribution": "not_available",
                },
            ),
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    (directory / "cost_evidence.json").write_text(
        json.dumps(evidence_report, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )

    history_path = directory / "cost_history.json"
    previous_history = None
    if history_path.is_file():
        try:
            previous_history = json.loads(history_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            # Never silently append to a corrupt history file; fail the artifact
            # write so the caller's existing rollback protection can restore it.
            raise RuntimeError("Existing cost_history.json is unreadable; refusing to overwrite it")
    history_document = build_proposal_history(evidence_report, previous_history)
    history_path.write_text(
        json.dumps(history_document, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )

    # Record hashes of all generated files except the manifest itself.
    files = sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and path.name != "manifest.json"
    )

    manifest = {
        "run_id": state.get("run_id"),
        "algorithm": "sha256",
        "files": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in files
        },
    }

    (directory / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )

def write_branch(s: AgentState) -> AgentState:
    """Write and commit local proposal artifacts with rollback on failure."""
    if s.get("approved") is not True:
        return {
            "status": "write_blocked",
            "events": _event(
                s,
                "Local write blocked because explicit human approval is missing",
            ),
        }

    repo = Path(os.getenv("FINOPS_GIT_REPO", ".")).resolve()
    out_name = os.getenv("FINOPS_OUTPUT_DIR", "artifacts")

    if not re.fullmatch(r"[A-Za-z0-9_-]+", out_name):
        return {
            "status": "write_blocked",
            "events": _event(s, "Invalid output directory"),
        }

    run_id = s.get("run_id")
    if not run_id or not re.fullmatch(r"[A-Za-z0-9_-]+", run_id):
        return {
            "status": "write_blocked",
            "events": _event(s, "Invalid or missing run ID"),
        }

    def git(*args, env=None):
        try:
            return subprocess.run(
                ["git", *args],
                cwd=repo,
                capture_output=True,
                text=True,
                timeout=30,
                shell=False,
                check=False,
                env={
                    **os.environ,
                    "GIT_TERMINAL_PROMPT": "0",
                    **(env or {}),
                },
            )
        except (OSError, subprocess.TimeoutExpired):
            return None

    # Without a repository, write local artifacts only.
    if not (repo / ".git").exists():
        out = Path(out_name).resolve()
        try:
            _write_artifacts(out, s)
        except Exception:  # noqa: BLE001 — convert artifact-write failures into a controlled workflow result.
            return {
                "status": "write_failed",
                "events": _event(s, "Local artifact writing failed"),
            }

        return {
            "output_path": str(out),
            "status": "artifacts_written",
            "events": _event(
                s,
                "Local artifacts written; no Git repository found",
            ),
        }

    dirty = git("status", "--porcelain")
    if dirty is None or dirty.returncode != 0 or dirty.stdout.strip():
        return {
            "status": "write_blocked",
            "events": _event(
                s,
                "Repository must be clean before branch operation",
            ),
        }

    prefix = re.sub(
        r"[^A-Za-z0-9/_-]",
        "-",
        os.getenv("FINOPS_GIT_BRANCH_PREFIX", "finops/optimization"),
    ).strip("/")

    if (
        not prefix
        or any(part in ("", ".", "..") for part in prefix.split("/"))
    ):
        return {
            "status": "write_blocked",
            "events": _event(s, "Invalid Git branch prefix"),
        }

    branch = f"{prefix}/{run_id}"
    original = git("branch", "--show-current")

    if original is None or original.returncode != 0 or not original.stdout.strip():
        return {
            "status": "write_blocked",
            "events": _event(s, "Cannot determine current branch"),
        }

    original_branch = original.stdout.strip()
    out = repo / out_name
    backup_parent = None
    branch_created = False

    # Preserve any pre-existing output directory, including ignored files.
    # This prevents a failed run from destroying artifacts from earlier runs.
    try:
        if out.exists():
            backup_parent = tempfile.mkdtemp(prefix="finops-backup-")
            backup = Path(backup_parent) / "output-backup"
            if out.is_dir():
                shutil.copytree(out, backup)
            else:
                shutil.copy2(out, backup)

        switch_result = git("switch", "-c", branch)
        if switch_result is None or switch_result.returncode != 0:
            return {
                "status": "write_blocked",
                "events": _event(s, "Branch creation failed"),
            }

        branch_created = True

        _write_artifacts(out, s)

        add_result = git("add", "--", out_name)
        if add_result is None or add_result.returncode != 0:
            raise RuntimeError("Git add failed")

        # A successful git add must stage the intended proposal artifacts.
        staged = git("diff", "--cached", "--quiet", "--", out_name)
        if staged is None or staged.returncode == 0:
            raise RuntimeError("No proposal artifacts were staged")

        name = os.getenv(
            "FINOPS_GIT_AUTHOR_NAME",
            "FinOps Optimization Agent",
        )
        email = os.getenv(
            "FINOPS_GIT_AUTHOR_EMAIL",
            "finops-agent@example.invalid",
        )

        commit_env = {
            "GIT_AUTHOR_NAME": name,
            "GIT_AUTHOR_EMAIL": email,
            "GIT_COMMITTER_NAME": name,
            "GIT_COMMITTER_EMAIL": email,
        }

        commit_result = git(
            "commit",
            "-m",
            f"chore(finops): proposal {run_id}",
            env=commit_env,
        )
        if commit_result is None or commit_result.returncode != 0:
            raise RuntimeError("Git commit failed")

        return {
            "output_path": str(out),
            "git_branch": branch,
            "status": "branch_committed",
            "events": _event(
                s,
                f"Committed {branch}; no remote push",
            ),
        }

    except Exception as exc:  # noqa: BLE001 — trigger rollback for unexpected Git workflow failures.
        rollback_ok = True

        # The original repository was clean, so restore the generated output
        # and return to the original branch without touching unrelated files.
        try:
            if branch_created:
                reset_result = git("reset", "--quiet")
                if reset_result is None or reset_result.returncode != 0:
                    rollback_ok = False

            if backup_parent is not None:
                backup = Path(backup_parent) / "output-backup"

                if out.is_dir():
                    shutil.rmtree(out)
                elif out.exists():
                    out.unlink()

                if backup.exists():
                    if backup.is_dir():
                        shutil.copytree(backup, out)
                    else:
                        out.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(backup, out)
            elif out.exists():
                if out.is_dir():
                    shutil.rmtree(out)
                else:
                    out.unlink()

            if branch_created:
                switch_back = git("switch", original_branch)
                if switch_back is None or switch_back.returncode != 0:
                    rollback_ok = False
                else:
                    delete_branch = git("branch", "-D", branch)
                    if delete_branch is None or delete_branch.returncode != 0:
                        rollback_ok = False

        except Exception:  # noqa: BLE001 — record rollback failure instead of masking the original failure.
            rollback_ok = False

        message = "Proposal generation failed; rollback completed"
        if not rollback_ok:
            message = (
                "Proposal generation failed; rollback was incomplete. "
                "Inspect Git status and the current branch before retrying."
            )

        return {
            "status": "write_failed",
            "events": _event(s, f"{message}: {type(exc).__name__}"),
        }

    finally:
        if backup_parent is not None:
            shutil.rmtree(backup_parent, ignore_errors=True)


def reject(state: AgentState) -> AgentState:
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
    graph = StateGraph(AgentState)

    for name, function in [
        ("collect_data", collect_data),
        ("optimize", optimize),
        ("assess_risk", assess_risk),
        ("approval", approval),
        ("write", write_branch),
        ("reject", reject),
    ]:
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