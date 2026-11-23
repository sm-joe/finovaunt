"""Read-only AWS inventory contract and account-isolation tests."""
import sys
import types

import pytest

from src.tools.inventory_service import collect_inventory, InventoryCollectionError

ACCOUNT = {
    "account_id": "123456789012",
    "role_arn": "arn:aws:iam::123456789012:role/ReadOnly",
    "region": "eu-central-1",
}


class FakePaginator:
    def __init__(self, pages):
        self.pages = pages

    def paginate(self):
        return self.pages


class FakeEC2:
    def get_paginator(self, operation):
        if operation == "describe_instances":
            return FakePaginator([{"Reservations": [{"Instances": [
                {"InstanceId": "i-test", "State": {"Name": "running"}, "InstanceType": "t3.micro",
                 "Tags": [{"Key": "Name", "Value": "worker"}]},
            ]}]}])
        assert operation == "describe_volumes"
        return FakePaginator([{"Volumes": [
            {"VolumeId": "vol-test", "State": "available", "Size": 20, "VolumeType": "gp3"},
        ]}])


class FakeRDS:
    def get_paginator(self, operation):
        assert operation == "describe_db_instances"
        return FakePaginator([{"DBInstances": [{
            "DBInstanceIdentifier": "db-test", "DBInstanceStatus": "available", "DBInstanceClass": "db.t3.micro",
        }]}])


class FakeSTS:
    def __init__(self, mismatch=False):
        self.mismatch = mismatch

    def assume_role(self, **kwargs):
        return {"Credentials": {"AccessKeyId": "fake", "SecretAccessKey": "fake", "SessionToken": "fake"}}

    def get_caller_identity(self):
        return {"Account": "999999999999" if self.mismatch else "123456789012"}


def test_inventory_detects_ec2_rds_ebs_without_savings(monkeypatch):
    def client(service, *, region_name, **kwargs):
        assert region_name == "eu-central-1"
        return {"ec2": FakeEC2(), "rds": FakeRDS(), "sts": FakeSTS()}[service]
    monkeypatch.setitem(sys.modules, "boto3", types.SimpleNamespace(client=client))
    result = collect_inventory(ACCOUNT)
    assert result["asset_count"] == 3
    assert {item["type"] for item in result["assets"]} == {"ec2", "rds", "ebs"}
    assert result["savings_estimated"] is False
    volume = next(item for item in result["assets"] if item["type"] == "ebs")
    assert volume["recommendation"] == "review_only"


def test_inventory_rejects_wrong_account_role():
    with pytest.raises(InventoryCollectionError):
        collect_inventory({**ACCOUNT, "role_arn": "arn:aws:iam::999999999999:role/Other"})


def test_inventory_respects_resource_cap(monkeypatch):
    def client(service, *, region_name, **kwargs):
        return {"ec2": FakeEC2(), "rds": FakeRDS(), "sts": FakeSTS()}[service]
    monkeypatch.setitem(sys.modules, "boto3", types.SimpleNamespace(client=client))
    result = collect_inventory(ACCOUNT, max_assets=1)
    assert result["asset_count"] == 1
    assert result["truncated"] is True
    assert result["status"] == "partial"
    assert result["observed_counts"] == {"ebs": 1, "ec2": 1, "rds": 1}
    assert result["collected_counts"] == {"ebs": 1, "ec2": 0, "rds": 0}
    assert result["observed_total"] == 3
    assert result["assets"][0]["type"] == "ebs"


def test_complete_inventory_reports_explicit_type_coverage(monkeypatch):
    def client(service, *, region_name, **kwargs):
        return {"ec2": FakeEC2(), "rds": FakeRDS(), "sts": FakeSTS()}[service]
    monkeypatch.setitem(sys.modules, "boto3", types.SimpleNamespace(client=client))
    result = collect_inventory(ACCOUNT)
    assert result["truncated"] is False
    assert result["observed_counts"] == {"ebs": 1, "ec2": 1, "rds": 1}
    assert result["collected_counts"] == result["observed_counts"]
    assert result["resource_cap"] == 500
