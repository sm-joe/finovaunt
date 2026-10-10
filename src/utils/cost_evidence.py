"""Build a provenance-first per-resource cost evidence report.

This module is intentionally pure: it does not call cloud APIs, modify the
workflow state, apply Terraform, or infer savings from account-level totals.
"""

from __future__ import annotations

from datetime import UTC, datetime
import math
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "1.0"


def _number(value: Any) -> float | None:
    """Return a finite numeric value, or None when the input is unusable."""
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
    return str(value).strip()


def _cost_evidence(metric: Mapping[str, Any]) -> dict[str, Any]:
    metadata = metric.get("metadata")
    if not isinstance(metadata, Mapping):
        metadata = {}

    raw_status = _text(metadata.get("cost_status"), "not_collected")
    source = _text(metadata.get("cost_source"), "unknown")
    observed_amount = _number(metadata.get("observed_cost_period_amount"))
    observed_currency = _text(metadata.get("observed_cost_currency"), "unknown").upper()
    period_start = _text(metadata.get("observed_cost_period_start")) or None
    period_end = _text(metadata.get("observed_cost_period_end_exclusive")) or None

    monthly_cost = _number(metric.get("monthly_cost_usd"))
    currency = _text(metadata.get("cost_currency"), "USD").upper()

    if raw_status == "simulated_monthly_cost":
        status = "simulated_monthly_cost"
        evidence_kind = "simulation"
        amount = monthly_cost
        amount_currency = currency
        period = {"start": None, "end_exclusive": None, "basis": "monthly_simulation"}
        warnings = ["Cost is mock/simulated data, not observed AWS spend."]
    elif raw_status == "verified_monthly_cost":
        status = "verified_monthly_cost"
        evidence_kind = "verified_monthly_resource_cost"
        amount = monthly_cost
        amount_currency = currency
        period = {"start": None, "end_exclusive": None, "basis": "monthly"}
        warnings = []
        if monthly_cost is None:
            status = "invalid_cost_value"
            evidence_kind = "unusable"
            warnings.append("Monthly cost value is missing or not finite.")
    elif raw_status == "observed_14_day_cost":
        status = "observed_period_cost_only"
        evidence_kind = "observed_resource_cost"
        amount = observed_amount
        amount_currency = observed_currency
        period = {
            "start": period_start,
            "end_exclusive": period_end,
            "basis": "observed_period_not_monthly",
        }
        warnings = [
            "Observed-period cost is not converted to monthly cost or used as a monthly savings baseline."
        ]
        if observed_amount is None or observed_currency != "USD":
            status = "invalid_or_unsupported_observed_cost"
            warnings.append("Observed amount is missing, invalid, or not denominated in USD.")
    elif raw_status == "observed_cost_non_usd":
        status = "observed_period_cost_non_usd"
        evidence_kind = "observed_resource_cost"
        amount = observed_amount
        amount_currency = observed_currency
        period = {
            "start": period_start,
            "end_exclusive": period_end,
            "basis": "observed_period_not_monthly",
        }
        warnings = ["Non-USD resource cost is not converted or used for USD savings."]
    elif raw_status in {"ambiguous_resource_cost", "invalid_resource_cost"}:
        status = raw_status
        evidence_kind = "unusable"
        amount = None
        amount_currency = None
        period = {"start": period_start, "end_exclusive": period_end, "basis": "unknown"}
        warnings = ["Resource-level cost evidence cannot be safely attributed."]
    else:
        status = "cost_unavailable"
        evidence_kind = "none"
        amount = None
        amount_currency = None
        period = {"start": None, "end_exclusive": None, "basis": "unknown"}
        warnings = ["No usable resource-level cost evidence is attached."]

    return {
        "status": status,
        "evidence_kind": evidence_kind,
        "source": source,
        "amount": amount,
        "currency": amount_currency,
        "period": period,
        "monthly_cost_usd": monthly_cost if status == "verified_monthly_cost" else None,
        "warnings": warnings,
    }


def _savings_evidence(proposal: Mapping[str, Any] | None, cost: Mapping[str, Any]) -> dict[str, Any]:
    if not proposal:
        return {
            "action": "not_proposed",
            "estimated_monthly_savings_usd": None,
            "basis": "unavailable",
            "classification": "not_estimated",
            "assumptions": [],
            "realized_savings": {"status": "not_verified", "amount_usd": None},
        }

    amount = _number(proposal.get("estimated_monthly_savings_usd"))
    basis = _text(proposal.get("savings_basis"), "unavailable")
    action = _text(proposal.get("action"), "unknown")
    assumptions: list[str] = []

    if basis == "simulated_estimate":
        classification = "simulated_estimate"
        assumptions.append("Estimate is based on mock/simulated inputs and is not a production forecast.")
    elif basis == "verified_monthly_cost_estimate":
        classification = "estimated_from_monthly_resource_cost"
        assumptions.append("Savings remain an estimate; instance compatibility, pricing, and workload requirements require review.")
    elif basis == "not_applicable" or action == "no_change":
        classification = "not_applicable"
    else:
        classification = "not_estimable_from_available_evidence"
        assumptions.append("Insufficient verified monthly resource-level cost evidence; account-level spend and observed-period cost are not used as monthly baselines.")

    if action == "review_only" and not assumptions:
        assumptions.append("Review recommendation only; no infrastructure change is authorized.")
    if amount is None:
        amount = 0.0
        assumptions.append("Proposal savings amount was missing or invalid; reported as zero for evidence safety.")
    if amount == 0 and classification not in {"not_applicable", "simulated_estimate", "estimated_from_monthly_resource_cost"}:
        classification = "not_estimable_from_available_evidence"

    return {
        "action": action,
        "estimated_monthly_savings_usd": amount,
        "basis": basis,
        "classification": classification,
        "assumptions": assumptions,
        "realized_savings": {
            "status": "not_verified",
            "amount_usd": None,
            "reason": "No post-change billing comparison is recorded by this workflow.",
        },
    }


