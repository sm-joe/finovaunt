"""Evidence-based EBS optimization, read-only pricing and Kubernetes PV checks.

Fail closed: unknown pricing or incomplete EKS PV visibility is never presented
as an actionable or verified saving. No automatic AWS/Kubernetes writes.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import re
import urllib.request
from urllib.error import HTTPError, URLError
from botocore.signers import RequestSigner


def _volume_id(text: str) -> str | None:
    match = re.search(r"vol-[a-f0-9]{8,17}", str(text), re.I)
    return match.group(0).lower() if match else None


def _is_kubernetes_volume(tags: dict) -> bool:
    return any(key.startswith(("kubernetes.io/", "ebs.csi.aws.com/", "KubernetesCluster")) or
               key in {"CSIVolumeName", "cluster.k8s.aws/cluster-name"} for key in tags) or
               any("pvc-" in str(value).lower() for value in tags.values())


def _kubernetes_refs(tags: dict) -> dict:
    return {
        "pv_name": tags.get("kubernetes.io/created-for/pv/name") or tags.get("CSIVolumeName"),
        "pvc_name": tags.get("kubernetes.io/created-for/pvc/name"),
        "pvc_namespace": tags.get("kubernetes.io/created-for/pvc/namespace"),
    }


def _prices(pricing, region: str, volume_types: set[str]) -> dict[str, dict]:
    """Fetch public AWS OnDemand Price List; accept unique verified USD GB-Mo rates."""
    results = {}
    for kind in sorted(volume_types & {"gp2", "gp3"}):
        records = []
        token = None
        for _ in range(20):
            params = {
                "ServiceCode": "AmazonEC2", "MaxResults": 100,
                "Filters": [
                    {"Type": "TERM_MATCH", "Field": "regionCode", "Value": region},
                    {"Type": "TERM_MATCH", "Field": "volumeApiName", "Value": kind},
                ],
            }
            if token:
                params["NextToken"] = token
            result = pricing.get_products(**params)
            records.extend(result.get("PriceList", []))
            token = result.get("NextToken")
            if not token:
                break
        else:
            continue  # incomplete price pagination must not produce a rate
        rates: set[Decimal] = set()
        for item in records:
            try:
                obj = json.loads(item) if isinstance(item, str) else item
                product = obj.get("product", {})
                attrs = product.get("attributes", {})
                if (product.get("productFamily") != "Storage"
                    or attrs.get("volumeApiName") != kind
                    or attrs.get("regionCode") != region):
                    continue
                usage = attrs.get("usagetype", "")
                if not re.search(r"EBS:VolumeUsage(?:\\.|$)", usage):
                    continue
                for term in obj.get("terms", {}).get("OnDemand", {}).values():
                    for dimension in term.get("priceDimensions", {}).values():
                        if dimension.get("unit") != "GB-Mo": continue
                        rate = Decimal(str(dimension["pricePerUnit"]["USD"]))
                        if rate.is_finite() and rate > 0:
                            rates.add(rate)
            except (ValueError, KeyError, TypeError, InvalidOperation):
                continue
        if len(rates) == 1:
            rate = rates.pop()
            results[kind] = {"usd_per_gb_month": str(rate), "region": region,
                             "source": "AWS Price List API / AmazonEC2 OnDemand",
                             "unit": "GB-Mo", "volume_type": kind}
    return results


def _k8s_pvs(eks, region: str, session) -> dict:
    """Query actual EKS Kubernetes APIs; never infer an absent PV from AWS tags."""
    clusters = []
    try:
        pages = eks.get_paginator("list_clusters").paginate()
        for page in pages:
            clusters.extend(page.get("clusters", []))
            if len(clusters) > 25:
                return {"status": "incomplete", "reason": "EKS cluster limit exceeded", "references": {}, "clusters_checked": 0}
    except Exception:
        return {"status": "incomplete", "reason": "EKS inventory unavailable", "references": {}, "clusters_checked": 0}
    refs: dict[str, list[dict]] = {}
    checked = 0
    # Empty native cluster list does not rule out external Kubernetes clusters.
    for name in clusters:
        try:
            cluster = eks.describe_cluster(name=name)["cluster"]
            endpoint = cluster.get("endpoint", "")
            cert = base64.b64decode(cluster["certificateAuthority"]["data"]).decode("utf-8")
            # AWS CLI-compatible EKS authentication via short-lived STS presigned URL.
            credentials = session.get_credentials().get_frozen_credentials()
            service_id = session._session.get_service_model("sts").service_id
            signer = RequestSigner(service_id, region, "sts", "v4", credentials, session._session.get_component("event_emitter"))
            presigned = signer.generate_presigned_url(
                {"method": "GET", "url": "https://sts." + region + ".amazonaws.com/?Action=GetCallerIdentity&Version=2011-06-15",
                 "body": {}, "headers": {"x-k8s-aws-id": name}, "context": {}},
                region_name=region, expires_in=60, operation_name="",
            )
            token = "k8s-aws-v1." + base64.urlsafe_b64encode(presigned.encode()).decode().rstrip("=")
            import ssl
            context = ssl.create_default_context(cadata=cert)
            # Enumerate paginated PVs, fail closed if auth/RBAC/network unavailable.
            cursor = None
            seen = set()
            while True:
                url = endpoint.rstrip("/") + "/api/v1/persistentvolumes?limit=500"
                if cursor:
                    from urllib.parse import quote
                    url += "&continue=" + quote(cursor, safe="")
                req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token, "Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=10, context=context) as response:
                    payload = json.load(response)
                for pv in payload.get("items", []):
                    spec = pv.get("spec", {})
                    csi = spec.get("csi") or {}
                    handle = csi.get("volumeHandle") if csi.get("driver") == "ebs.csi.aws.com" else ""
                    handle = handle or (spec.get("awsElasticBlockStore") or {}).get("volumeID", "")
                    volume_id = _volume_id(handle)
                    if volume_id:
                        claim = spec.get("claimRef") or {}
                        refs.setdefault(volume_id, []).append({
                            "cluster": name, "pv": pv.get("metadata", {}).get("name"),
                            "pvc": claim.get("name"), "namespace": claim.get("namespace"),
                            "pv_phase": pv.get("status", {}).get("phase"),
                            "reclaim_policy": spec.get("persistentVolumeReclaimPolicy"),
                        })
                cursor = payload.get("metadata", {}).get("continue")
                if not cursor:
                    break
                if cursor in seen:
                    raise RuntimeError("Kubernetes pagination loop")
                seen.add(cursor)
            checked += 1
        except Exception:
            return {"status": "incomplete", "reason": "EKS PV verification unavailable or forbidden", "references": refs, "clusters_checked": checked}
    return {"status": "complete" if clusters else "no_eks_clusters",
            "reason": "Kubernetes PV API queried for each discovered EKS cluster" if clusters else "No EKS clusters discovered in configured region",
            "references": refs, "clusters_checked": checked}


def enrich_ebs(assets: list[dict], *, region: str, session) -> dict:
    """Add separate cost, PV evidence, uncertainty, and review recommendations."""
    import boto3
    volumes = [item for item in assets if item.get("type") == "ebs"]
    if not volumes:
        return {"pricing_status": "not_needed", "kubernetes_status": "not_needed", "assets_enriched": 0}
    types = {str(v.get("volume_type", "")) for v in volumes}
    try:
        pricing = session.client("pricing", region_name="us-east-1")
        rates = _prices(pricing, region, types)
    except Exception:
        rates = {}
    try:
        evidence = _k8s_pvs(session.client("eks", region_name=region), region, session)
    except Exception:
        evidence = {"status": "incomplete", "reason": "Kubernetes PV lookup unavailable", "references": {}, "clusters_checked": 0}
    for asset in volumes:
        tags = asset.get("tags", {})
        k8s_tagged = _is_kubernetes_volume(tags)
        matches = evidence["references"].get(asset["id"].lower(), [])
        if matches:
            correlation = "pv_found"
        elif evidence["status"] == "complete":
            correlation = "no_pv_found_in_discovered_eks"
        else:
            correlation = "not_verified"
        rate = rates.get(asset.get("volume_type", ""))
        reasons = []
        if matches:
            reasons.append("Kubernetes PV still references the volume; preserve data and investigate PV/PVC ownership.")
        elif k8s_tagged:
            reasons.append("Kubernetes/PVC tags detected; check orphaned claims, reclaim policy and snapshot retention.")
        else:
            reasons.append("No Kubernetes ownership tags detected; verify all workload and backup dependencies.")
        if evidence["status"] != "complete":
            reasons.append("Kubernetes PV coverage is incomplete; absence of a PV is NOT verified.")
        if not rate:
            reasons.append("Verified monthly EBS storage price unavailable for this volume type and region.")
        if asset.get("volume_type") == "gp3" and (int(asset.get("iops") or 3000) > 3000 or int(asset.get("throughput") or 125) > 125):
            reasons.append("gp3 provisioned IOPS/throughput charges are additional to storage.")
        if asset.get("state") != "available":
            reasons.append("Volume is not confirmed unattached in the latest AWS inventory.")
        # A pricing estimate is a storage-only potential reduction if the
        # volume were deleted after verification, never an existing saving.
        storage = None
        if rate and asset.get("size_gib") and asset.get("state") == "available":
            storage = Decimal(str(asset["size_gib"])) * Decimal(rate["usd_per_gb_month"])
        asset["optimization_evidence"] = {
            "pricing": rate, "kubernetes": {
                "status": correlation, "discovery_status": evidence["status"],
                "clusters_checked": evidence["clusters_checked"],
                "pv_references": matches, "tags": _kubernetes_refs(tags),
            },
            "possible_monthly_storage_reduction_usd": str(storage.quantize(Decimal("0.01"))) if storage is not None else None,
            "estimated_monthly_savings_usd": None if correlation == "pv_found" else (
                str(storage.quantize(Decimal("0.01"))) if storage is not None else None
            ),
            "verified_savings_usd": None,
            "confidence": "blocked" if matches else ("low" if correlation == "not_verified" or k8s_tagged else "medium"),
            "risk": "high" if k8s_tagged or matches else "medium",
            "requires_human_approval": True, "can_auto_delete": False,
            "evidence": reasons,
            "estimated_savings_assumptions": [
                "Storage-only theoretical reduction if safely retired for an entire month",
                "AWS Price List OnDemand USD per GB-month for configured region",
                "Does not include snapshots, taxes, discounts, IOPS, throughput or minimums",
                "No AWS or Kubernetes resource has been changed",
            ],
        }
    return {"pricing_status": "partial" if len(rates) < len(types) else "collected",
            "kubernetes_status": evidence["status"], "clusters_checked": evidence["clusters_checked"],
            "assets_enriched": len(volumes)}
