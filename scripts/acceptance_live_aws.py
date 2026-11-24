"""Operator-run live AWS read-only release acceptance.

This is deliberately NOT a CI mock and does NOT modify AWS infrastructure.
Run using the real source credentials intended for a deployment; the collector
role is assumed and identity-verified by Finovaunt's own production code.

Exit nonzero if required evidence is unavailable. Output excludes resource
names, account IDs, IAM identifiers, access keys and billing amounts.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

from src.tools.aws_identity import resolve_aws_session
from src.tools.billing_service import collect_billing
from src.tools.finops_core import collect_eks, collect_s3


def acceptance(account: dict, external_id: str = "") -> dict:
    report = {"schema": 1, "checked_at": datetime.now(timezone.utc).isoformat(),
              "status": "fail", "checks": {}, "aws_mutations": 0}
    credentials, auth = resolve_aws_session(account, external_id=external_id,
                                            session_name="FinovauntV1ReadOnlyAcceptance")
    report["checks"]["role_identity"] = {"status": "pass", "mode": auth}
    try:
        billing = collect_billing(account, external_id=external_id)
        report["checks"]["cost_explorer"] = {
            "status": "pass" if billing.get("cost_scope") == "account_service_month_to_date"
                                 and billing.get("pages_collected", 0) >= 1 else "fail",
            "pages_collected": billing.get("pages_collected", 0),
            "count": len(billing.get("services", [])),
            "is_final": billing.get("is_final"),
        }
    except Exception:
        report["checks"]["cost_explorer"] = {"status": "fail", "reason": "read_only_billing_unavailable"}

    # Collect only inventory evidence, not prices, resource modifications, or
    # recommendations. Empty buckets/clusters are valid when fully enumerated.
    try:
        inventory = collect_s3(account, credentials)
        report["checks"]["s3"] = {
            "status": "pass" if inventory.get("status") == "success" else "fail",
            "bucket_count": inventory.get("observed_buckets"),
            "cost_attribution": "not_assessed",
        }
    except Exception:
        report["checks"]["s3"] = {"status": "fail", "reason": "read_only_s3_unavailable"}

    try:
        clusters = collect_eks(account, credentials)
        report["checks"]["eks"] = {
            "status": "pass" if clusters.get("status") == "success" else "fail",
            "cluster_count": len(clusters.get("clusters", [])),
            "namespace_dollar_costs": "not_assessed",
        }
    except Exception:
        report["checks"]["eks"] = {"status": "fail", "reason": "read_only_eks_unavailable"}

    # EC2/EBS/RDS inventory uses the exact production collector, bounded
    # to avoid silently accepting truncated enumeration in release evidence.
    try:
        from src.tools.inventory_service import collect_inventory
        collected = collect_inventory(account, external_id=external_id)
        report["checks"]["ec2_ebs_rds"] = {
            "status": "fail" if collected.get("truncated") else "pass",
            "truncated": bool(collected.get("truncated")),
            "asset_count": collected.get("asset_count"),
        }
    except Exception:
        report["checks"]["ec2_ebs_rds"] = {
            "status": "fail", "reason": "read_only_inventory_unavailable"
        }
    report["status"] = ("pass" if all(
        item["status"] == "pass" for item in report["checks"].values()
    ) else "fail")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Live, read-only Finovaunt release acceptance")
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--role-arn", required=True)
    parser.add_argument("--region", default="us-east-1")
    args = parser.parse_args()
    if not args.account_id.isdigit() or len(args.account_id) != 12:
        parser.error("account-id must be exactly twelve digits")
    account = {"account_id": args.account_id,
               "role_arn": args.role_arn, "region": args.region}
    try:
        result = acceptance(account, external_id=os.getenv("FINOVAUNT_EXTERNAL_ID", ""))
    except Exception:
        result = {"schema": 1, "status": "fail",
                  "checks": {"role_identity": {
                      "status": "fail", "reason": "source_or_target_role_authentication_failed"}},
                  "aws_mutations": 0}
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["status"] != "pass":
        sys.exit(1)


if __name__ == "__main__":
    main()
