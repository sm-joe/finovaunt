"""Build an auditable, append-only history of FinOps evidence snapshots.

This module compares evidence; it does not infer realized savings, convert
observed-period charges into monthly costs, or treat account spend as resource cost.
"""
from __future__ import annotations

from datetime import UTC, datetime
import math
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "1.0"
_UTILIZATION_FIELDS = ("avg_cpu_percent", "peak_cpu_percent", "avg_memory_percent")


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip() or default


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _resource_key(resource: Mapping[str, Any]) -> str:
    # Provider-scoped resource IDs are preferred; region remains in the key to
    # avoid accidentally comparing resources with reused IDs across regions.
    return "|".join((
        _text(resource.get("provider"), "unknown").lower(),
        _text(resource.get("region"), "unknown").lower(),
        _text(resource.get("resource_id"), "unknown"),
    ))


def _snapshot_resource(resource: Mapping[str, Any]) -> dict[str, Any]:
    utilization = resource.get("utilization")
    if not isinstance(utilization, Mapping):
        utilization = {}
    cost = resource.get("cost_evidence")
    if not isinstance(cost, Mapping):
        cost = {}
    period = cost.get("period")
    if not isinstance(period, Mapping):
        period = {}
    recommendation = resource.get("recommendation")
    if not isinstance(recommendation, Mapping):
        recommendation = {}
    savings = resource.get("savings_evidence")
    if not isinstance(savings, Mapping):
        savings = {}
    return {
        "resource_id": _text(resource.get("resource_id"), "unknown"),
        "provider": _text(resource.get("provider"), "unknown"),
        "resource_type": _text(resource.get("resource_type"), "unknown"),
        "name": _text(resource.get("name"), "unknown"),
        "region": _text(resource.get("region"), "unknown"),
        "environment": _text(resource.get("environment"), "unknown"),
        "utilization": {field: _number(utilization.get(field)) for field in _UTILIZATION_FIELDS},
        "cost": {
            "status": _text(cost.get("status"), "cost_unavailable"),
            "evidence_kind": _text(cost.get("evidence_kind"), "none"),
            "amount": _number(cost.get("amount")),
            "currency": _text(cost.get("currency"), "unknown").upper(),
            "monthly_cost_usd": _number(cost.get("monthly_cost_usd")),
            "period_start": _text(period.get("start")) or None,
            "period_end_exclusive": _text(period.get("end_exclusive")) or None,
            "period_basis": _text(period.get("basis"), "unknown"),
        },
        "recommendation": {
            "action": _text(recommendation.get("action"), "not_proposed"),
            "risk": _text(recommendation.get("risk"), "unknown"),
            "requires_human_approval": bool(recommendation.get("requires_human_approval", True)),
            "proposed_instance_type": _text(recommendation.get("proposed_instance_type")) or None,
        },
        "savings": {
            "estimated_monthly_savings_usd": _number(savings.get("estimated_monthly_savings_usd")),
            "basis": _text(savings.get("basis"), "unavailable"),
            "classification": _text(savings.get("classification"), "not_estimated"),
            # A proposal is not evidence that a change was deployed or savings realized.
            "realized_savings_status": _text(
                (savings.get("realized_savings") or {}).get("status")
                if isinstance(savings.get("realized_savings"), Mapping) else None,
                "not_verified",
            ),
            "realized_savings_usd": None,
        },
    }


