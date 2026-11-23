"""Read-only EKS namespace CPU/memory samples via Kubernetes Metrics API.

This does NOT determine Kubernetes cost. Calls EKS kube-apiserver directly
with AWS-signed short-lived token and verified cluster certificate.
"""
from __future__ import annotations

import base64
from collections import defaultdict
from decimal import Decimal, InvalidOperation
import json
import re
import ssl
from urllib.parse import quote, urlparse
import urllib.request

from botocore.signers import RequestSigner


_CPU = re.compile(r"^([0-9]+(?:\.[0-9]+)?)(n|u|m|)?$")
_MEMORY = re.compile(r"^([0-9]+(?:\.[0-9]+)?)(Ki|Mi|Gi|Ti|K|M|G|T|)?$")
_CPU_MULTIPLIER = {"n": Decimal("0.000001"), "u": Decimal("0.001"), "m": Decimal("1"), "": Decimal("1000")}
_MEMORY_MULTIPLIER = {"Ki": Decimal(1) / (1024 * 1024),
                      "Mi": Decimal(1) / 1024, "Gi": Decimal(1), "Ti": Decimal(1024),
                      "K": Decimal(1000) / (1024 ** 3), "M": Decimal(1000000) / (1024 ** 3),
                      "G": Decimal(1000000000) / (1024 ** 3), "T": Decimal(1000000000000) / (1024 ** 3),
                      "": Decimal(1) / (1024 ** 3)}


def cpu_millicores(value: str) -> Decimal:
    match = _CPU.fullmatch(str(value))
    if not match:
        raise ValueError("Invalid Kubernetes CPU quantity.")
    return Decimal(match.group(1)) * _CPU_MULTIPLIER[match.group(2)]


def memory_mib(value: str) -> Decimal:
    match = _MEMORY.fullmatch(str(value))
    if not match:
        raise ValueError("Invalid Kubernetes memory quantity.")
    # Multipliers above are in GiB; report MiB.
    return Decimal(match.group(1)) * _MEMORY_MULTIPLIER[match.group(2)] * 1024


def _eks_token(session, *, cluster: str, region: str) -> str:
    credentials = session.get_credentials().get_frozen_credentials()
    service_id = session._session.get_service_model("sts").service_id
    signer = RequestSigner(service_id, region, "sts", "v4", credentials,
                           session._session.get_component("event_emitter"))
    presigned = signer.generate_presigned_url(
        {"method": "GET",
         "url": f"https://sts.{region}.amazonaws.com/?Action=GetCallerIdentity&Version=2011-06-15",
         "body": {}, "headers": {"x-k8s-aws-id": cluster}, "context": {}},
        region_name=region, expires_in=60, operation_name="")
    return "k8s-aws-v1." + base64.urlsafe_b64encode(presigned.encode()).decode().rstrip("=")


def _load_pages(*, endpoint: str, token: str, certificate: str) -> list[dict]:
    host = urlparse(endpoint)
    if (host.scheme != "https" or not host.hostname or host.username or host.password
            or not (host.hostname.endswith(".eks.amazonaws.com")
                    or host.hostname.endswith(".eks.amazonaws.com.cn"))):
        raise ValueError("Only an AWS EKS HTTPS cluster endpoint may receive signed credentials.")
    context = ssl.create_default_context(cadata=certificate)
    seen = set()
    cursor = ""
    pages = []
    for _ in range(20):
        url = endpoint.rstrip("/") + "/apis/metrics.k8s.io/v1beta1/pods?limit=500"
        if cursor:
            url += "&continue=" + quote(cursor, safe="")
        req = urllib.request.Request(url, headers={
            "Authorization": "Bearer " + token, "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=10, context=context) as response:
            payload = json.load(response)
        if not isinstance(payload.get("items"), list):
            raise ValueError("Kubernetes pod metrics response has no items.")
        pages.append(payload)
        cursor = str(payload.get("metadata", {}).get("continue") or "")
        if not cursor:
            return pages
        if cursor in seen:
            raise ValueError("Kubernetes pagination token repeated.")
        seen.add(cursor)
    raise ValueError("Kubernetes pod metrics pagination limit exceeded.")


def collect_namespace_usage(cluster: dict, *, name: str, region: str, session) -> dict:
    endpoint = str(cluster.get("endpoint") or "")
    authority = cluster.get("certificateAuthority") or {}
    encoded = authority.get("data")
    if not endpoint or not encoded:
        return {"status": "not_assessed", "reason": "EKS endpoint or CA not available.",
                "namespace_costs": None, "namespaces": []}
    try:
        certificate = base64.b64decode(encoded, validate=True).decode("utf-8")
        token = _eks_token(session, cluster=name, region=region)
        pages = _load_pages(endpoint=endpoint, token=token, certificate=certificate)
        usage = defaultdict(lambda: {"cpu_millicores": Decimal("0"),
                                     "memory_mib": Decimal("0"), "pods_sampled": 0})
        for page in pages:
            for pod in page["items"]:
                namespace = str(pod.get("metadata", {}).get("namespace") or "")
                if not namespace:
                    continue
                containers = pod.get("containers", [])
                if not isinstance(containers, list):
                    raise ValueError("Invalid Kubernetes containers data.")
                cpu = Decimal("0")
                memory = Decimal("0")
                for container in containers:
                    metrics = container.get("usage") or {}
                    cpu += cpu_millicores(str(metrics["cpu"]))
                    memory += memory_mib(str(metrics["memory"]))
                usage[namespace]["cpu_millicores"] += cpu
                usage[namespace]["memory_mib"] += memory
                usage[namespace]["pods_sampled"] += 1
        return {"status": "collected", "source": "kubernetes_metrics_api",
                "namespace_costs": None, "coverage": "observed_pods_only",
                "namespaces": [{"namespace": namespace,
                    "cpu_millicores_sampled": str(sample["cpu_millicores"]),
                    "memory_mib_sampled": str(sample["memory_mib"].quantize(Decimal("0.01"))),
                    "pods_sampled": sample["pods_sampled"],
                    "cost_usd": None}
                    for namespace, sample in sorted(usage.items())],
                "notes": ["Point-in-time pod usage sample; not requests, limits, node cost or billed spend.",
                          "Namespace cost allocation requires verified infrastructure costs and a shared-cost model."]}
    except Exception:
        return {"status": "not_assessed",
                "reason": "Kubernetes Metrics API, authentication, CA, RBAC or network unavailable.",
                "namespace_costs": None, "namespaces": []}
