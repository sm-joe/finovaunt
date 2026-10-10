"""Mock and read-only AWS cloud metrics collection."""
import os
from datetime import UTC, datetime, timedelta
from statistics import fmean
import math

from src.utils.guardrails import ResourceMetric


def collect_mock_metrics() -> list[ResourceMetric]:
    """Return deterministic sample data for development and tests."""
    return [
        ResourceMetric(
            provider="aws",
            resource_id="aws:ec2:eu-central-1:worker-01",
            resource_type="compute",
            name="worker-01",
            region="eu-central-1",
            environment="dev",
            monthly_cost_usd=286.4,
            avg_cpu_percent=3.8,
            peak_cpu_percent=11.5,
            avg_memory_percent=22,
            metadata={
                "instance_type": "m6i.2xlarge",
                "discovery": "mock",
                "cost_status": "simulated_monthly_cost",
                "cost_currency": "USD",
            },
        ),
        ResourceMetric(
            provider="aws",
            resource_id="aws:rds:eu-central-1:payments-primary",
            resource_type="database",
            name="payments-primary",
            region="eu-central-1",
            environment="prod",
            monthly_cost_usd=1480,
            avg_cpu_percent=47,
            peak_cpu_percent=94,
            avg_memory_percent=81,
            production_critical=True,
            metadata={
                "engine": "postgres",
                "discovery": "mock",
                "cost_status": "simulated_monthly_cost",
                "cost_currency": "USD",
            },
        ),
        ResourceMetric(
            provider="gcp",
            resource_id="gcp:compute:us-central1:batch-02",
            resource_type="compute",
            name="batch-02",
            region="us-central1",
            environment="test",
            monthly_cost_usd=194.75,
            avg_cpu_percent=8.2,
            peak_cpu_percent=24,
            avg_memory_percent=31,
            metadata={
                "machine_type": "n2-standard-8",
                "discovery": "mock",
                "cost_status": "simulated_monthly_cost",
                "cost_currency": "USD",
            },
        ),
        ResourceMetric(
            provider="gcp",
            resource_id="gcp:database:us-central1:analytics-prod",
            resource_type="database",
            name="analytics-prod",
            region="us-central1",
            environment="prod",
            monthly_cost_usd=920,
            avg_cpu_percent=39,
            peak_cpu_percent=89,
            avg_memory_percent=77,
            production_critical=True,
            metadata={
                "engine": "cloudsql-postgres",
                "discovery": "mock",
                "cost_status": "simulated_monthly_cost",
                "cost_currency": "USD",
            },
        ),
    ]


def _environment_from_tags(tags: list[dict]) -> str:
    """Normalize common environment tag names and values."""
    tag_values = {
        str(tag.get("Key", "")).strip().lower():
        str(tag.get("Value", "")).strip().lower()
        for tag in tags
    }

    value = next(
        (
            tag_values[key]
            for key in ("environment", "env", "stage")
            if tag_values.get(key)
        ),
        "",
    )

    aliases = {
        "production": "prod",
        "prd": "prod",
        "development": "dev",
        "sandbox": "dev",
        "testing": "test",
        "qa": "test",
        "preprod": "staging",
        "pre-production": "staging",
    }

    value = aliases.get(value, value)
    return value if value in {
        "dev", "test", "staging", "prod"
    } else "unknown"


def _valid_cpu_datapoints(datapoints: list[dict]) -> list[dict]:
    """Keep only datapoints with finite Average and Maximum values."""
    valid: list[dict] = []
    for point in datapoints:
        try:
            average = float(point["Average"])
            maximum = float(point["Maximum"])
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if not (math.isfinite(average) and math.isfinite(maximum)):
            continue
        if not (0 <= average <= 100 and 0 <= maximum <= 100):
            continue
        valid.append(point)
    return valid


def _summarize_cpu_datapoints(
    datapoints: list[dict],
) -> tuple[float, float] | None:
    """Return average CPU and peak CPU from paired, finite datapoints."""
    valid = _valid_cpu_datapoints(datapoints)
    if not valid:
        return None
    averages = [float(point["Average"]) for point in valid]
    maxima = [float(point["Maximum"]) for point in valid]
    return round(fmean(averages), 2), round(max(maxima), 2)


