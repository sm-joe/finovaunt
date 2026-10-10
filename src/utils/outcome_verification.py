"""Verify post-change cost outcomes using explicit approval and billing evidence.

This module is deliberately pure: it does not call cloud APIs, approve changes,
apply Terraform, or infer savings from account-level billing totals.
"""
from __future__ import annotations

from datetime import UTC, datetime
import math
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "1.0"


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip() or default


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _timestamp(value: Any) -> datetime | None:
    raw = _text(value)
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value else None


def _resource_key(resource: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        _text(resource.get("provider"), "unknown").lower(),
        _text(resource.get("region"), "unknown").lower(),
        _text(resource.get("resource_id"), "unknown"),
    )


def _resources(report: Mapping[str, Any]) -> dict[tuple[str, str, str], Mapping[str, Any]]:
    raw = report.get("resources", [])
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return {}
    result: dict[tuple[str, str, str], Mapping[str, Any]] = {}
    for item in raw:
        if isinstance(item, Mapping):
            result[_resource_key(item)] = item
    return result


def _billing_window(resource: Mapping[str, Any]) -> tuple[datetime, datetime] | None:
    cost = resource.get("cost_evidence")
    if not isinstance(cost, Mapping):
        return None
    if cost.get("status") not in {"verified_monthly_cost", "observed_period_cost_only"}:
        return None
    period = cost.get("period")
    if not isinstance(period, Mapping):
        return None
    start = _timestamp(period.get("start"))
    end = _timestamp(period.get("end_exclusive"))
    if start is None or end is None or end <= start:
        return None
    return start, end


def _cost(resource: Mapping[str, Any]) -> tuple[float, str, str] | None:
    evidence = resource.get("cost_evidence")
    if not isinstance(evidence, Mapping):
        return None
    status = evidence.get("status")
    currency = _text(evidence.get("currency"), "unknown").upper()
    if currency != "USD":
        return None
    if status == "verified_monthly_cost":
        amount = _number(evidence.get("monthly_cost_usd"))
        return (amount, "verified_monthly_cost", currency) if amount is not None else None
    if status == "observed_period_cost_only":
        amount = _number(evidence.get("amount"))
        return (amount, "observed_period_cost_only", currency) if amount is not None else None
    return None


def _verify_resource(
    baseline: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
    *,
    deployed_at: datetime | None,
    baseline_generated_at: datetime | None,
    after_generated_at: datetime | None,
    deployment_valid: bool,
) -> dict[str, Any]:
    reasons: list[str] = []
    if baseline is None:
        reasons.append("Resource is absent from the baseline report.")
    if after is None:
        reasons.append("Resource is absent from the post-change report.")
    if not deployment_valid:
        reasons.append("Approval and deployment evidence is incomplete or invalid.")
    if deployed_at is None:
        reasons.append("A timezone-aware deployment timestamp is required.")
    if baseline_generated_at is None or after_generated_at is None:
        reasons.append("Both reports require valid timezone-aware generated_at timestamps.")
    elif deployed_at is not None:
        if baseline_generated_at >= deployed_at:
            reasons.append("Baseline report must predate the deployment timestamp.")
        if after_generated_at <= deployed_at:
            reasons.append("Post-change report must be generated after deployment.")

    before_cost_record = _cost(baseline) if baseline is not None else None
    after_cost_record = _cost(after) if after is not None else None
    before_window = _billing_window(baseline) if baseline is not None else None
    after_window = _billing_window(after) if after is not None else None
    reduction: float | None = None
    before_cost = before_cost_record[0] if before_cost_record else None
    after_cost = after_cost_record[0] if after_cost_record else None

    if before_cost_record is None or after_cost_record is None:
        reasons.append("Both records need supported USD resource-level cost evidence: verified monthly cost or observed-period cost.")
    elif before_cost_record[1] != after_cost_record[1]:
        reasons.append("Baseline and post-change cost evidence must use the same cost basis.")
    if before_window is None or after_window is None:
        reasons.append("Explicit, dated billing windows are required; monthly estimates without period dates are insufficient.")
    elif deployed_at is not None:
        before_start, before_end = before_window
        after_start, after_end = after_window
        if before_end > deployed_at:
            reasons.append("Baseline billing window must end at or before deployment.")
        if after_start < deployed_at:
            reasons.append("Post-change billing window must start at or after deployment.")
        if before_end > after_start:
            reasons.append("Baseline and post-change billing windows must not overlap.")
        if (before_end - before_start) != (after_end - after_start):
            reasons.append("Baseline and post-change billing windows must have equal duration.")

    if before_cost is not None and after_cost is not None and before_window and after_window:
        reduction = round(before_cost - after_cost, 6)

    cost_basis = before_cost_record[1] if before_cost_record else None
    is_monthly_basis = cost_basis == "verified_monthly_cost"
    if reasons:
        status = "not_verified"
        realized = {"status": "not_verified", "amount_usd": None}
    elif reduction is not None and reduction > 0 and is_monthly_basis:
        status = "verified_monthly_cost_reduction"
        realized = {
            "status": "verified",
            "amount_usd": reduction,
            "basis": "comparable_verified_monthly_resource_cost",
            "attribution": "temporally_associated_with_change; causal attribution is not proven by cost comparison alone",
        }
    elif reduction is not None and reduction > 0:
        status = "verified_observed_period_cost_reduction"
        realized = {
            "status": "not_verified",
            "amount_usd": None,
            "reason": "A lower observed-period charge is verified, but it is not treated as recurring monthly savings.",
        }
    elif reduction == 0 and is_monthly_basis:
        status = "no_cost_reduction_observed"
        realized = {"status": "verified_zero_reduction", "amount_usd": 0.0}
    elif reduction == 0:
        status = "no_observed_period_cost_reduction"
        realized = {"status": "not_verified", "amount_usd": None}
    elif is_monthly_basis:
        status = "monthly_cost_increased"
        realized = {"status": "verified_negative_outcome", "amount_usd": reduction}
    else:
        status = "observed_period_cost_increased"
        realized = {"status": "not_verified", "amount_usd": None}

    return {
        "resource_id": _text((after or baseline or {}).get("resource_id"), "unknown"),
        "provider": _text((after or baseline or {}).get("provider"), "unknown"),
        "region": _text((after or baseline or {}).get("region"), "unknown"),
        "verification_status": status,
        "cost_basis": cost_basis or "unavailable",
        "baseline_cost_usd": before_cost,
        "post_change_cost_usd": after_cost,
        "cost_reduction_usd": reduction if not reasons else None,
        "realized_monthly_savings_usd": reduction if not reasons and is_monthly_basis and reduction is not None and reduction > 0 else None,
        "baseline_billing_window": {
            "start": _iso(before_window[0]) if before_window else None,
            "end_exclusive": _iso(before_window[1]) if before_window else None,
        },
        "post_change_billing_window": {
            "start": _iso(after_window[0]) if after_window else None,
            "end_exclusive": _iso(after_window[1]) if after_window else None,
        },
        "realized_savings": realized,
        "limitations": reasons,
    }


