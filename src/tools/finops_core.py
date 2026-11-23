"""AWS-only FinOps assessment: billing tags, EC2/RDS, S3, EKS, budgets.

The entire collector is read-only. Recommendations are review-only and do
not claim savings without attributable billing and utilization evidence.
Individual integration failures remain explicitly NOT_ASSESSED.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from src.tools.aws_identity import resolve_aws_session
from src.tools.aws_errors import aws_call, aws_pages

TAG_KEYS = ("Team", "Project", "Environment")
MAX_CLUSTER_RESULTS = 200
MAX_BUCKET_RESULTS = 1000


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _client(service: str, region: str, credentials: dict):
    import boto3
    return boto3.client(service, region_name=region, **credentials)


def _amount(raw: Any) -> Decimal:
    try:
        amount = Decimal(str(raw))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("AWS returned an invalid billing amount.") from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError("AWS returned an invalid billing amount.")
    return amount


def _ce_pages(client, query: dict) -> list[dict]:
    pages = []
    token = None
    seen = set()
    for _ in range(100):
        request = dict(query)
        if token:
            request["NextPageToken"] = token
        response = aws_call("cost_explorer", client.get_cost_and_usage, **request)
        pages.append(response)
        token = response.get("NextPageToken")
        if not token:
            return pages
        if not isinstance(token, str) or token in seen:
            raise ValueError("Cost Explorer pagination token is invalid.")
        seen.add(token)
    raise ValueError("Cost Explorer pagination exceeded the safe limit.")


def collect_cost_allocation(credentials: dict, *, now: datetime | None = None) -> dict:
    """Aggregate tag spend using Cost Explorer (no invented resource attribution).

    AWS requires activation of user-defined cost allocation tags, and tags
    absent from cost records are grouped as unallocated.
    """
    current = now or _utc_now()
    start = current.date().replace(day=1).isoformat()
    end = (current.date() + timedelta(days=1)).isoformat()
    ce = _client("ce", "us-east-1", credentials)
    output = {}
    for key in TAG_KEYS:
        query = {
            "TimePeriod": {"Start": start, "End": end},
            "Granularity": "MONTHLY", "Metrics": ["UnblendedCost"],
            "GroupBy": [{"Type": "TAG", "Key": key}],
        }
        groups: dict[str, Decimal] = {}
        currency = None
        page_count = 0
        for page in _ce_pages(ce, query):
            page_count += 1
            for period in page.get("ResultsByTime", []):
                for group in period.get("Groups", []):
                    raw = str((group.get("Keys") or [""])[0])
                    # CE returns TAG grouping as Key$Value or Key$ for absent tags.
                    value = raw.split("$", 1)[1] if raw.startswith(key + "$") else ""
                    name = value.strip() or "Unallocated"
                    metric = group.get("Metrics", {}).get("UnblendedCost", {})
                    unit = str(metric.get("Unit", "USD"))
                    if currency is not None and unit != currency:
                        raise ValueError("Cost Explorer returned mixed currencies.")
                    currency = unit
                    groups[name] = groups.get(name, Decimal("0")) + _amount(metric.get("Amount"))
        output[key.lower()] = {
            "currency": currency or "USD", "pages_collected": page_count,
            "status": "collected",
            "groups": [{"name": name, "cost_exact": str(amount)}
                       for name, amount in sorted(groups.items())],
            "unallocated_cost_exact": str(groups.get("Unallocated", Decimal("0"))),
            "cost_scope": "tagged_account_month_to_date",
        }
    return {"period_start": start, "period_end_exclusive": end,
            "allocation": output, "source": "aws_cost_explorer",
            "notes": ["Tags must be activated as AWS cost allocation tags; untagged costs remain unallocated.",
                      "Service or tag spend is not an exact per-resource charge."]}


def _cw_values(client, *, namespace: str, metric: str, dimensions: list[dict],
               statistic: str = "Average", days: int = 14) -> list[float]:
    end = _utc_now()
    result = aws_call("cloudwatch_metric", client.get_metric_statistics,
        Namespace=namespace, MetricName=metric, Dimensions=dimensions,
        StartTime=end - timedelta(days=days), EndTime=end, Period=86400,
        Statistics=[statistic])
    return [float(point[statistic]) for point in result.get("Datapoints", [])
            if statistic in point]


def collect_rightsizing(account: dict, credentials: dict, *, max_items: int = 300) -> dict:
    """Conservative CPU-based review queue; not an executable resize plan."""
    region = str(account["region"])
    ec2 = _client("ec2", region, credentials)
    rds = _client("rds", region, credentials)
    cw = _client("cloudwatch", region, credentials)
    findings = []
    counts = {"ec2_observed": 0, "rds_observed": 0}
    capped = False
    for page in aws_pages("inventory_ec2_instances",
                          ec2.get_paginator("describe_instances").paginate()):
        for reservation in page.get("Reservations", []):
            for instance in reservation.get("Instances", []):
                counts["ec2_observed"] += 1
                if len(findings) >= max_items:
                    capped = True
                    continue
                if instance.get("State", {}).get("Name") != "running":
                    continue
                instance_id = str(instance["InstanceId"])
                try:
                    cpu = _cw_values(cw, namespace="AWS/EC2", metric="CPUUtilization",
                                     dimensions=[{"Name": "InstanceId", "Value": instance_id}])
                    status = "review_low_cpu" if len(cpu) >= 7 and max(cpu) < 10 else "insufficient_evidence"
                    if len(cpu) >= 7 and max(cpu) >= 10:
                        continue
                    findings.append({"type": "ec2", "resource_id": instance_id,
                        "region": region, "current_size": instance.get("InstanceType"),
                        "status": status, "samples": len(cpu),
                        "cpu_average_percent": round(sum(cpu) / len(cpu), 2) if cpu else None,
                        "cpu_max_percent": max(cpu) if cpu else None,
                        "recommendation": "review_only", "estimated_monthly_savings_usd": None,
                        "risk": "high", "approval_required": True,
                        "reason": "CPU alone cannot justify rightsizing; verify memory, peak usage, storage, reservations and workload ownership."})
                except Exception:
                    findings.append({"type": "ec2", "resource_id": instance_id,
                        "region": region, "status": "metrics_unavailable",
                        "recommendation": "not_assessed", "estimated_monthly_savings_usd": None})
    for page in aws_pages("inventory_rds", rds.get_paginator("describe_db_instances").paginate()):
        for db in page.get("DBInstances", []):
            counts["rds_observed"] += 1
            if len(findings) >= max_items:
                capped = True
                continue
            db_id = str(db["DBInstanceIdentifier"])
            try:
                cpu = _cw_values(cw, namespace="AWS/RDS", metric="CPUUtilization",
                                 dimensions=[{"Name": "DBInstanceIdentifier", "Value": db_id}])
                if len(cpu) >= 7 and max(cpu) >= 10:
                    continue
                findings.append({"type": "rds", "resource_id": db_id,
                    "region": region, "current_size": db.get("DBInstanceClass"),
                    "status": "review_low_cpu" if len(cpu) >= 7 else "insufficient_evidence",
                    "samples": len(cpu), "recommendation": "review_only",
                    "estimated_monthly_savings_usd": None,
                    "risk": "high", "approval_required": True,
                    "reason": "Database rightsizing requires memory, IO, backup, replication and peak usage evidence."})
            except Exception:
                findings.append({"type": "rds", "resource_id": db_id,
                    "region": region, "status": "metrics_unavailable",
                    "recommendation": "not_assessed", "estimated_monthly_savings_usd": None})
    return {"source": "aws_cloudwatch_ec2_rds",
            "lookback_days": 14, "observed": counts, "capped": capped,
            "findings": findings,
            "verified_savings_usd": None,
            "notes": ["Only explicit review candidates; no automatic resizing or termination.",
                      "CPU-only evidence is insufficient for an executable downsizing proposal."]}


def collect_s3(account: dict, credentials: dict) -> dict:
    """Bucket names/tags and approximate daily storage telemetry, not bucket billing."""
    s3 = _client("s3", str(account["region"]), credentials)
    cw = _client("cloudwatch", "us-east-1", credentials)
    result = aws_call("s3_buckets", s3.list_buckets)
    buckets = result.get("Buckets", [])
    if len(buckets) > MAX_BUCKET_RESULTS:
        return {"status": "partial", "reason": "bucket_cap_exceeded",
                "observed_buckets": len(buckets), "buckets": []}
    rows = []
    for bucket in buckets:
        name = str(bucket.get("Name", ""))
        if not name:
            continue
        record = {"name": name, "region": "unknown", "tags": {},
                  "storage_bytes": None, "cost_usd": None,
                  "storage_metrics_status": "not_assessed",
                  "cost_attribution_status": "requires_cur_or_data_export"}
        try:
            loc = aws_call("s3_bucket_location", s3.get_bucket_location, Bucket=name).get("LocationConstraint")
            record["region"] = "us-east-1" if loc is None else ("eu-west-1" if loc == "EU" else loc)
        except Exception:
            record["region"] = "unavailable"
        try:
            tags = s3.get_bucket_tagging(Bucket=name).get("TagSet", [])
            record["tags"] = {str(t["Key"]): str(t["Value"]) for t in tags}
        except Exception:
            record["tags_status"] = "not_available"
        try:
            measures = _cw_values(cw, namespace="AWS/S3", metric="BucketSizeBytes",
                   dimensions=[{"Name": "BucketName", "Value": name},
                               {"Name": "StorageType", "Value": "StandardStorage"}],
                   statistic="Average", days=3)
            record["storage_bytes"] = max(measures) if measures else None
            record["storage_metrics_status"] = "collected" if measures else "not_available"
        except Exception:
            record["storage_metrics_status"] = "not_available"
        rows.append(record)
    return {"status": "success", "source": "s3_inventory_cloudwatch",
            "observed_buckets": len(buckets), "buckets": rows,
            "notes": ["S3 CloudWatch daily StandardStorage bytes exclude other classes and do not prove billed bucket cost.",
                      "Bucket-level cost attribution requires a verified CUR or Data Export; no cost is inferred."]}


def collect_eks(account: dict, credentials: dict) -> dict:
    """Discover EKS clusters only; refuse to invent namespace-level spend."""
    region = str(account["region"])
    eks = _client("eks", region, credentials)
    names = []
    for page in aws_pages("eks_clusters", eks.get_paginator("list_clusters").paginate()):
        names.extend(str(x) for x in page.get("clusters", []))
        if len(names) > MAX_CLUSTER_RESULTS:
            return {"status": "partial", "reason": "cluster_cap_exceeded",
                    "observed_clusters_at_least": len(names), "clusters": []}
    clusters = []
    import boto3
    session = boto3.Session(**credentials)
    from src.tools.eks_usage import collect_namespace_usage
    for name in names:
        try:
            c = aws_call("eks_cluster_details", eks.describe_cluster, name=name)["cluster"]
            usage = collect_namespace_usage(c, name=name, region=region, session=session)
            clusters.append({"name": name, "arn": c.get("arn"),
                "version": c.get("version"), "status": c.get("status"),
                "region": region, "namespace_costs": None,
                "namespace_usage": usage,
                "allocation_status": "requires_verified_cluster_cost_and_shared_cost_model"})
        except Exception:
            clusters.append({"name": name, "region": region,
                "status": "details_unavailable", "namespace_costs": None,
                "allocation_status": "not_assessed"})
    return {"status": "success", "source": "aws_eks", "clusters": clusters,
            "notes": ["Kubernetes Metrics API samples observed namespace CPU/memory only when RBAC and Metrics Server permit it.",
                      "Observed usage is not billed namespace cost; allocation requires verified cluster infrastructure spend and a shared-cost model."]}


def collect_budgets(account: dict, credentials: dict) -> dict:
    """Read existing AWS Budgets, without creating or modifying budgets."""
    budgets = _client("budgets", "us-east-1", credentials)
    rows = []
    for page in aws_pages("aws_budgets", budgets.get_paginator("describe_budgets").paginate(
            AccountId=str(account["account_id"]))):
        for budget in page.get("Budgets", []):
            amount = budget.get("BudgetLimit") or {}
            actual = budget.get("CalculatedSpend", {}).get("ActualSpend") or {}
            rows.append({"name": budget.get("BudgetName"), "type": budget.get("BudgetType"),
                "unit": amount.get("Unit"), "limit_exact": amount.get("Amount"),
                "actual_exact": actual.get("Amount"),
                "status": "observed", "source": "aws_budgets"})
    return {"status": "success", "budgets": rows, "source": "aws_budgets",
            "notes": ["Existing AWS budgets are read only; Finovaunt does not create budgets or send alerts."]}


def assess_aws_finops(account: dict, *, external_id: str = "") -> dict:
    credentials, identity_mode = resolve_aws_session(
        account, external_id=external_id, session_name="FinovauntFinOpsReadOnly")
    collectors = {
        "cost_allocation": lambda: collect_cost_allocation(credentials),
        "rightsizing": lambda: collect_rightsizing(account, credentials),
        "s3": lambda: collect_s3(account, credentials),
        "eks": lambda: collect_eks(account, credentials),
        "budgets": lambda: collect_budgets(account, credentials),
    }
    sections: dict[str, dict] = {}
    for name, run in collectors.items():
        try:
            sections[name] = {"status": "collected", "evidence": run()}
        except Exception:
            # Never record invented zero costs/resources on denied or failed APIs.
            sections[name] = {"status": "not_assessed",
                              "reason": "AWS read-only evidence unavailable; check service permissions and logs."}
    return {"account_id": str(account["account_id"]), "region": str(account["region"]),
            "scanned_at": _utc_now().isoformat(), "read_only": True,
            "aws_auth_mode": identity_mode, "sections": sections,
            "status": "partial" if any(s["status"] != "collected" for s in sections.values()) else "success",
            "realized_savings_usd": None, "automated_actions_performed": 0}
