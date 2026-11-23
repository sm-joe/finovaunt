# Finovaunt AWS FinOps Product Scope

Finovaunt is **AWS-only**. Supported service families are Cost Explorer, AWS Budgets, EC2, EBS, RDS, S3, CloudWatch and Amazon EKS. Other AWS services may appear as *billing line items* but are not scanned or modified. No other cloud providers are supported.

## Collector security

- Default API collection is **read-only** and uses the existing source-credential chain (including the locally configured default `demo-user` profile) to assume the onboarded `Finovaunt-RO-Scan-Role`. The principal must be trusted; the role must have the necessary read permissions.
- Minimum incremental permissions beyond existing read-only EC2/EBS/RDS and Cost Explorer: `cloudwatch:GetMetricStatistics`, `s3:ListAllMyBuckets`, `s3:GetBucketLocation`, `s3:GetBucketTagging`, `eks:ListClusters`, `eks:DescribeCluster`, `budgets:DescribeBudgets`.
- Cost Explorer tag allocation requires `ce:GetCostAndUsage` and **activated** AWS cost allocation tags for Team, Project and Environment. Unallocated charges remain unallocated; no resource-level cost attribution is fabricated.
- Missing optional permissions produce per-section `not_assessed`, never a false zero.
- The API has **no automatic AWS shutdown permission** and does not import or invoke the privileged executor.

## Implementation status by milestone

| Milestone | Delivered in initial AWS FinOps increment | Still required before complete |
| --- | --- | --- |
| M1 — Cost ingestion and allocation | Month-to-date Cost Explorer explicitly filtered by linked account, grouped by Team, Project, Environment tags and AWS Region, exact decimals, unallocated visibility, persistent revision-scoped evidence | CUR 2.0 / AWS Data Exports source, historical region drilldowns, hourly/daily ingestion, complete resource attribution and reconciled charges |
| M2 — Resource optimization | Read-only EC2 and RDS CPU telemetry review; existing EBS lifecycle/pricing/PV review | Memory, network, IO and utilization seasonality; attributable instance pricing; verified recommendations with savings and confidence |
| M3 — S3 cost intelligence | S3 bucket/region/tag discovery and CloudWatch StandardStorage size telemetry | Verified bucket-level costs from CUR, all storage classes, requests/transfer, Storage Lens and lifecycle class recommendations |
| M4 — EKS FinOps | EKS cluster inventory/status, read-only Kubernetes Metrics API namespace CPU/memory samples (RBAC permitting), and explicit absence of namespace cost attribution; existing EBS PV verification | Verified node costs and pod/request telemetry coverage, namespace/workload dollar allocation, shared cost model and accuracy acceptance |
| M5 — Budgets and automation | Existing AWS Budgets read; disabled-by-default schedule evaluator; separate gated EC2 executor | Policy management UI, durable scheduling, approval/reconciliation, anomaly alerts and complete audit/recovery |
| M6 — Production platform | Existing Docker smoke and persisted restart acceptance, backup checks, security CI | Transactional database and migrations, multi-user RBAC, frontend E2E, rate limits, full upgrade/rollback tests, signed releases |

These are milestones, not claims that all work within each milestone is finished. Do not publish a production-complete or stable version until the remaining acceptance gates pass.

## One-click read-only assessment

After onboarding your AWS account, select it in the dashboard, open **AWS FinOps**, and choose **Collect AWS FinOps Evidence**. This uses the existing API source credentials and target read-only role. Every section records whether its own evidence is available. The result is saved locally, and changing the IAM role or region invalidates the *current* view without deleting past evidence.

The S3 StandardStorage CloudWatch metric is a daily capacity observation, **not a billed cost**. EKS list/describe responses do not prove namespace spending. Low EC2/RDS CPU is **not** an executable rightsizing recommendation. No savings are considered realized until validated against post-change billing and resource lifecycle evidence.

## EKS namespace usage (read-only, not a dollar cost)

If the EKS Kubernetes API is reachable from the Finovaunt container, a signed short-lived EKS token and the cluster's AWS-provided CA are used for `GET /apis/metrics.k8s.io/v1beta1/pods`. Kubernetes Metrics Server must be installed and the AWS role principal must be granted read access to the `pods` resource in `metrics.k8s.io` for the desired namespaces; cluster-wide access is required to collect across all namespaces. EKS IAM `eks:DescribeCluster` alone does not supply Kubernetes RBAC.

Finovaunt aggregates **sampled** namespace CPU (millicores), memory (MiB) and observed pod counts. This is point-in-time usage, not requests/limits, full workload coverage, node accounting, or attributable spend. Private EKS endpoints must be reachable from the API container; auth/RBAC/metrics unavailability returns `not_assessed`, not zero usage. The query is GET-only, certificate verified, and restricts signed credentials to an EKS endpoint hostname. No Kubernetes resource is edited.

## Optional non-production power executor

This subsystem is separate from the dashboard and does **not** run by default. It targets only explicitly enumerated EC2 instance IDs tagged with `Environment=dev|development|test|qa|staging` and excludes EKS/Kubernetes/Auto Scaling instances. Its dedicated `Finovaunt-NonProd-Executor-Role` must be created and trusted separately; do not attach power permissions to the read-only scanner. It should be granted only `ec2:DescribeInstances`, `ec2:StartInstances`, `ec2:StopInstances` for the approved account, region and resources, with IAM tag-based conditions on the start/stop actions.

Dry-run planning (still verifies the explicitly configured executor role and inventory):

```bash
python scripts/nonprod_executor.py \
  --role-arn arn:aws:iam::123456789012:role/Finovaunt-NonProd-Executor-Role \
  --region us-east-1 --environment dev --action stop \
  --instance-id i-0123456789abcdef0
```

Actual EC2 writes require both `FINOVAUNT_ALLOW_NONPROD_EXECUTION=explicitly-enabled` and `--execute`. This is an explicitly approved **manual executor**, not a configured scheduler: there is no automatic shutdown by default. Do not configure cron execution until audit storage, approval expiry, work-hour timezone rules and rollback/recovery have been validated. Use separate least-privilege credentials for privileged execution.

## Operations

The read-only assessment may take longer than a simple billing scan because it queries optional services and CloudWatch datapoints. A missing feature-specific permission is not a general account authorization failure. Assessments are bounded to 40 persisted snapshots and tied to the collector revision. The existing offline state backup includes FinOps evidence. Keep the local API behind loopback or authenticated TLS, and treat injected administrator-capable source credentials as sensitive.
