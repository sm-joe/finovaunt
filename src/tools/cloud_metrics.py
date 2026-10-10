"""Mock and read-only AWS cloud metrics collection."""
import os
from datetime import UTC, datetime, timedelta
from statistics import fmean

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


def _summarize_cpu_datapoints(
    datapoints: list[dict],
) -> tuple[float, float] | None:
    """Return average CPU and peak CPU, or None if telemetry is absent."""
    averages = [
        float(point["Average"])
        for point in datapoints
        if point.get("Average") is not None
    ]
    maxima = [
        float(point["Maximum"])
        for point in datapoints
        if point.get("Maximum") is not None
    ]

    if not averages or not maxima:
        return None

    return round(fmean(averages), 2), round(max(maxima), 2)


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

    def read_cpu(
        namespace: str,
        dimension_name: str,
        dimension_value: str,
    ) -> tuple[float, float] | None:
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
            Period=3600,
            Statistics=["Average", "Maximum"],
        )
        return _summarize_cpu_datapoints(response.get("Datapoints", []))

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

                instance_id = instance["InstanceId"]
                resource_id = f"aws:ec2:{region}:{instance_id}"
                tags = instance.get("Tags", [])
                cpu = read_cpu("AWS/EC2", "InstanceId", instance_id)

                if cpu is None:
                    warnings.append(
                        f"{resource_id}: no usable CloudWatch CPU datapoints; "
                        "excluded from recommendations."
                    )
                    continue

                avg_cpu, peak_cpu = cpu
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
                            "memory_status": "not_collected",
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
                    warnings.append(
                        f"{resource_id}: no usable CloudWatch CPU datapoints; "
                        "excluded from recommendations."
                    )
                    continue

                avg_cpu, peak_cpu = cpu
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
                            "memory_status": "not_collected",
                            "cost_status": "not_collected",
                        },
                    )
                )

            if len(metrics) >= max_resources:
                break

    if not metrics:
        warnings.append(
            "No resources with usable CPU telemetry were discovered. "
            "No optimization recommendations should be generated."
        )

    return metrics, warnings