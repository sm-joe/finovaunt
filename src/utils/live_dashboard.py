"""Real AWS account dashboard projection; no artifact files or synthetic data.

All fields originate from persisted responses to successful AWS Cost Explorer
and EC2/RDS/EBS API requests. Missing evidence is represented as unavailable,
not zero spend, savings or resources.
"""
from __future__ import annotations

from scripts import access_control


def account_dashboard(account_id: str) -> dict | None:
    account = access_control.get_account(account_id)
    if account is None:
        return None
    billing_history = access_control.billing_history(account_id)
    latest_billing = billing_history[-1] if billing_history else None
    latest_inventory = access_control.latest_inventory_scan(account_id)
    assets = list(latest_inventory.get("assets", [])) if latest_inventory else []

    # Savings are scenario estimates from verified AWS Price List rates,
    # never realized reductions. PV associations block any savings claim.
    candidates = []
    for asset in assets:
        if asset.get("type") != "ebs" or asset.get("state") != "available":
            continue
        evidence = asset.get("optimization_evidence") or {}
        pv = evidence.get("kubernetes") or {"status": "not_verified"}
        candidates.append({
            "resource_id": asset["id"], "name": asset["name"],
            "type": asset["type"], "region": asset["region"],
            "reason": "Unattached EBS volume requires human review; Kubernetes ownership, backups and retention must be checked.",
            "action": "review_only",
            "estimated_monthly_savings": evidence.get("estimated_monthly_savings_usd"),
            "possible_monthly_storage_reduction_usd": evidence.get("possible_monthly_storage_reduction_usd"),
            "verified_savings": None,
            "confidence": evidence.get("confidence", "blocked"),
            "risk": evidence.get("risk", "high"),
            "pricing": evidence.get("pricing"),
            "kubernetes": pv,
            "evidence": evidence.get("evidence", ["Pricing and Kubernetes evidence not yet collected."]),
            "assumptions": evidence.get("estimated_savings_assumptions", []),
            "requires_human_approval": True,
            "can_auto_delete": False,
            "inventory_scan_id": latest_inventory.get("id") if latest_inventory else None,
        })
    return {
        "source": "aws_collected",
        "account": {k: v for k, v in account.items() if k != "external_id"},
        "billing": latest_billing,
        "inventory": latest_inventory,
        "ebs_reviews": access_control.ebs_reviews(account_id),
        "billing_history": [
            {"id": scan["id"], "scanned_at": scan.get("scanned_at"),
             "period_start": scan.get("period_start"),
             "total_cost": scan.get("total_cost"),
             "currency": scan.get("currency"), "status": scan.get("status")}
            for scan in billing_history
        ],
        "review_candidates": candidates,
        "estimated_savings": None,  # No aggregate savings without complete comparable evidence.
        "potential_ebs_savings_usd": (
            str(sum(
                (__import__("decimal").Decimal(c["estimated_monthly_savings"]) for c in candidates
                 if c["estimated_monthly_savings"] is not None),
                __import__("decimal").Decimal("0")
            )) if any(c["estimated_monthly_savings"] is not None for c in candidates) else None
        ),
        "ebs_price_coverage": {
            "priced_candidates": sum(c["estimated_monthly_savings"] is not None for c in candidates),
            "total_candidates": len(candidates),
        },
        "realized_savings": None,
        "billing_status": "collected" if latest_billing else "not_collected",
        "inventory_status": "collected" if latest_inventory else "not_collected",
    }
