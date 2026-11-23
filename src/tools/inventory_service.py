"""Read-only AWS inventory for one explicitly onboarded account and region.

The collector does not mutate AWS resources or infer prices or savings from
resource descriptions alone. An empty inventory is a valid observation.
"""
from __future__ import annotations
from datetime import datetime, timezone

from src.tools.aws_errors import aws_call


class InventoryCollectionError(RuntimeError):
    pass


def collect_inventory(account: dict, *, external_id: str = "", max_assets: int = 500) -> dict:
    import boto3
    if not 1 <= max_assets <= 5000:
        raise ValueError("max_assets must be between 1 and 5000")
    account_id = str(account["account_id"])
    region = str(account["region"])
    role_arn = str(account["role_arn"])
    if not role_arn.startswith(f"arn:aws:iam::{account_id}:role/"):
        raise InventoryCollectionError("IAM role does not belong to the onboarded account.")

    sts = boto3.client("sts", region_name=region)
    assume = {"RoleArn": role_arn, "RoleSessionName": "FinovauntInventoryReadOnly"}
    if external_id:
        assume["ExternalId"] = external_id
    credentials = aws_call("assume_role", sts.assume_role, **assume)["Credentials"]
    session_kwargs = {
        "aws_access_key_id": credentials["AccessKeyId"],
        "aws_secret_access_key": credentials["SecretAccessKey"],
        "aws_session_token": credentials["SessionToken"],
    }
    if str(aws_call("verify_identity", boto3.client("sts", region_name=region, **session_kwargs).get_caller_identity).get("Account")) != account_id:
        raise InventoryCollectionError("Assumed AWS account identity does not match onboarding.")

    ec2 = boto3.client("ec2", region_name=region, **session_kwargs)
    rds = boto3.client("rds", region_name=region, **session_kwargs)
    assets: list[dict] = []
    truncated = False
    observed_counts = {"ebs": 0, "ec2": 0, "rds": 0}
    collected_counts = {"ebs": 0, "ec2": 0, "rds": 0}

    def add(item: dict) -> None:
        nonlocal truncated
        kind = item["type"]
        observed_counts[kind] += 1
        if len(assets) < max_assets:
            assets.append(item)
            collected_counts[kind] += 1
        else:
            truncated = True

    # Prioritize volume evidence so a large fleet of EC2/RDS resources
    # cannot silently consume the cap before the EBS safety review.
    # Counts still reflect every observed resource (even if omitted).
    for page in aws_call("inventory_ec2_volumes", ec2.get_paginator("describe_volumes").paginate):
        for volume in page.get("Volumes", []):
            tags = {str(tag.get("Key")): str(tag.get("Value")) for tag in volume.get("Tags", [])}
            add({
                "id": str(volume["VolumeId"]),
                "type": "ebs",
                "name": tags.get("Name") or str(volume["VolumeId"]),
                "state": str(volume.get("State", "unknown")),
                "size": f"{volume.get('Size', 0)} GiB / {volume.get('VolumeType', 'unknown')}",
                "region": region,
                "size_gib": int(volume.get("Size", 0)),
                "volume_type": str(volume.get("VolumeType", "unknown")),
                "iops": volume.get("Iops"),
                "throughput": volume.get("Throughput"),
                "availability_zone": volume.get("AvailabilityZone"),
                "encrypted": bool(volume.get("Encrypted", False)),
                "created_at": volume.get("CreateTime").isoformat() if volume.get("CreateTime") else None,
                "tags": tags,
                "attachments": [
                    {"instance_id": a.get("InstanceId"), "state": a.get("State")}
                    for a in volume.get("Attachments", [])
                ],
                "cost_status": "not_attributed",
                "recommendation": "review_only" if volume.get("State") == "available" else "not_assessed",
            })

    for page in aws_call("inventory_ec2_instances", ec2.get_paginator("describe_instances").paginate):
        for reservation in page.get("Reservations", []):
            for instance in reservation.get("Instances", []):
                tags = {str(tag.get("Key")): str(tag.get("Value")) for tag in instance.get("Tags", [])}
                add({
                    "id": str(instance["InstanceId"]),
                    "type": "ec2",
                    "name": tags.get("Name") or str(instance["InstanceId"]),
                    "state": str(instance.get("State", {}).get("Name", "unknown")),
                    "size": str(instance.get("InstanceType", "unknown")),
                    "region": region,
                    "cost_status": "not_attributed",
                    "recommendation": "not_assessed",
                })

    for page in aws_call("inventory_rds", rds.get_paginator("describe_db_instances").paginate):
        for db in page.get("DBInstances", []):
            add({
                "id": str(db["DBInstanceIdentifier"]),
                "type": "rds",
                "name": str(db["DBInstanceIdentifier"]),
                "state": str(db.get("DBInstanceStatus", "unknown")),
                "size": str(db.get("DBInstanceClass", "unknown")),
                "region": region,
                "cost_status": "not_attributed",
                "recommendation": "not_assessed",
            })

    optimization = {"pricing_status": "not_collected", "kubernetes_status": "not_verified"}
    try:
        from src.tools.ebs_optimization import enrich_ebs
        session = boto3.Session(**session_kwargs)
        optimization = enrich_ebs(assets, region=region, session=session)
    except Exception:
        # Pricing/EKS access must never invalidate a real inventory scan.
        for asset in assets:
            if asset.get("type") == "ebs":
                asset["optimization_evidence"] = {
                    "pricing": None, "kubernetes": {"status": "not_verified"},
                    "estimated_monthly_savings_usd": None, "verified_savings_usd": None,
                    "confidence": "blocked", "risk": "high", "can_auto_delete": False,
                    "requires_human_approval": True,
                    "evidence": ["AWS pricing or Kubernetes PV verification unavailable."],
                }
    return {
        "optimization_collection": optimization,
        "account_id": account_id,
        "region": region,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "status": "partial" if truncated else ("empty_inventory" if not assets else "success"),
        "asset_count": len(assets),
        "observed_counts": observed_counts,
        "collected_counts": collected_counts,
        "observed_total": sum(observed_counts.values()),
        "resource_cap": max_assets,
        "truncated": truncated,
        "assets": assets,
        "read_only": True,
        "savings_estimated": False,
    }
