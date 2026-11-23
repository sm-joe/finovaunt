"""Resolve AWS credentials for onboarded accounts without role chaining.

When an AWS workload already runs under the *exact* target role, use its
renewing credential provider chain directly. For a different account/role,
assume the explicitly onboarded role and verify the resulting identity.
Never silently use arbitrary same-account credentials as authorization.
"""
from __future__ import annotations

import re
from typing import Any

from src.tools.aws_errors import aws_call, AWSAccessError


_ROLE = re.compile(r"^arn:(aws(?:-[a-z]+)?):iam::([0-9]{12}):role/(?:[a-zA-Z0-9+=,.@_/-]*/)?([a-zA-Z0-9+=,.@_-]+)$")
_SESSION = re.compile(r"^arn:(aws(?:-[a-z]+)?):sts::([0-9]{12}):assumed-role/([^/]+)/([^/]+)$")


def resolve_aws_session(account: dict, *, external_id: str = "", session_name: str = "FinovauntReadOnly") -> tuple[dict, str]:
    """Return client/session kwargs and direct|assumed, never AWS key material in results.

    A role identity is only treated as direct if account, partition and
    role name match the configured IAM role. Role names are unique per account.
    Other role identities must explicitly AssumeRole.
    """
    import boto3

    account_id = str(account.get("account_id", ""))
    role_arn = str(account.get("role_arn", ""))
    region = str(account.get("region", "us-east-1"))
    expected = _ROLE.fullmatch(role_arn)
    if not expected or expected.group(2) != account_id:
        raise AWSAccessError("verify_identity", "InvalidRoleConfiguration",
                             "Onboarded IAM role must belong to the selected 12-digit AWS account.")

    source_sts = boto3.client("sts", region_name=region)
    identity = aws_call("source_identity", source_sts.get_caller_identity)
    source_arn = str(identity.get("Arn", ""))
    session = _SESSION.fullmatch(source_arn)
    if (session and str(identity.get("Account")) == account_id
            and session.group(1) == expected.group(1)
            and session.group(2) == account_id
            and session.group(3) == expected.group(3)):
        # The runtime already possesses automatically rotating role credentials.
        # Never assume a role into itself or copy temporary credentials.
        return {}, "direct"

    parameters: dict[str, Any] = {
        "RoleArn": role_arn, "RoleSessionName": session_name,
    }
    if external_id:
        parameters["ExternalId"] = external_id
    response = aws_call("assume_role", source_sts.assume_role, **parameters)
    creds = response["Credentials"]
    kwargs = {
        "aws_access_key_id": creds["AccessKeyId"],
        "aws_secret_access_key": creds["SecretAccessKey"],
        "aws_session_token": creds["SessionToken"],
    }
    assumed = aws_call(
        "verify_identity",
        boto3.client("sts", region_name=region, **kwargs).get_caller_identity,
    )
    assumed_arn = str(assumed.get("Arn", ""))
    assumed_match = _SESSION.fullmatch(assumed_arn)
    if (str(assumed.get("Account")) != account_id
            or not assumed_match
            or assumed_match.group(1) != expected.group(1)
            or assumed_match.group(3) != expected.group(3)):
        raise AWSAccessError("verify_identity", "RoleMismatch",
                             "Assumed role identity does not match the onboarded IAM role.")
    return kwargs, "assumed"


def inspect_source_identity(account: dict) -> dict:
    """Read-only diagnostics; no role assumption and never returns AWS credentials."""
    import boto3
    from datetime import datetime, timezone
    account_id = str(account["account_id"])
    role_arn = str(account["role_arn"])
    region = str(account["region"])
    expected = _ROLE.fullmatch(role_arn)
    if not expected or expected.group(2) != account_id:
        raise AWSAccessError("verify_identity", "InvalidRoleConfiguration")
    identity = aws_call("source_identity",
                        boto3.client("sts", region_name=region).get_caller_identity)
    source_arn = str(identity.get("Arn", ""))
    session = _SESSION.fullmatch(source_arn)
    direct = bool(
        session and session.group(1) == expected.group(1)
        and session.group(2) == account_id
        and session.group(3) == expected.group(3)
        and str(identity.get("Account")) == account_id
    )
    return {
        "status": "direct_role_ready" if direct else "assume_role_required",
        "source_account_id": str(identity.get("Account", "")),
        "source_principal_arn": source_arn,
        "target_account_id": account_id,
        "target_role_arn": role_arn,
        "assume_role_required": not direct,
        "role_assumption_verified": False,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "note": ("Current source role matches the onboarded collector role."
                 if direct else "Source credentials exist, but target-role assumption and trust have not been tested."),
    }
