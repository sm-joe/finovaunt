"""Cost Explorer collection contract tests: paging, precision and account isolation."""
from datetime import date
from decimal import Decimal
import sys
import types

import pytest

from src.tools.billing_service import BillingCollectionError, collect_billing

ACCOUNT = {
    "account_id": "123456789012",
    "role_arn": "arn:aws:iam::123456789012:role/FinovauntReadOnly",
    "region": "eu-central-1",
}


class FakeSts:
    def __init__(self, assumed=False, identity="123456789012"):
        self.assumed = assumed
        self.identity = identity

    def assume_role(self, **kwargs):
        assert kwargs["RoleArn"] == ACCOUNT["role_arn"]
        return {"Credentials": {"AccessKeyId": "fake", "SecretAccessKey": "fake", "SessionToken": "fake"}}

    def get_caller_identity(self):
        return {"Account": self.identity, "Arn": (f"arn:aws:sts::{self.identity}:assumed-role/FinovauntReadOnly/test" if self.assumed else f"arn:aws:iam::{self.identity}:user/source") }


class FakeCe:
    def __init__(self):
        self.requests = []

    def get_cost_and_usage(self, **kwargs):
        self.requests.append(kwargs)
        assert kwargs["TimePeriod"] == {"Start": "2026-11-01", "End": "2026-11-24"}
        if "NextPageToken" not in kwargs:
            return {
                "ResultsByTime": [{"Groups": [{
                    "Keys": ["Amazon EC2"],
                    "Metrics": {"UnblendedCost": {"Amount": "0.100000001", "Unit": "USD"}},
                }]}],
                "NextPageToken": "next",
            }
        assert kwargs["NextPageToken"] == "next"
        return {"ResultsByTime": [{"Groups": [{
            "Keys": ["Amazon EC2"],
            "Metrics": {"UnblendedCost": {"Amount": "0.200000002", "Unit": "USD"}},
        }, {
            "Keys": ["Amazon S3"],
            "Metrics": {"UnblendedCost": {"Amount": "1.125000001", "Unit": "USD"}},
        }]}]}


def test_billing_uses_all_pages_and_preserves_exact_amounts(monkeypatch):
    ce = FakeCe()
    def client(name, *, region_name, **kwargs):
        if name == "ce":
            assert region_name == "us-east-1"
            return ce
        assert name == "sts"
        return FakeSts(assumed=bool(kwargs))
    monkeypatch.setitem(sys.modules, "boto3", types.SimpleNamespace(client=client))
    result = collect_billing(ACCOUNT, today=date(2026, 11, 23), external_id="test-only-id")
    assert len(ce.requests) == 2
    assert all(x["Filter"]["Dimensions"] == {"Key": "LINKED_ACCOUNT", "Values": ["123456789012"]} for x in ce.requests)
    assert result["pages_collected"] == 2
    assert result["total_cost_exact"] == "1.425000004"
    assert result["total_cost"] == 1.43
    assert result["is_final"] is False
    assert result["resource_attribution"] == "not_available"
    assert result["services"][0]["amount_exact"] == "0.300000003"
    assert Decimal(result["total_cost_exact"]) == sum(
        (Decimal(item["amount_exact"]) for item in result["services"]), Decimal("0")
    )


def test_onboarded_role_must_belong_to_same_account(monkeypatch):
    with pytest.raises(BillingCollectionError, match="does not match"):
        collect_billing({**ACCOUNT, "role_arn": "arn:aws:iam::999999999999:role/Other"})


def test_assumed_identity_must_match_onboarded_account(monkeypatch):
    def client(name, *, region_name, **kwargs):
        return FakeSts(assumed=bool(kwargs), identity="999999999999")
    monkeypatch.setitem(sys.modules, "boto3", types.SimpleNamespace(client=client))
    from src.tools.aws_errors import AWSAccessError
    with pytest.raises(AWSAccessError, match="RoleMismatch"):
        collect_billing(ACCOUNT)
