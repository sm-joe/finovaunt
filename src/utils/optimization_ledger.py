"""Evidence ledger for EBS optimization candidates across persisted real AWS scans.

No inferred deletion or financial outcome: absent from a complete same-region
inventory is only 'not_observed', never proof of volume deletion or savings.
"""
from __future__ import annotations
from datetime import datetime, timezone


def update_ledger(ledger: list[dict], account_id: str, scan: dict) -> list[dict]:
    region = str(scan.get("region") or "")
    scanned_at = str(scan.get("scanned_at") or datetime.now(timezone.utc).isoformat())
    scan_id = str(scan["id"])
    complete = scan.get("status") in {"success", "empty_inventory"} and scan.get("truncated") is False
    # Missing/older collectors can omit truncated; do NOT infer completeness.
    previous = {(r["account_id"], r["region"], r["resource_id"]): dict(r)
                for r in ledger if all(k in r for k in ("account_id", "region", "resource_id"))}
    current = {}
    for volume in scan.get("assets", []):
        if volume.get("type") != "ebs":
            continue
        volume_id = str(volume.get("id", ""))
        if not volume_id:
            continue
        current[volume_id] = volume
        key = (account_id, region, volume_id)
        prior = previous.get(key)
        state = str(volume.get("state", "unknown"))
        if prior is None and state != "available":
            continue  # history focuses on observed optimization candidates only
        evidence = volume.get("optimization_evidence") or {}
        if prior is None:
            prior = {
                "account_id": account_id, "region": region, "resource_id": volume_id,
                "first_seen_at": scanned_at, "first_scan_id": scan_id,
                "observations": 0, "savings_verified_usd": None,
            }
        prior.update({
            "name": str(volume.get("name", volume_id)),
            "last_seen_at": scanned_at, "last_scan_id": scan_id,
            "last_observed_state": state,
            "lifecycle": "candidate_observed" if state == "available" else "no_longer_unattached",
            "latest_evidence": {
                "size_gib": volume.get("size_gib"),
                "volume_type": volume.get("volume_type"),
                "pricing": evidence.get("pricing"),
                "potential_storage_reduction_usd": evidence.get("possible_monthly_storage_reduction_usd"),
                "estimated_savings_usd": evidence.get("estimated_monthly_savings_usd"),
                "confidence": evidence.get("confidence"),
                "risk": evidence.get("risk"),
                "kubernetes": evidence.get("kubernetes"),
            },
            "observations": int(prior.get("observations", 0)) + 1,
            "savings_verified_usd": None,
        })
        previous[key] = prior
    if complete and region:
        for key, item in previous.items():
            if key[0] == account_id and key[1] == region and key[2] not in current:
                item["lifecycle"] = "not_observed_in_latest_complete_scan"
                item["last_checked_at"] = scanned_at
                item["last_checked_scan_id"] = scan_id
                # Keep the previous price quote as historic evidence only;
                # never turn a missing resource into verified savings.
    elif region:
        for key, item in previous.items():
            if key[0] == account_id and key[1] == region and key[2] not in current:
                item["lifecycle"] = "current_scan_incomplete"
                item["last_checked_at"] = scanned_at
                item["last_checked_scan_id"] = scan_id
    return sorted(previous.values(), key=lambda item: (item["account_id"], item["region"], item["resource_id"]))
