"""Safe actionable diagnostics for errors raised while collecting AWS evidence.

Never return raw ClientError messages, request parameters, ARNs, or tokens
to browser clients. AWS stage + allowlisted error code are sufficient.
"""
from __future__ import annotations

import re
from typing import Callable, TypeVar
from botocore.exceptions import (
    BotoCoreError, ClientError, NoCredentialsError, PartialCredentialsError,
    CredentialRetrievalError, EndpointConnectionError,
)

T = TypeVar("T")
_CODES = {
    "AccessDenied", "AccessDeniedException", "UnauthorizedOperation",
    "ExpiredToken", "ExpiredTokenException", "InvalidClientTokenId",
    "UnrecognizedClientException", "SignatureDoesNotMatch",
    "ValidationException", "OptInRequired", "DataUnavailableException",
    "LimitExceededException", "Throttling", "ThrottlingException",
    "IncompleteSignature", "InvalidParameterException",
}
_GUIDANCE = {
    "assume_role": (
        "The API source AWS identity must have sts:AssumeRole on the onboarded role; "
        "that role must trust the source principal. If the trust policy requires "
        "sts:ExternalId, enter the matching External ID when collecting."
    ),
    "verify_identity": (
        "Verify the assumed role credentials are active and the target role "
        "belongs to the onboarded AWS account."
    ),
    "cost_explorer": (
        "Allow ce:GetCostAndUsage for the assumed role, and verify Cost Explorer "
        "is enabled and billing data is available for this AWS account."
    ),
    "source_identity": (
        "Configure valid AWS source credentials in the API container "
        "(prefer a workload identity or short-lived session) and restart the service."
    ),
    "inventory": (
        "Allow read-only EC2/RDS Describe actions in the selected account/region."
    ),
}


class AWSAccessError(RuntimeError):
    def __init__(self, stage: str, code: str, guidance: str | None = None):
        self.stage = stage
        self.code = code
        self.guidance = guidance or _GUIDANCE.get(stage, "Verify AWS connectivity and IAM permissions.")
        super().__init__(f"AWS {stage} failed ({code}). {self.guidance}")

    def public_payload(self) -> dict:
        return {
            "error": "aws_collection_failed",
            "stage": self.stage,
            "aws_error_code": self.code,
            "message": str(self),
        }


def aws_call(stage: str, fn: Callable[..., T], **kwargs) -> T:
    try:
        return fn(**kwargs)
    except ClientError as exc:
        original = str(exc.response.get("Error", {}).get("Code", "Unknown"))
        code = original if original in _CODES else "AWSClientError"
        if code in {"ExpiredToken", "ExpiredTokenException", "InvalidClientTokenId", "UnrecognizedClientException", "SignatureDoesNotMatch", "IncompleteSignature"}:
            hint = ("AWS credentials were rejected or expired. Renew the API container's "
                    "source credentials, then retry. If this occurred after sts:AssumeRole, "
                    "check the assumed role session and account.")
        elif code in {"Throttling", "ThrottlingException", "LimitExceededException"}:
            hint = "AWS throttled the request. Retry after the AWS rate limit allows it."
        else:
            hint = None
        raise AWSAccessError(stage, code, hint) from exc
    except (NoCredentialsError, PartialCredentialsError, CredentialRetrievalError) as exc:
        raise AWSAccessError("source_identity" if stage == "assume_role" else stage, "CredentialsUnavailable") from exc
    except EndpointConnectionError as exc:
        raise AWSAccessError(stage, "EndpointUnreachable", "The API container cannot reach the AWS endpoint. Check networking, DNS and region.") from exc
    except BotoCoreError as exc:
        raise AWSAccessError(stage, "SDKError") from exc