def build_cost_evidence_report(
    state: Mapping[str, Any],
    *,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Build a resource-by-resource evidence report from serialized agent state.

    Account-level spend is recorded only as separate context. It is never copied
    into a resource record and never used to calculate savings.
    """
    timestamp = generated_at or datetime.now(UTC)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)

    metrics = state.get("metrics", [])
    proposals = state.get("proposals", [])
    if not isinstance(metrics, Sequence) or isinstance(metrics, (str, bytes)):
        metrics = []
    if not isinstance(proposals, Sequence) or isinstance(proposals, (str, bytes)):
        proposals = []

    proposal_by_resource: dict[str, Mapping[str, Any]] = {}
    for item in proposals:
        if isinstance(item, Mapping):
            resource_id = _text(item.get("resource_id"))
            if resource_id and resource_id not in proposal_by_resource:
                proposal_by_resource[resource_id] = item

    records: list[dict[str, Any]] = []
    for raw_metric in metrics:
        if not isinstance(raw_metric, Mapping):
            continue
        resource_id = _text(raw_metric.get("resource_id"), "unknown")
        metadata = raw_metric.get("metadata")
        if not isinstance(metadata, Mapping):
            metadata = {}
        cost = _cost_evidence(raw_metric)
        proposal = proposal_by_resource.get(resource_id)
        savings = _savings_evidence(proposal, cost)
        utilization = {
            "avg_cpu_percent": _number(raw_metric.get("avg_cpu_percent")),
            "peak_cpu_percent": _number(raw_metric.get("peak_cpu_percent")),
            "avg_memory_percent": _number(raw_metric.get("avg_memory_percent")),
        }
        data_quality = list(cost["warnings"])
        if proposal is None:
            data_quality.append("No proposal matched this resource ID.")
        if savings["classification"] == "not_estimable_from_available_evidence":
            data_quality.append("Savings are not estimable from the available resource-level cost evidence.")

        records.append({
            "resource_id": resource_id,
            "provider": _text(raw_metric.get("provider"), "unknown"),
            "resource_type": _text(raw_metric.get("resource_type"), "unknown"),
            "name": _text(raw_metric.get("name"), "unknown"),
            "region": _text(raw_metric.get("region"), "unknown"),
            "environment": _text(raw_metric.get("environment"), "unknown"),
            "production_critical": bool(raw_metric.get("production_critical", False)),
            "utilization": utilization,
            "cost_evidence": cost,
            "recommendation": {
                "action": _text((proposal or {}).get("action"), "not_proposed"),
                "rationale": _text((proposal or {}).get("rationale")) or None,
                "risk": _text((proposal or {}).get("risk"), "unknown"),
                "requires_human_approval": bool((proposal or {}).get("requires_human_approval", True)),
                "proposed_instance_type": _text((proposal or {}).get("proposed_instance_type")) or None,
            },
            "savings_evidence": savings,
            "data_quality_warnings": list(dict.fromkeys(data_quality)),
        })

    billing = state.get("billing_summary", {})
    if not isinstance(billing, Mapping):
        billing = {}
    account_context: dict[str, Any] = {
        "status": _text(billing.get("status"), "not_collected"),
        "period_start": _text(billing.get("period_start")) or None,
        "period_end_exclusive": _text(billing.get("period_end_exclusive")) or None,
        "metric": _text(billing.get("metric")) or None,
        "currency": _text(billing.get("currency")) or None,
        "total_cost": _number(billing.get("total_cost")),
        "group_by": billing.get("group_by", []),
        "resource_attribution": _text(billing.get("resource_attribution"), "not_available"),
        "usage_note": "Account-level billing is context only and is not attributed to individual resources or used to calculate savings.",
    }
    resource_costs = billing.get("ec2_resource_costs", {})
    if isinstance(resource_costs, Mapping):
        account_context["ec2_resource_cost_collection"] = {
            "status": _text(resource_costs.get("status"), "not_collected"),
            "period_start": _text(resource_costs.get("period_start")) or None,
            "period_end_exclusive": _text(resource_costs.get("period_end_exclusive")) or None,
            "granularity": _text(resource_costs.get("granularity")) or None,
            "reason": _text(resource_costs.get("reason")) or None,
            "resource_attribution": _text(resource_costs.get("resource_attribution"), "not_available"),
        }

    counts: dict[str, int] = {}
    for record in records:
        key = record["cost_evidence"]["status"]
        counts[key] = counts.get(key, 0) + 1
    savings_counts: dict[str, int] = {}
    for record in records:
        key = record["savings_evidence"]["classification"]
        savings_counts[key] = savings_counts.get(key, 0) + 1

    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": _text(state.get("run_id"), "unknown"),
        "generated_at": timestamp.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "summary": {
            "resource_count": len(records),
            "cost_evidence_status_counts": counts,
            "savings_classification_counts": savings_counts,
            "realized_savings_verified": False,
        },
        "account_billing_context": account_context,
        "resources": records,
    }
