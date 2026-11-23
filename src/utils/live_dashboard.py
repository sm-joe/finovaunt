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

    # Unattached EBS volumes are review candidates, not monetized savings.
    candidates = [
        {"resource_id": asset["id"], "name": asset["name"],
         "type": asset["type"], "region": asset["region"],
         "reason": "EBS volume is unattached; verify retention and snapshots before taking action.",
         "estimated_monthly_savings": None, "action": "review_only"}
        for asset in assets
        if asset.get("type") == "ebs" and asset.get("recommendation") == "review_only"
    ]
    return {
        "source": "aws_collected",
        "account": {k: v for k, v in account.items() if k != "external_id"},
        "billing": latest_billing,
        "inventory": latest_inventory,
        "billing_history": [
            {"id": scan["id"], "scanned_at": scan.get("scanned_at"),
             "period_start": scan.get("period_start"),
             "total_cost": scan.get("total_cost"),
             "currency": scan.get("currency"), "status": scan.get("status")}
            for scan in billing_history
        ],
        "review_candidates": candidates,
        "estimated_savings": None,
        "realized_savings": None,
        "billing_status": "collected" if latest_billing else "not_collected",
        "inventory_status": "collected" if latest_inventory else "not_collected",
    }