def _summarize_memory_datapoints(
    datapoints: list[dict],
) -> tuple[float, float] | None:
    """Return average and peak memory percentages from valid CWAgent points."""
    valid = _valid_cpu_datapoints(datapoints)
    if not valid:
        return None
    averages = [float(point["Average"]) for point in valid]
    maxima = [float(point["Maximum"]) for point in valid]
    return round(fmean(averages), 2), round(max(maxima), 2)


def _timestamp_text(value: object) -> str | None:
    if not isinstance(value, datetime):
        return None
    stamp = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return stamp.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _telemetry_metadata(
    datapoints: list[dict],
    *,
    start_time: datetime,
    end_time: datetime,
    period_seconds: int,
    lookback_days: int,
    metric_name: str = "CPUUtilization",
) -> dict[str, str]:
    """Describe the actual CloudWatch evidence behind a percentage summary."""
    valid = _valid_cpu_datapoints(datapoints)
    stamps = [point.get("Timestamp") for point in valid]
    stamps = [stamp for stamp in stamps if isinstance(stamp, datetime)]
    expected = max(1, round((end_time - start_time).total_seconds() / period_seconds))
    coverage = round(min(100.0, len(valid) / expected * 100), 2)
    return {
        "telemetry_status": "available" if valid else "unavailable",
        "telemetry_metric": metric_name,
        "telemetry_period_seconds": str(period_seconds),
        "telemetry_lookback_days": str(lookback_days),
        "telemetry_window_start": _timestamp_text(start_time) or "",
        "telemetry_window_end": _timestamp_text(end_time) or "",
        "telemetry_datapoints_returned": str(len(datapoints)),
        "telemetry_datapoints_usable": str(len(valid)),
        "telemetry_datapoints_expected": str(expected),
        "telemetry_coverage_percent": str(coverage),
        "telemetry_first_datapoint_at": _timestamp_text(min(stamps)) if stamps else "",
        "telemetry_latest_datapoint_at": _timestamp_text(max(stamps)) if stamps else "",
    }


def _read_ec2_memory(
    cloudwatch,
    *,
    instance_id: str,
    start_time: datetime,
    end_time: datetime,
    period_seconds: int,
    lookback_days: int,
) -> tuple[float | None, dict[str, str], str | None]:
    """Read optional CloudWatch Agent memory telemetry without inventing values.

    Only a unique CWAgent mem_used_percent metric matching this EC2 instance is
    accepted. Metrics with ambiguous dimension sets are rejected rather than
    selecting an arbitrary series.
    """
    base = {
        "memory_status": "not_published",
        "memory_source": "cloudwatch:CWAgent:mem_used_percent",
        "memory_metric": "mem_used_percent",
        "memory_period_seconds": str(period_seconds),
        "memory_lookback_days": str(lookback_days),
        "memory_datapoints_usable": "0",
        "memory_datapoints_expected": str(
            max(1, round((end_time - start_time).total_seconds() / period_seconds))
        ),
        "memory_coverage_percent": "0.0",
        "memory_first_datapoint_at": "",
        "memory_latest_datapoint_at": "",
    }
    try:
        response = cloudwatch.list_metrics(
            Namespace="CWAgent",
            MetricName="mem_used_percent",
            Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
        )
        candidates = [
            item
            for item in response.get("Metrics", [])
            if any(
                dimension.get("Name") == "InstanceId"
                and dimension.get("Value") == instance_id
                for dimension in item.get("Dimensions", [])
            )
        ]
        exact = [
            item for item in candidates
            if len(item.get("Dimensions", [])) == 1
        ]
        if len(exact) == 1:
            selected = exact[0]
        elif len(candidates) == 1:
            selected = candidates[0]
        elif len(candidates) > 1:
            base["memory_status"] = "ambiguous_dimensions"
            return None, base, None
        else:
            return None, base, None

        dimensions = selected.get("Dimensions", [])
        datapoint_response = cloudwatch.get_metric_statistics(
            Namespace="CWAgent",
            MetricName="mem_used_percent",
            Dimensions=dimensions,
            StartTime=start_time,
            EndTime=end_time,
            Period=period_seconds,
            Statistics=["Average", "Maximum"],
        )
        datapoints = datapoint_response.get("Datapoints", [])
        summary = _summarize_memory_datapoints(datapoints)
        telemetry = _telemetry_metadata(
            datapoints,
            start_time=start_time,
            end_time=end_time,
            period_seconds=period_seconds,
            lookback_days=lookback_days,
            metric_name="mem_used_percent",
        )
        base.update({
            "memory_status": "available" if summary is not None else "no_usable_datapoints",
            "memory_datapoints_usable": telemetry["telemetry_datapoints_usable"],
            "memory_datapoints_expected": telemetry["telemetry_datapoints_expected"],
            "memory_coverage_percent": telemetry["telemetry_coverage_percent"],
            "memory_first_datapoint_at": telemetry["telemetry_first_datapoint_at"],
            "memory_latest_datapoint_at": telemetry["telemetry_latest_datapoint_at"],
        })
        return (summary[0] if summary is not None else None), base, None
    except Exception as exc:
        base["memory_status"] = "collection_error"
        return None, base, f"{type(exc).__name__}"


