"""Kubernetes metric parsing, namespace samples and endpoint safety."""
import base64
from decimal import Decimal
import pytest

from src.tools import eks_usage


def test_kubernetes_cpu_and_memory_units_are_converted_exactly():
    assert eks_usage.cpu_millicores("500m") == Decimal("500")
    assert eks_usage.cpu_millicores("100000000n") == Decimal("100")
    assert eks_usage.cpu_millicores("2") == Decimal("2000")
    assert eks_usage.memory_mib("1024Ki") == Decimal("1")
    assert eks_usage.memory_mib("2Gi") == Decimal("2048")
    assert eks_usage.memory_mib("1048576") == Decimal("1")
    with pytest.raises(ValueError):
        eks_usage.cpu_millicores("abc")
    with pytest.raises(ValueError):
        eks_usage.memory_mib("-2Gi")


def test_namespace_usage_is_metrics_only_and_not_billed_cost(monkeypatch):
    monkeypatch.setattr(eks_usage, "_eks_token", lambda *args, **kwargs: "test-token")
    monkeypatch.setattr(eks_usage, "_load_pages", lambda **kwargs: [{
        "items": [
            {"metadata": {"namespace": "engineering"}, "containers": [
                {"usage": {"cpu": "150m", "memory": "128Mi"}},
                {"usage": {"cpu": "0.1", "memory": "64Mi"}},
            ]},
            {"metadata": {"namespace": "engineering"}, "containers": [
                {"usage": {"cpu": "100m", "memory": "256Mi"}},
            ]},
            {"metadata": {"namespace": "finance"}, "containers": [
                {"usage": {"cpu": "50m", "memory": "32Mi"}},
            ]},
        ]
    }])
    result = eks_usage.collect_namespace_usage({
        "endpoint": "https://example.eks.amazonaws.com",
        "certificateAuthority": {"data": base64.b64encode(b"cert").decode()},
    }, name="demo-eks", region="us-east-1", session=object())
    assert result["status"] == "collected"
    assert result["namespace_costs"] is None
    assert result["coverage"] == "observed_pods_only"
    ns = next(x for x in result["namespaces"] if x["namespace"] == "engineering")
    assert ns["pods_sampled"] == 2
    assert ns["cpu_millicores_sampled"] == "350.0"
    assert ns["memory_mib_sampled"] == "448.00"
    assert ns["cost_usd"] is None


def test_unapproved_kubernetes_endpoints_are_rejected_before_http():
    with pytest.raises(ValueError, match="Only an AWS EKS HTTPS"):
        eks_usage._load_pages(endpoint="http://127.0.0.1:8000",
                              token="secret", certificate="untrusted")
    with pytest.raises(ValueError, match="Only an AWS EKS HTTPS"):
        eks_usage._load_pages(endpoint="https://evil.example",
                              token="secret", certificate="untrusted")


def test_missing_cluster_rbac_or_metrics_do_not_produce_zero_usage(monkeypatch):
    monkeypatch.setattr(eks_usage, "_eks_token", lambda *args, **kwargs: "test-token")
    def failed(**kwargs):
        raise PermissionError("no cluster metrics RBAC")
    monkeypatch.setattr(eks_usage, "_load_pages", failed)
    result = eks_usage.collect_namespace_usage({
        "endpoint": "https://demo.eks.amazonaws.com",
        "certificateAuthority": {"data": base64.b64encode(b"cert").decode()},
    }, name="demo", region="us-east-1", session=object())
    assert result["status"] == "not_assessed"
    assert result["namespace_costs"] is None
    assert result["namespaces"] == []