def _compare(current: Mapping[str, Any], previous: Mapping[str, Any] | None) -> dict[str, Any]:
    if previous is None:
        return {
            "baseline": "no_previous_snapshot",
            "utilization_delta_percentage_points": {field: None for field in _UTILIZATION_FIELDS},
            "monthly_resource_cost_delta_usd": None,
            "cost_comparison_status": "no_previous_snapshot",
            "recommendation_changed": None,
            "proposed_monthly_savings_delta_usd": None,
            "realized_savings": {"status": "not_verified", "amount_usd": None},
        }

    current_util = current.get("utilization", {})
    previous_util = previous.get("utilization", {})
    deltas: dict[str, float | None] = {}
    for field in _UTILIZATION_FIELDS:
        now = _number(current_util.get(field)) if isinstance(current_util, Mapping) else None
        before = _number(previous_util.get(field)) if isinstance(previous_util, Mapping) else None
        deltas[field] = round(now - before, 6) if now is not None and before is not None else None

    current_cost = current.get("cost", {})
    previous_cost = previous.get("cost", {})
    monthly_delta: float | None = None
    cost_status = "not_comparable"
    if isinstance(current_cost, Mapping) and isinstance(previous_cost, Mapping):
        now_cost = _number(current_cost.get("monthly_cost_usd"))
        before_cost = _number(previous_cost.get("monthly_cost_usd"))
        comparable = (
            current_cost.get("status") == "verified_monthly_cost"
            and previous_cost.get("status") == "verified_monthly_cost"
            and now_cost is not None
            and before_cost is not None
            and _text(current_cost.get("currency"), "USD").upper() == "USD"
            and _text(previous_cost.get("currency"), "USD").upper() == "USD"
        )
        if comparable:
            monthly_delta = round(now_cost - before_cost, 6)
            cost_status = "comparable_verified_monthly_resource_cost"
        elif current_cost.get("status") == previous_cost.get("status") == "simulated_monthly_cost":
            cost_status = "simulated_cost_not_production_evidence"
        elif current_cost.get("period_basis") == previous_cost.get("period_basis") == "observed_period_not_monthly":
            cost_status = "observed_period_cost_not_compared_as_monthly"

    current_savings = current.get("savings", {})
    previous_savings = previous.get("savings", {})
    now_estimate = _number(current_savings.get("estimated_monthly_savings_usd")) if isinstance(current_savings, Mapping) else None
    before_estimate = _number(previous_savings.get("estimated_monthly_savings_usd")) if isinstance(previous_savings, Mapping) else None
    return {
        "baseline": "immediately_previous_run",
        "utilization_delta_percentage_points": deltas,
        "monthly_resource_cost_delta_usd": monthly_delta,
        "cost_comparison_status": cost_status,
        "recommendation_changed": (
            current.get("recommendation") != previous.get("recommendation")
        ),
        "proposed_monthly_savings_delta_usd": (
            round(now_estimate - before_estimate, 6)
            if now_estimate is not None and before_estimate is not None else None
        ),
        "realized_savings": {
            "status": "not_verified",
            "amount_usd": None,
            "reason": "Evidence snapshots alone do not prove deployment or realized savings.",
        },
    }


def build_proposal_history(
    current_report: Mapping[str, Any],
    previous_history: Mapping[str, Any] | None = None,
    *,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Append a snapshot and compare it with the latest prior distinct run.

    Reprocessing the same run_id replaces that run's snapshot rather than
    double-counting it. The input history is never mutated.
    """
    timestamp = generated_at or datetime.now(UTC)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    run_id = _text(current_report.get("run_id"), "unknown")
    resources_raw = current_report.get("resources", [])
    if not isinstance(resources_raw, Sequence) or isinstance(resources_raw, (str, bytes)):
        resources_raw = []
    current_resources = [
        _snapshot_resource(item) for item in resources_raw if isinstance(item, Mapping)
    ]

    history_runs: list[dict[str, Any]] = []
    if isinstance(previous_history, Mapping):
        raw_runs = previous_history.get("runs", [])
        if isinstance(raw_runs, Sequence) and not isinstance(raw_runs, (str, bytes)):
            history_runs = [dict(item) for item in raw_runs if isinstance(item, Mapping)]

    # If this run is being regenerated, remove its previous copy before choosing
    # the comparison baseline. This makes retries deterministic and idempotent.
    history_runs = [item for item in history_runs if _text(item.get("run_id"), "unknown") != run_id]
    previous_run = history_runs[-1] if history_runs else None
    previous_resources_raw = previous_run.get("resources", []) if previous_run else []
    previous_by_key: dict[str, Mapping[str, Any]] = {}
    if isinstance(previous_resources_raw, Sequence) and not isinstance(previous_resources_raw, (str, bytes)):
        for item in previous_resources_raw:
            if isinstance(item, Mapping):
                previous_by_key[_resource_key(item)] = item

    compared_resources = []
    for resource in current_resources:
        previous = previous_by_key.get(_resource_key(resource))
        compared_resources.append({
            **resource,
            "changes_since_previous": _compare(resource, previous),
        })

    run_record = {
        "run_id": run_id,
        "generated_at": _text(current_report.get("generated_at"), timestamp.astimezone(UTC).isoformat().replace("+00:00", "Z")),
        "resource_count": len(compared_resources),
        "resources": compared_resources,
        "account_billing_context": current_report.get("account_billing_context", {}),
        "realized_savings_verified": False,
    }
    history_runs.append(run_record)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": timestamp.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "run_count": len(history_runs),
        "latest_run_id": run_id,
        "history_retention": "append_only_snapshots_except_same_run_retry_replacement",
        "runs": history_runs,
        "controls": {
            "account_cost_is_not_resource_cost": True,
            "observed_period_cost_is_not_monthly_cost": True,
            "proposed_savings_are_not_realized_savings": True,
            "realized_savings_status": "not_verified_without_post_change_validation",
        },
    }