def collect_aws_metrics() -> tuple[list[ResourceMetric], list[str]]:
    """Discover running EC2 and available RDS CPU metrics without mutations.

    Costs and memory utilization are intentionally not fabricated.
    Resources without usable CPU telemetry are excluded and reported as warnings.
    """
    import boto3

    region = (
        os.getenv("FINOPS_AWS_REGION")
        or os.getenv("AWS_REGION")
        or os.getenv("AWS_DEFAULT_REGION")
        or ""
    ).strip()

    if not region:
        raise ValueError(
            "Set FINOPS_AWS_REGION or configure an AWS default region."
        )

    try:
        lookback_days = int(os.getenv("FINOPS_AWS_LOOKBACK_DAYS", "14"))
        max_resources = int(os.getenv("FINOPS_AWS_MAX_RESOURCES", "100"))
    except ValueError as exc:
        raise ValueError(
            "FINOPS_AWS_LOOKBACK_DAYS and FINOPS_AWS_MAX_RESOURCES "
            "must be integers."
        ) from exc

    if not 1 <= lookback_days <= 90:
        raise ValueError(
            "FINOPS_AWS_LOOKBACK_DAYS must be between 1 and 90."
        )

    if not 1 <= max_resources <= 1000:
        raise ValueError(
            "FINOPS_AWS_MAX_RESOURCES must be between 1 and 1000."
        )

    session = boto3.Session(region_name=region)
    ec2 = session.client("ec2")
    rds = session.client("rds")
    cloudwatch = session.client("cloudwatch")

    end_time = datetime.now(UTC)
    start_time = end_time - timedelta(days=lookback_days)

    metrics: list[ResourceMetric] = []
    warnings: list[str] = []
    discovered_resources = 0
    excluded_resources = 0
    period_seconds = 3600

    def read_cpu(
        namespace: str,
        dimension_name: str,
        dimension_value: str,
    ) -> tuple[tuple[float, float], dict[str, str | int | float | None]] | None:
        response = cloudwatch.get_metric_statistics(
            Namespace=namespace,
            MetricName="CPUUtilization",
            Dimensions=[
                {
                    "Name": dimension_name,
                    "Value": dimension_value,
                }
            ],
            StartTime=start_time,
            EndTime=end_time,
            Period=period_seconds,
            Statistics=["Average", "Maximum"],
        )
        datapoints = response.get("Datapoints", [])
        summary = _summarize_cpu_datapoints(datapoints)
        if summary is None:
            return None
        return summary, _telemetry_metadata(
            datapoints,
            start_time=start_time,
            end_time=end_time,
            period_seconds=period_seconds,
            lookback_days=lookback_days,
        )

    # EC2: running instances only.
    ec2_paginator = ec2.get_paginator("describe_instances")

    for page in ec2_paginator.paginate(
        Filters=[
            {
                "Name": "instance-state-name",
                "Values": ["running"],
            }
        ]
    ):
        for reservation in page.get("Reservations", []):
            for instance in reservation.get("Instances", []):
                if len(metrics) >= max_resources:
                    warnings.append(
                        f"Resource limit reached ({max_resources}); "
                        "additional resources were not scanned."
                    )
                    break

                discovered_resources += 1
                instance_id = instance["InstanceId"]
                resource_id = f"aws:ec2:{region}:{instance_id}"
                tags = instance.get("Tags", [])
                cpu = read_cpu("AWS/EC2", "InstanceId", instance_id)

                if cpu is None:
                    excluded_resources += 1
                    warnings.append(
                        f"{resource_id}: no usable CloudWatch CPU datapoints; "
                        "excluded from recommendations."
                    )
                    continue

                (avg_cpu, peak_cpu), telemetry = cpu
                avg_memory, memory_metadata, memory_error = _read_ec2_memory(
                    cloudwatch,
                    instance_id=instance_id,
                    start_time=start_time,
                    end_time=end_time,
                    period_seconds=period_seconds,
                    lookback_days=lookback_days,
                )
                if memory_error:
                    warnings.append(
                        f"{resource_id}: optional memory telemetry collection failed "
                        f"({memory_error}); CPU collection remains usable."
                    )
                environment = _environment_from_tags(tags)
                name = next(
                    (
                        tag["Value"]
                        for tag in tags
                        if tag.get("Key", "").lower() == "name"
                    ),
                    instance_id,
                )

                metrics.append(
                    ResourceMetric(
                        provider="aws",
                        resource_id=resource_id,
                        resource_type="compute",
                        name=name,
                        region=region,
                        environment=environment,
                        monthly_cost_usd=0,
                        avg_cpu_percent=avg_cpu,
                        peak_cpu_percent=peak_cpu,
                        avg_memory_percent=avg_memory,
                        production_critical=environment == "prod",
                        metadata={
                            "discovery": "aws-live",
                            "instance_type": instance.get(
                                "InstanceType", "unknown"
                            ),
                            "instance_state": instance.get(
                                "State", {}
                            ).get("Name", "unknown"),
                            "metrics_source": "cloudwatch:AWS/EC2:CPUUtilization",
                            "metrics_window_days": str(lookback_days),
                            **telemetry,
                            **memory_metadata,
                            "cost_status": "not_collected",
                        },
                    )
                )

            if len(metrics) >= max_resources:
                break

        if len(metrics) >= max_resources:
            break

    # RDS: discover database instances and read their resource tags.
    if len(metrics) < max_resources:
        rds_paginator = rds.get_paginator("describe_db_instances")

        for page in rds_paginator.paginate():
            for database in page.get("DBInstances", []):
                if len(metrics) >= max_resources:
                    warnings.append(
                        f"Resource limit reached ({max_resources}); "
                        "additional resources were not scanned."
                    )
                    break

                discovered_resources += 1
                identifier = database["DBInstanceIdentifier"]
                resource_id = f"aws:rds:{region}:{identifier}"

                # RDS tags are retrieved using a separate read-only API.
                tag_response = rds.list_tags_for_resource(
                    ResourceName=database["DBInstanceArn"]
                )
                tags = tag_response.get("TagList", [])

                cpu = read_cpu(
                    "AWS/RDS",
                    "DBInstanceIdentifier",
                    identifier,
                )

                if cpu is None:
                    excluded_resources += 1
                    warnings.append(
                        f"{resource_id}: no usable CloudWatch CPU datapoints; "
                        "excluded from recommendations."
                    )
                    continue

                (avg_cpu, peak_cpu), telemetry = cpu
                environment = _environment_from_tags(tags)

                metrics.append(
                    ResourceMetric(
                        provider="aws",
                        resource_id=resource_id,
                        resource_type="database",
                        name=identifier,
                        region=region,
                        environment=environment,
                        monthly_cost_usd=0,
                        avg_cpu_percent=avg_cpu,
                        peak_cpu_percent=peak_cpu,
                        production_critical=environment == "prod",
                        metadata={
                            "discovery": "aws-live",
                            "engine": str(database.get("Engine", "unknown")),
                            "db_instance_class": str(
                                database.get("DBInstanceClass", "unknown")
                            ),
                            "db_status": str(
                                database.get("DBInstanceStatus", "unknown")
                            ),
                            "metrics_source": "cloudwatch:AWS/RDS:CPUUtilization",
                            "metrics_window_days": str(lookback_days),
                            **telemetry,
                            "memory_status": "not_collected",
                            "cost_status": "not_collected",
                        },
                    )
                )

            if len(metrics) >= max_resources:
                break

    usable_resources = len(metrics)
    if discovered_resources:
        coverage = round(usable_resources / discovered_resources * 100, 2)
        warnings.append(
            "CPU telemetry coverage: "
            f"{usable_resources}/{discovered_resources} inspected resources usable "
            f"({coverage:.2f}%); {excluded_resources} excluded; "
            f"period={period_seconds}s; lookback={lookback_days} days."
        )
    else:
        warnings.append(f"No running EC2 or RDS instances were discovered in {region}.")

    if not metrics:
        warnings.append(
            "No resources with usable CPU telemetry were discovered. "
            "No optimization recommendations should be generated."
        )

    return metrics, warnings
