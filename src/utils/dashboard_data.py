"""Read-only dashboard projections over Finovaunt's existing scan artifacts.

This module does not collect cloud data or estimate/verify savings. It projects
existing cost_evidence.json, proposal.json, billing.json, and cost_history.json
into stable API payloads for the dashboard.
"""
from __future__ import annotations

from datetime import datetime
import json
import math
from pathlib import Path
from typing import Any, Mapping


ARTIFACT_FILES = (
    "cost_evidence.json",
    "proposal.json",
    "billing.json",
    "cost_history.json",
)


class DashboardDataError(RuntimeError):
    """Raised when the latest scan artifacts are missing or malformed."""


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip() or default


def _read_json(path: Path, *, required: bool = False) -> dict[str, Any]:
    if not path.exists():
        if required:
            raise DashboardDataError(f"Required scan artifact is missing: {path.name}")
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DashboardDataError(f"Scan artifact is unreadable: {path.name}") from exc
    if not isinstance(payload, dict):
        raise DashboardDataError(f"Scan artifact must contain a JSON object: {path.name}")
    return payload


def load_artifacts(artifact_dir: Path) -> dict[str, Any]:
    """Load the latest scan files. Evidence is required; other files are optional."""
    if not artifact_dir.exists() or not artifact_dir.is_dir():
        raise DashboardDataError("No scan artifact directory is available yet.")
    return {
        "evidence": _read_json(artifact_dir / "cost_evidence.json", required=True),
        "proposal": _read_json(artifact_dir / "proposal.json"),
        "billing": _read_json(artifact_dir / "billing.json"),
        "history": _read_json(artifact_dir / "cost_history.json"),
    }