def build_outcome_verification(
    baseline_report: Mapping[str, Any],
    post_change_report: Mapping[str, Any],
    change_record: Mapping[str, Any],
    *,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Compare resource costs across a documented, approved deployment.

    `change_record` must contain approval.status='approved',
    deployment.status='applied' or 'deployed', change_id, and a timezone-aware
    deployment.deployed_at. Resource records are matched by provider, region,
    and resource_id. Missing evidence fails closed.
    """
    now = generated_at or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    approval = change_record.get("approval")
    deployment = change_record.get("deployment")
    approval = approval if isinstance(approval, Mapping) else {}
    deployment = deployment if isinstance(deployment, Mapping) else {}
    change_id = _text(change_record.get("change_id"))
    approval_status = _text(approval.get("status")).lower()
    deployment_status = _text(deployment.get("status")).lower()
    deployed_at = _timestamp(deployment.get("deployed_at"))
    deployment_valid = bool(
        change_id
        and approval_status == "approved"
        and deployment_status in {"applied", "deployed"}
        and deployed_at is not None
        and _text(deployment.get("evidence_ref"))
    )

    baseline_generated_at = _timestamp(baseline_report.get("generated_at"))
    after_generated_at = _timestamp(post_change_report.get("generated_at"))
    baseline_resources = _resources(baseline_report)
    after_resources = _resources(post_change_report)

    requested = change_record.get("resources")
    if isinstance(requested, Sequence) and not isinstance(requested, (str, bytes)) and requested:
        keys = [_resource_key(item) for item in requested if isinstance(item, Mapping)]
    else:
        keys = sorted(set(baseline_resources) | set(after_resources))

    outcomes = [
        _verify_resource(
            baseline_resources.get(key),
            after_resources.get(key),
            deployed_at=deployed_at,
            baseline_generated_at=baseline_generated_at,
            after_generated_at=after_generated_at,
            deployment_valid=deployment_valid,
        )
        for key in keys
    ]
    verified_count = sum(item["verification_status"] == "verified_monthly_cost_reduction" for item in outcomes)
    observed_reduction_count = sum(item["verification_status"] == "verified_observed_period_cost_reduction" for item in outcomes)
    not_verified_count = sum(item["verification_status"] == "not_verified" for item in outcomes)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "change": {
            "change_id": change_id or None,
            "approval_status": approval_status or "unknown",
            "deployment_status": deployment_status or "unknown",
            "deployed_at": _iso(deployed_at),
            "deployment_evidence_ref": _text(deployment.get("evidence_ref")) or None,
            "evidence_valid": deployment_valid,
        },
        "baseline_run_id": _text(baseline_report.get("run_id"), "unknown"),
        "post_change_run_id": _text(post_change_report.get("run_id"), "unknown"),
        "summary": {
            "resources_evaluated": len(outcomes),
            "verified_monthly_cost_reductions": verified_count,
            "verified_observed_period_cost_reductions": observed_reduction_count,
            "not_verified": not_verified_count,
            "realized_savings_usd": round(sum(
                item["realized_savings"]["amount_usd"] or 0.0
                for item in outcomes
                if item["realized_savings"]["status"] == "verified"
            ), 6),
            "causal_attribution_proven": False,
        },
        "resources": outcomes,
        "controls": {
            "requires_explicit_approval_and_deployment_evidence": True,
            "requires_comparable_usd_resource_cost_basis": True,
            "requires_dated_non_overlapping_equal_duration_billing_windows": True,
            "observed_period_reduction_is_not_recurring_monthly_savings": True,
            "account_level_totals_not_used_for_resource_savings": True,
            "simulated_and_observed_period_costs_not_used_as_monthly_baselines": True,
            "causal_attribution_proven": False,
        },
    }
