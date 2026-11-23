"""AWS FinOps evidence contracts, error boundaries and read-only scheduling."""
from datetime import datetime, timezone
from decimal import Decimal
import sys
import types

import pytest

from src.tools import finops_core
from src.tools.nonprod_scheduling import validate_shutdown_policy, evaluate_shutdown_window


def test_cost_allocation_preserves_exact_tagged_and_unallocated_spend(monkeypatch):
    calls = []
    class CE:
        def get_cost_and_usage(self, **params):
            calls.append(params)
            key = params["GroupBy"][0]["Key"]
            assert params["Filter"]["Dimensions"] == {"Key": "LINKED_ACCOUNT", "Values": ["123456789012"]}
            dimension_key = "us-east-1" if key == "REGION" else key + "$Engineering"
            return {"ResultsByTime": [{"Groups": [
                {"Keys": [dimension_key],
                 "Metrics": {"UnblendedCost": {"Amount": "10.1200000001", "Unit": "USD"}}},
                {"Keys": ["" if key == "REGION" else key + "$"],
                 "Metrics": {"UnblendedCost": {"Amount": "2.2", "Unit": "USD"}}},
            ]}]}
    monkeypatch.setattr(finops_core, "_client", lambda service, region, creds: CE())
    result = finops_core.collect_cost_allocation({}, account_id="123456789012",
        now=datetime(2026, 11, 23, tzinfo=timezone.utc))
    assert len(calls) == 4
    assert result["allocation"]["region"]["groups"][0]["name"] == "Unallocated"
    assert any(group["name"] == "us-east-1" for group in result["allocation"]["region"]["groups"])
    assert result["period_start"] == "2026-11-01"
    assert result["allocation"]["team"]["groups"][0]["cost_exact"] == "10.1200000001"
    assert result["allocation"]["team"]["unallocated_cost_exact"] == "2.2"
    assert sum((Decimal(x["cost_exact"]) for x in result["allocation"]["team"]["groups"]), Decimal("0")) == Decimal("12.3200000001")


def test_aws_finops_partial_coverage_never_invents_zero_cost(monkeypatch):
    monkeypatch.setattr(finops_core, "resolve_aws_session", lambda account, **kwargs: ({}, "direct"))
    monkeypatch.setattr(finops_core, "collect_cost_allocation", lambda credentials: (_ for _ in ()).throw(PermissionError()))
    monkeypatch.setattr(finops_core, "collect_rightsizing", lambda account, credentials: {"findings": []})
    monkeypatch.setattr(finops_core, "collect_s3", lambda account, credentials: {"buckets": []})
    monkeypatch.setattr(finops_core, "collect_eks", lambda account, credentials: {"clusters": []})
    monkeypatch.setattr(finops_core, "collect_budgets", lambda account, credentials: {"budgets": []})
    result = finops_core.assess_aws_finops({
        "account_id": "123456789012", "region": "us-east-1",
        "role_arn": "arn:aws:iam::123456789012:role/ReadOnly",
    })
    assert result["status"] == "partial"
    assert result["sections"]["cost_allocation"]["status"] == "not_assessed"
    assert "evidence" not in result["sections"]["cost_allocation"]
    assert result["realized_savings_usd"] is None
    assert result["automated_actions_performed"] == 0


def test_s3_bucket_cost_not_invented_from_storage_bytes(monkeypatch):
    class S3:
        def list_buckets(self):
            return {"Buckets": [{"Name": "team-data"}]}
        def get_bucket_location(self, **kwargs):
            return {"LocationConstraint": None}
        def get_bucket_tagging(self, **kwargs):
            return {"TagSet": [{"Key": "Team", "Value": "Engineering"}]}
    monkeypatch.setattr(finops_core, "_client",
        lambda service, region, creds: S3() if service == "s3" else object())
    monkeypatch.setattr(finops_core, "_cw_values", lambda *args, **kwargs: [1024.0])
    output = finops_core.collect_s3({"region": "us-east-1"}, {})
    bucket = output["buckets"][0]
    assert bucket["tags"]["Team"] == "Engineering"
    assert bucket["storage_bytes"] == 1024.0
    assert bucket["cost_usd"] is None
    assert bucket["cost_attribution_status"] == "requires_cur_or_data_export"


def test_eks_discovery_requires_real_workload_evidence(monkeypatch):
    class Paginator:
        def paginate(self):
            return [{"clusters": ["sample"]}]
    class EKS:
        def get_paginator(self, name):
            assert name == "list_clusters"
            return Paginator()
        def describe_cluster(self, *, name):
            return {"cluster": {"arn": "arn:aws:eks:us-east-1:123456789012:cluster/sample",
                                "status": "ACTIVE", "version": "1.35"}}
    monkeypatch.setattr(finops_core, "_client", lambda *args: EKS())
    output = finops_core.collect_eks({"region": "us-east-1"}, {})
    assert output["clusters"][0]["namespace_costs"] is None
    assert output["clusters"][0]["allocation_status"] == "requires_verified_cluster_cost_and_shared_cost_model"


def test_disabled_nonproduction_schedule_cannot_execute_changes():
    policy = {"enabled": False, "service": "ec2",
              "tag_key": "Environment", "tag_value": "dev",
              "timezone": "UTC", "shutdown_local": "19:00",
              "startup_local": "08:00", "weekends": True}
    valid = validate_shutdown_policy(policy)
    assert valid["execution_mode"] == "planning_only"
    evaluated = evaluate_shutdown_window(policy,
        now=datetime(2026, 11, 22, 12, 0, tzinfo=timezone.utc))
    assert evaluated["desired_state"] == "stopped"
    assert evaluated["execution_performed"] is False
    with pytest.raises(ValueError, match="disabled"):
        validate_shutdown_policy({**policy, "enabled": True})
    with pytest.raises(ValueError, match="non-production"):
        validate_shutdown_policy({**policy, "tag_value": "production"})
    with pytest.raises(ValueError, match="EC2"):
        validate_shutdown_policy({**policy, "service": "rds"})


def test_rightsizing_requires_utilization_and_never_auto_resizes(monkeypatch):
    class Pager:
        def __init__(self, pages):
            self.pages = pages
        def paginate(self):
            return self.pages
    class EC2:
        def get_paginator(self, name):
            return Pager([{"Reservations": [{"Instances": [{
                "InstanceId": "i-example", "State": {"Name": "running"},
                "InstanceType": "m5.large",
            }]}]}])
    class RDS:
        def get_paginator(self, name):
            return Pager([{"DBInstances": []}])
    def client(service, region, credentials):
        return {"ec2": EC2(), "rds": RDS(), "cloudwatch": object()}[service]
    monkeypatch.setattr(finops_core, "_client", client)
    monkeypatch.setattr(finops_core, "_cw_values", lambda *args, **kwargs: [3.0] * 8)
    report = finops_core.collect_rightsizing({"region": "us-east-1"}, {})
    assert report["findings"][0]["status"] == "review_low_cpu"
    assert report["findings"][0]["estimated_monthly_savings_usd"] is None
    assert report["findings"][0]["approval_required"] is True