def _proposal_index(proposal_document: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for item in _list(proposal_document.get("proposals")):
        if not isinstance(item, Mapping):
            continue
        resource_id = _text(item.get("resource_id"))
        if resource_id and resource_id not in result:
            result[resource_id] = item
    return result


def _resource_rows(artifacts: Mapping[str, Any]) -> list[dict[str, Any]]:
    evidence = _mapping(artifacts.get("evidence"))
    proposal_doc = _mapping(artifacts.get("proposal"))
    proposals = _proposal_index(proposal_doc)
    rows: list[dict[str, Any]] = []

    for raw in _list(evidence.get("resources")):
        if not isinstance(raw, Mapping):
            continue
        resource_id = _text(raw.get("resource_id"), "unknown")
        recommendation = _mapping(raw.get("recommendation"))
        savings = _mapping(raw.get("savings_evidence"))
        cost = _mapping(raw.get("cost_evidence"))
        utilization = _mapping(raw.get("utilization"))
        proposal = proposals.get(resource_id, {})
        estimate = _number(savings.get("estimated_monthly_savings_usd"))
        classification = _text(savings.get("classification"), "not_estimable_from_available_evidence")
        # A malformed or negative amount is never allowed to inflate dashboard totals.
        if estimate is None or estimate < 0:
            estimate = None

        rows.append({
            "resource_id": resource_id,
            "name": _text(raw.get("name"), resource_id),
            "provider": _text(raw.get("provider"), "unknown"),
            "resource_type": _text(raw.get("resource_type"), "unknown"),
            "region": _text(raw.get("region"), "unknown"),
            "environment": _text(raw.get("environment"), "unknown"),
            "production_critical": bool(raw.get("production_critical", False)),
            "utilization": {
                "avg_cpu_percent": _number(utilization.get("avg_cpu_percent")),
                "peak_cpu_percent": _number(utilization.get("peak_cpu_percent")),
                "avg_memory_percent": _number(utilization.get("avg_memory_percent")),
            },
            "cost": {
                "status": _text(cost.get("status"), "cost_unavailable"),
                "amount": _number(cost.get("amount")),
                "currency": _text(cost.get("currency"), "unknown").upper(),
                "monthly_cost_usd": _number(cost.get("monthly_cost_usd")),
                "period": _mapping(cost.get("period")),
                "source": _text(cost.get("source"), "unknown"),
            },
            "recommendation": {
                "action": _text(recommendation.get("action"), "not_proposed"),
                "rationale": recommendation.get("rationale"),
                "risk": _text(recommendation.get("risk"), "unknown"),
                "requires_human_approval": bool(recommendation.get("requires_human_approval", True)),
                "proposed_instance_type": recommendation.get("proposed_instance_type"),
                "optimization_confidence": _text(proposal.get("optimization_confidence"), "low"),
                "missing_evidence": _list(proposal.get("missing_evidence")),
            },
            "savings": {
                "estimated_monthly_usd": estimate,
                "basis": _text(savings.get("basis"), "unavailable"),
                "classification": classification,
                "assumptions": _list(savings.get("assumptions")),
                "realized_status": _text(
                    _mapping(savings.get("realized_savings")).get("status"),
                    "not_verified",
                ),
                "realized_monthly_usd": _number(
                    _mapping(savings.get("realized_savings")).get("amount_usd")
                ),
            },
            "data_quality_warnings": _list(raw.get("data_quality_warnings")),
        })
    return rows


def build_overview(artifacts: Mapping[str, Any]) -> dict[str, Any]:
    evidence = _mapping(artifacts.get("evidence"))
    billing = _mapping(artifacts.get("billing"))
    history = _mapping(artifacts.get("history"))
    account = _mapping(evidence.get("account_billing_context"))
    if not account:
        account = billing
    rows = _resource_rows(artifacts)

    evidenced = [
        row["savings"]["estimated_monthly_usd"]
        for row in rows
        if row["savings"]["classification"] == "estimated_from_monthly_resource_cost"
        and row["savings"]["estimated_monthly_usd"] is not None
    ]
    simulated = [
        row["savings"]["estimated_monthly_usd"]
        for row in rows
        if row["savings"]["classification"] == "simulated_estimate"
        and row["savings"]["estimated_monthly_usd"] is not None
    ]
    action_counts: dict[str, int] = {}
    risk_counts: dict[str, int] = {}
    for row in rows:
        action = row["recommendation"]["action"]
        risk = row["recommendation"]["risk"]
        action_counts[action] = action_counts.get(action, 0) + 1
        risk_counts[risk] = risk_counts.get(risk, 0) + 1

    total = len(rows)
    latest_run_id = _text(evidence.get("run_id")) or _text(history.get("latest_run_id")) or None
    return {
        "generated_at": _text(evidence.get("generated_at")) or None,
        "run_id": latest_run_id,
        "data_source": "mock" if any(
            row["savings"]["classification"] == "simulated_estimate" for row in rows
        ) else "live_or_unknown",
        "currency": "USD",
        "cloud_spend": {
            "status": _text(account.get("status"), "not_collected"),
            "amount": _number(account.get("total_cost", account.get("total_cost_usd"))),
            "currency": _text(account.get("currency"), "USD").upper(),
            "period_start": account.get("period_start"),
            "period_end_exclusive": account.get("period_end_exclusive"),
            "scope": "account_level_context_only",
            "resource_attribution": _text(account.get("resource_attribution"), "not_available"),
        },
        "potential_monthly_savings_usd": round(sum(evidenced), 2),
        "simulated_monthly_savings_usd": round(sum(simulated), 2),
        "realized_savings": {
            "status": "not_verified",
            "amount_usd": None,
            "reason": "No verified realized-savings total is available in the current scan artifacts.",
        },
        "resources_scanned": total,
        "opportunities": sum(1 for row in rows if row["recommendation"]["action"] not in {"no_change", "not_proposed"}),
        "resources_without_estimable_savings": sum(
            1 for row in rows
            if row["savings"]["classification"] in {
                "not_estimable_from_available_evidence", "not_estimated"
            }
        ),
        "action_counts": action_counts,
        "risk_counts": risk_counts,
        "scan_count": len(_list(history.get("runs"))),
        "savings_policy": {
            "potential_total_includes_only": "estimated_from_monthly_resource_cost",
            "simulated_estimates_are_separate": True,
            "account_cost_is_not_resource_cost": True,
            "realized_savings_requires_post_change_verification": True,
        },
    }


def build_opportunities(artifacts: Mapping[str, Any]) -> dict[str, Any]:
    rows = _resource_rows(artifacts)
    items = [
        row for row in rows
        if row["recommendation"]["action"] not in {"no_change", "not_proposed"}
    ]
    items.sort(
        key=lambda row: (
            row["savings"]["classification"] == "estimated_from_monthly_resource_cost",
            row["savings"]["estimated_monthly_usd"] or 0,
        ),
        reverse=True,
    )
    return {"count": len(items), "items": items}


def build_assets(artifacts: Mapping[str, Any]) -> dict[str, Any]:
    rows = _resource_rows(artifacts)
    return {"count": len(rows), "items": rows}


def build_scans(artifacts: Mapping[str, Any]) -> dict[str, Any]:
    history = _mapping(artifacts.get("history"))
    evidence = _mapping(artifacts.get("evidence"))
    runs = _list(history.get("runs"))
    scans = []
    for run in runs:
        if not isinstance(run, Mapping):
            continue
        resources = _list(run.get("resources"))
        actions: dict[str, int] = {}
        for resource in resources:
            if not isinstance(resource, Mapping):
                continue
            action = _text(_mapping(resource.get("recommendation")).get("action"), "not_proposed")
            actions[action] = actions.get(action, 0) + 1
        scans.append({
            "run_id": _text(run.get("run_id"), "unknown"),
            "generated_at": _text(run.get("generated_at")) or None,
            "resource_count": int(_number(run.get("resource_count")) or len(resources)),
            "action_counts": actions,
            "realized_savings": {"status": "not_verified", "amount_usd": None},
        })
    if not scans and evidence:
        scans.append({
            "run_id": _text(evidence.get("run_id"), "unknown"),
            "generated_at": _text(evidence.get("generated_at")) or None,
            "resource_count": len(_list(evidence.get("resources"))),
            "action_counts": {},
            "realized_savings": {"status": "not_verified", "amount_usd": None},
        })
    scans.sort(key=lambda item: item.get("generated_at") or "")
    return {"count": len(scans), "items": scans}


def build_scan_detail(artifacts: Mapping[str, Any], run_id: str) -> dict[str, Any] | None:
    history = _mapping(artifacts.get("history"))
    for run in _list(history.get("runs")):
        if isinstance(run, Mapping) and _text(run.get("run_id")) == run_id:
            return dict(run)
    evidence = _mapping(artifacts.get("evidence"))
    if _text(evidence.get("run_id")) == run_id:
        return {
            "run_id": run_id,
            "generated_at": evidence.get("generated_at"),
            "resource_count": len(_list(evidence.get("resources"))),
            "resources": _list(evidence.get("resources")),
            "account_billing_context": evidence.get("account_billing_context", {}),
            "realized_savings_verified": False,
        }
    return None
