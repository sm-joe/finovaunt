"""Mock-only cloud discovery data; no SDK or credentials."""
from src.utils.guardrails import ResourceMetric

def collect_mock_metrics() -> list[ResourceMetric]:
    """Return low-utilization compute and high-peak production databases."""
    return [
      ResourceMetric(provider="aws",resource_id="aws:ec2:eu-central-1:worker-01",resource_type="compute",name="worker-01",region="eu-central-1",environment="dev",monthly_cost_usd=286.4,avg_cpu_percent=3.8,peak_cpu_percent=11.5,avg_memory_percent=22,metadata={"instance_type":"m6i.2xlarge","discovery":"mock"}),
      ResourceMetric(provider="aws",resource_id="aws:rds:eu-central-1:payments-primary",resource_type="database",name="payments-primary",region="eu-central-1",environment="prod",monthly_cost_usd=1480,avg_cpu_percent=47,peak_cpu_percent=94,avg_memory_percent=81,production_critical=True,metadata={"engine":"postgres","discovery":"mock"}),
      ResourceMetric(provider="gcp",resource_id="gcp:compute:us-central1:batch-02",resource_type="compute",name="batch-02",region="us-central1",environment="test",monthly_cost_usd=194.75,avg_cpu_percent=8.2,peak_cpu_percent=24,avg_memory_percent=31,metadata={"machine_type":"n2-standard-8","discovery":"mock"}),
      ResourceMetric(provider="gcp",resource_id="gcp:database:us-central1:analytics-prod",resource_type="database",name="analytics-prod",region="us-central1",environment="prod",monthly_cost_usd=920,avg_cpu_percent=39,peak_cpu_percent=89,avg_memory_percent=77,production_critical=True,metadata={"engine":"cloudsql-postgres","discovery":"mock"}),
    ]
