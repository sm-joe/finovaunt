"""Workload IAM role execution must bypass self-assumption without reducing isolation."""
import sys
import types

import pytest
from botocore.exceptions import ClientError

from src.tools.aws_identity import resolve_aws_session
from src.tools.aws_errors import AWSAccessError

ACCOUNT = {
    "account_id": "638631156706",
    "role_arn": "arn:aws:iam::638631156706:role/Finovaunt-RO-Scan-Role",
    "region": "us-east-1",
}


class STS:
    def __init__(self, arn, *, assumed=None):
        self.arn = arn
        self.assumed = assumed
        self.calls = []

    def get_caller_identity(self):
        return {"Account": self.arn.split(":")[4], "Arn": self.arn}

    def assume_role(self, **kwargs):
        self.calls.append(kwargs)
        if self.assumed is None:
            raise AssertionError("Must not invoke AssumeRole on the current workload role")
        return {"Credentials": {"AccessKeyId": "FAKE", "SecretAccessKey": "FAKE", "SessionToken": "FAKE"}}


def test_identical_onboarded_workload_role_uses_default_provider(monkeypatch):
    source = STS("arn:aws:sts::638631156706:assumed-role/Finovaunt-RO-Scan-Role/FinovauntPermissionTest")
    monkeypatch.setitem(sys.modules, "boto3", types.SimpleNamespace(
        client=lambda name, **kwargs: source,
    ))
    credentials, mode = resolve_aws_session(ACCOUNT)
    assert credentials == {}
    assert mode == "direct"
    assert not source.calls


def test_path_role_is_identified_by_unique_role_name(monkeypatch):
    source = STS("arn:aws:sts::638631156706:assumed-role/Finovaunt-RO-Scan-Role/abc")
    monkeypatch.setitem(sys.modules, "boto3", types.SimpleNamespace(client=lambda name, **kwargs: source))
    kwargs, mode = resolve_aws_session({**ACCOUNT, "role_arn": "arn:aws:iam::638631156706:role/finops/Finovaunt-RO-Scan-Role"})
    assert mode == "direct" and kwargs == {}


def test_source_role_in_different_account_must_assume_target(monkeypatch):
    source = STS("arn:aws:sts::000000000000:assumed-role/Finovaunt-RO-Scan-Role/source", assumed=True)
    target = STS("arn:aws:sts::638631156706:assumed-role/Finovaunt-RO-Scan-Role/result")
    calls = []
    def client(name, **kwargs):
        calls.append(kwargs)
        return target if kwargs.get("aws_access_key_id") else source
    monkeypatch.setitem(sys.modules, "boto3", types.SimpleNamespace(client=client))
    result, mode = resolve_aws_session(ACCOUNT, external_id="external-test")
    assert mode == "assumed"
    assert result["aws_access_key_id"] == "FAKE"
    assert source.calls[0]["ExternalId"] == "external-test"


def test_other_role_same_account_does_not_bypass_trust(monkeypatch):
    source = STS("arn:aws:sts::638631156706:assumed-role/SomeOtherRole/session")
    def denied(**kwargs):
        raise ClientError({"Error": {"Code": "AccessDenied", "Message": "secret details"}}, "AssumeRole")
    source.assume_role = denied
    monkeypatch.setitem(sys.modules, "boto3", types.SimpleNamespace(client=lambda name, **kwargs: source))
    with pytest.raises(AWSAccessError) as error:
        resolve_aws_session(ACCOUNT)
    assert error.value.stage == "assume_role"
    assert "secret details" not in str(error.value.public_payload())


def test_wrong_assumed_role_is_not_accepted(monkeypatch):
    source = STS("arn:aws:iam::638631156706:user/source", assumed=True)
    incorrect = STS("arn:aws:sts::638631156706:assumed-role/IncorrectRole/test")
    monkeypatch.setitem(sys.modules, "boto3", types.SimpleNamespace(
        client=lambda name, **kwargs: incorrect if kwargs.get("aws_access_key_id") else source
    ))
    with pytest.raises(AWSAccessError) as error:
        resolve_aws_session(ACCOUNT)
    assert error.value.stage == "verify_identity"


def test_role_in_wrong_account_is_rejected_even_for_direct_mode(monkeypatch):
    with pytest.raises(AWSAccessError) as error:
        resolve_aws_session({**ACCOUNT, "role_arn": "arn:aws:iam::000000000000:role/Finovaunt-RO-Scan-Role"})
    assert error.value.code == "InvalidRoleConfiguration"
