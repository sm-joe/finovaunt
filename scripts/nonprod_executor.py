"""Opt-in, independently authorized EC2 non-production power executor.

NEVER imported by the dashboard or default read-only collector. This CLI
requires a separate narrowly scoped IAM role, an exact resource allowlist,
explicit enablement and a human-approved action. No scheduling is enabled
automatically.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import re
from pathlib import Path


ACCOUNT_RE = re.compile(r"^arn:aws:iam::([0-9]{12}):role/Finovaunt-NonProd-Executor-Role$")
INSTANCE_RE = re.compile(r"^i-[a-f0-9]{8,17}$")
SAFE_ENVS = {"dev", "development", "test", "qa", "staging"}


def verify_ec2_target(instance: dict, *, expected_id: str, environment: str) -> dict:
    if str(instance.get("InstanceId", "")) != expected_id:
        raise ValueError("EC2 instance identity did not match the allowlist.")
    tags = {str(t.get("Key")): str(t.get("Value")) for t in instance.get("Tags", [])}
    if tags.get("Environment", "").lower() != environment:
        raise ValueError("Instance does not have the approved non-production Environment tag.")
    if any(k.startswith("kubernetes.io/cluster/") or
           k.startswith("eks:") or k in {"aws:autoscaling:groupName",
                                          "k8s.io/cluster-autoscaler/enabled"}
           for k in tags):
        raise ValueError("EKS, Kubernetes and Auto Scaling-managed instances are excluded.")
    if str(instance.get("RootDeviceType", "")) != "ebs":
        raise ValueError("Only EBS-backed EC2 instances can be scheduled.")
    return {"instance_id": expected_id, "environment": environment,
            "owner": tags.get("Owner"), "service": "ec2"}


def execute_action(*, role_arn: str, region: str, instance_ids: list[str],
                   environment: str, action: str, execute: bool = False) -> dict:
    """Plan by default; never reuse collector credentials for write operations."""
    if not ACCOUNT_RE.fullmatch(role_arn):
        raise ValueError("Explicit Finovaunt-NonProd-Executor-Role ARN is required.")
    if action not in {"start", "stop"}:
        raise ValueError("Action must be start or stop.")
    if environment not in SAFE_ENVS or len(instance_ids) > 20 or not instance_ids:
        raise ValueError("Provide 1–20 exact instance IDs with an approved non-production environment.")
    if len(set(instance_ids)) != len(instance_ids) or not all(INSTANCE_RE.fullmatch(i) for i in instance_ids):
        raise ValueError("Provide unique valid EC2 instance identifiers.")
    if not re.fullmatch(r"[a-z]{2}(?:-gov)?-[a-z]+-[0-9]", region):
        raise ValueError("A valid AWS region is required.")
    if execute and os.environ.get("FINOVAUNT_ALLOW_NONPROD_EXECUTION") != "explicitly-enabled":
        raise PermissionError("Execution is disabled. Set the separate opt-in flag explicitly.")

    import boto3
    from src.tools.aws_errors import aws_call
    sts = boto3.client("sts", region_name=region)
    response = aws_call("nonprod_executor_assume_role", sts.assume_role,
        RoleArn=role_arn, RoleSessionName="FinovauntNonProdOperator")
    creds = response["Credentials"]
    kwargs = {"aws_access_key_id": creds["AccessKeyId"],
              "aws_secret_access_key": creds["SecretAccessKey"],
              "aws_session_token": creds["SessionToken"]}
    principal = aws_call("verify_identity",
        boto3.client("sts", region_name=region, **kwargs).get_caller_identity)
    if str(principal.get("Account")) != ACCOUNT_RE.fullmatch(role_arn).group(1) or (
        "/Finovaunt-NonProd-Executor-Role/" not in str(principal.get("Arn", ""))):
        raise PermissionError("Assumed identity does not match the dedicated non-production executor role.")
    ec2 = boto3.client("ec2", region_name=region, **kwargs)
    response = aws_call("nonprod_executor_inventory", ec2.describe_instances, InstanceIds=instance_ids)
    actual = [i for r in response.get("Reservations", []) for i in r.get("Instances", [])]
    by_id = {str(i["InstanceId"]): i for i in actual}
    if set(by_id) != set(instance_ids):
        raise ValueError("All allowlisted EC2 instances must be found before proceeding.")
    targets = [verify_ec2_target(by_id[i], expected_id=i, environment=environment)
               for i in instance_ids]
    plan = {"action": action, "region": region, "environment": environment,
            "role_arn": role_arn, "instance_ids": instance_ids,
            "targets": targets, "executed": False,
            "requires_operator_approval": True,
            "scanned_at": datetime.now(timezone.utc).isoformat()}
    if not execute:
        return plan
    # Fail closed for inconsistent states; never stop an already stopped node.
    valid_states = {"stop": {"running"}, "start": {"stopped"}}[action]
    if any(i.get("State", {}).get("Name") not in valid_states for i in actual):
        raise ValueError("Unexpected EC2 state; no actions executed.")
    operation = ec2.stop_instances if action == "stop" else ec2.start_instances
    try:
        operation(InstanceIds=instance_ids, DryRun=True)
    except Exception as exc:
        from botocore.exceptions import ClientError
        if not isinstance(exc, ClientError) or exc.response.get("Error", {}).get("Code") != "DryRunOperation":
            raise PermissionError("EC2 DryRun authorization failed; no changes executed.") from None
    operation(InstanceIds=instance_ids)
    plan["executed"] = True
    return plan


def main() -> None:
    parser = argparse.ArgumentParser(description="Optional isolated EC2 non-production executor")
    parser.add_argument("--role-arn", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--environment", choices=sorted(SAFE_ENVS), required=True)
    parser.add_argument("--action", choices=("start", "stop"), required=True)
    parser.add_argument("--instance-id", action="append", required=True)
    parser.add_argument("--execute", action="store_true", help="Perform AWS actions after explicit environment opt-in")
    args = parser.parse_args()
    result = execute_action(role_arn=args.role_arn, region=args.region,
        environment=args.environment, action=args.action,
        instance_ids=args.instance_id, execute=args.execute)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
