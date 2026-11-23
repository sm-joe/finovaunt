"""Historical candidate lifecycle never infers volume deletion or savings."""
from src.utils.optimization_ledger import update_ledger


def scan(scan_id, assets, *, region="us-east-1", truncated=False, status="success"):
    return {"id": scan_id, "region": region, "scanned_at": "2026-11-23T12:00:00+00:00",
            "assets": assets, "truncated": truncated, "status": status}


def volume(state="available"):
    return {"id": "vol-0c3f82dcff34589ab", "name": "demo-eks-pvc", "type": "ebs",
            "state": state, "size_gib": 25, "volume_type": "gp3",
            "optimization_evidence": {
                "possible_monthly_storage_reduction_usd": "2.00",
                "estimated_monthly_savings_usd": None,
            }}


def test_candidate_persists_when_no_longer_observed_in_complete_inventory():
    initial = update_ledger([], "123456789012", scan("one", [volume()]))
    assert initial[0]["lifecycle"] == "candidate_observed"
    assert initial[0]["savings_verified_usd"] is None
    later = update_ledger(initial, "123456789012", scan("two", [], status="empty_inventory"))
    assert len(later) == 1
    assert later[0]["lifecycle"] == "not_observed_in_latest_complete_scan"
    assert later[0]["latest_evidence"]["potential_storage_reduction_usd"] == "2.00"
    assert later[0]["savings_verified_usd"] is None
    assert later[0]["first_scan_id"] == "one"
    assert later[0]["last_checked_scan_id"] == "two"


def test_truncated_scan_never_claims_absence():
    previous = update_ledger([], "123456789012", scan("one", [volume()]))
    current = update_ledger(previous, "123456789012", scan("two", [], truncated=True, status="partial"))
    assert current[0]["lifecycle"] == "current_scan_incomplete"
    assert current[0]["savings_verified_usd"] is None


def test_attached_volume_is_not_a_deletion():
    previous = update_ledger([], "123456789012", scan("one", [volume()]))
    updated = update_ledger(previous, "123456789012", scan("two", [volume("in-use")]))
    assert updated[0]["lifecycle"] == "no_longer_unattached"
    assert updated[0]["observations"] == 2


def test_account_and_region_boundaries_are_respected():
    previous = update_ledger([], "123456789012", scan("one", [volume()]))
    other = update_ledger(previous, "999999999999", scan("two", [], status="empty_inventory"))
    assert other[0]["lifecycle"] == "candidate_observed"
    other = update_ledger(previous, "123456789012", scan("two", [], region="eu-west-1", status="empty_inventory"))
    assert other[0]["lifecycle"] == "candidate_observed"


def test_unknown_completeness_does_not_assume_deleted():
    previous = update_ledger([], "123456789012", scan("one", [volume()]))
    updated = update_ledger(previous, "123456789012", {
        "id": "legacy", "region": "us-east-1", "scanned_at": "2026-11-23", "status": "success",
        "assets": [],
    })
    assert updated[0]["lifecycle"] == "current_scan_incomplete"
