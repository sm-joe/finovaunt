"""EBS optimization: real Price List rates and Kubernetes PV safety contracts."""
import json

from src.tools.ebs_optimization import _prices, _volume_id, enrich_ebs


class PriceList:
    def get_products(self, **kwargs):
        kind = next(x["Value"] for x in kwargs["Filters"] if x["Field"] == "volumeApiName")
        region = next(x["Value"] for x in kwargs["Filters"] if x["Field"] == "regionCode")
        return {"PriceList": [json.dumps({
            "product": {
                "productFamily": "Storage",
                "attributes": {"volumeApiName": kind, "regionCode": region,
                               "usagetype": "USE1-EBS:VolumeUsage." + kind},
            },
            "terms": {"OnDemand": {"offer": {"priceDimensions": {
                "storage": {"unit": "GB-Mo", "pricePerUnit": {
                    "USD": "0.08" if kind == "gp3" else "0.10",
                }},
            }}}},
        })]}


def test_price_list_matches_region_volume_and_storage_only():
    prices = _prices(PriceList(), "us-east-1", {"gp3", "gp2", "io2"})
    assert prices["gp3"]["usd_per_gb_month"] == "0.08"
    assert prices["gp2"]["usd_per_gb_month"] == "0.10"
    assert "io2" not in prices


def test_price_list_missing_or_mixed_rates_is_not_guessed():
    class NoPrices:
        def get_products(self, **kwargs):
            return {"PriceList": []}
    assert _prices(NoPrices(), "us-east-1", {"gp3"}) == {}


def test_aws_ebs_volume_id_extracted_from_kubernetes_handle():
    assert _volume_id("aws://us-east-1a/vol-0c3f82dcff34589ab") == "vol-0c3f82dcff34589ab"
    assert _volume_id("unrelated") is None


def _session():
    class Session:
        def client(self, service, region_name):
            if service == "pricing": return PriceList()
            if service == "eks": return object()
            raise AssertionError(service)
    return Session()


def test_unattached_gp3_hypothetical_savings_are_not_verified(monkeypatch):
    from src.tools import ebs_optimization as module
    monkeypatch.setattr(module, "_k8s_pvs", lambda *args: {
        "status": "complete", "references": {}, "clusters_checked": 1,
    })
    items = [{
        "id": "vol-0c3f82dcff34589ab", "type": "ebs", "state": "available",
        "size_gib": 100, "volume_type": "gp3", "tags": {}, "iops": 3000,
        "throughput": 125,
    }]
    result = enrich_ebs(items, region="us-east-1", session=_session())
    ev = items[0]["optimization_evidence"]
    assert result["pricing_status"] == "collected"
    assert ev["estimated_monthly_savings_usd"] == "8.00"
    assert ev["verified_savings_usd"] is None
    assert ev["can_auto_delete"] is False
    assert ev["requires_human_approval"] is True


def test_eks_pv_association_blocks_estimate_even_with_real_price(monkeypatch):
    from src.tools import ebs_optimization as module
    monkeypatch.setattr(module, "_k8s_pvs", lambda *args: {
        "status": "complete", "clusters_checked": 1,
        "references": {"vol-0c3f82dcff34589ab": [{
            "cluster": "demo-eks", "pv": "pvc-123", "pvc": "work",
            "namespace": "default", "reclaim_policy": "Retain",
        }]},
    })
    items = [{
        "id": "vol-0c3f82dcff34589ab", "type": "ebs", "state": "available",
        "size_gib": 100, "volume_type": "gp3",
        "tags": {"kubernetes.io/created-for/pvc/name": "work"},
    }]
    enrich_ebs(items, region="us-east-1", session=_session())
    ev = items[0]["optimization_evidence"]
    assert ev["kubernetes"]["status"] == "pv_found"
    assert ev["estimated_monthly_savings_usd"] is None
    assert ev["possible_monthly_storage_reduction_usd"] == "8.00"
    assert ev["risk"] == "high"


def test_incomplete_eks_evidence_is_marked_unverified(monkeypatch):
    from src.tools import ebs_optimization as module
    monkeypatch.setattr(module, "_k8s_pvs", lambda *args: {
        "status": "incomplete", "references": {}, "clusters_checked": 0,
    })
    items = [{
        "id": "vol-0c3f82dcff34589ab", "type": "ebs", "state": "available",
        "size_gib": 50, "volume_type": "gp3",
        "tags": {"kubernetes.io/created-for/pvc/name": "legacy"},
    }]
    enrich_ebs(items, region="us-east-1", session=_session())
    ev = items[0]["optimization_evidence"]
    assert ev["kubernetes"]["status"] == "not_verified"
    assert ev["confidence"] == "low"
    assert ev["estimated_monthly_savings_usd"] is None
    assert ev["possible_monthly_storage_reduction_usd"] == "4.00"
    assert ev["risk"] == "high"
    assert ev["can_auto_delete"] is False
