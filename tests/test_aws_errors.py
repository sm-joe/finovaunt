"""AWS failures are attributable to a stage, without leaking AWS error text."""
from __future__ import annotations
from botocore.exceptions import ClientError, NoCredentialsError
from src.tools.aws_errors import AWSAccessError, aws_call


def _client_error(code: str, message: str = "secret role ARN and user metadata") -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": message}}, "AssumeRole")


def test_assume_role_denied_has_actionable_safe_guidance():
    def deny(**kwargs):
        raise _client_error("AccessDenied")

    try:
        aws_call("assume_role", deny, RoleArn="arn:aws:iam::123456789012:role/test")
        raise AssertionError("Expected AWSAccessError")
    except AWSAccessError as exc:
        body = exc.public_payload()
        assert body["stage"] == "assume_role"
        assert body["aws_error_code"] == "AccessDenied"
        assert "sts:AssumeRole" in body["message"]
        assert "secret role ARN" not in str(body)
        assert "123456789012" not in str(body)


def test_cost_explorer_denied_reports_cost_explorer_scope():
    def deny(**kwargs):
        raise _client_error("AccessDeniedException")
    try:
        aws_call("cost_explorer", deny)
        raise AssertionError("Expected AWSAccessError")
    except AWSAccessError as exc:
        body = exc.public_payload()
        assert body["stage"] == "cost_explorer"
        assert "ce:GetCostAndUsage" in body["message"]
        assert body["aws_error_code"] == "AccessDeniedException"


def test_missing_source_identity_is_not_misreported_as_cost_explorer():
    def missing(**kwargs):
        raise NoCredentialsError()
    try:
        aws_call("assume_role", missing)
        raise AssertionError("Expected AWSAccessError")
    except AWSAccessError as exc:
        assert exc.stage == "source_identity"
        assert exc.code == "CredentialsUnavailable"


def test_unknown_codes_and_sensitive_messages_are_suppressed():
    def unexpected(**kwargs):
        raise _client_error("UnauthorizedCustomException", "private-details-from-aws")
    try:
        aws_call("verify_identity", unexpected)
        raise AssertionError("Expected AWSAccessError")
    except AWSAccessError as exc:
        assert exc.public_payload()["aws_error_code"] == "AWSClientError"
        assert "private-details-from-aws" not in str(exc.public_payload())


def test_success_is_returned_unchanged():
    assert aws_call("cost_explorer", lambda **kwargs: {"ok": True}) == {"ok": True}
