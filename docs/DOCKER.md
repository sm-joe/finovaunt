# Finovaunt — Docker Deployment and Operations

Finovaunt provides a self-hosted React dashboard and a Python API using two Docker Compose services. The API stores user/account metadata and scan history in a bind-mounted `data/` directory, and dashboard scan artifacts in `artifacts-live/`.

## Requirements

- Linux with Docker Engine and Docker Compose v2
- OpenSSL for generating a first-install password
- TCP 4173 and 8787 available on local loopback
- Docker permissions to run a one-shot root-owned directory initialization helper; the application service itself runs as UID 10001

## Quickstart (Bash only)

From the repository root:

```bash
umask 077
printf 'FINOVAUNT_BOOTSTRAP_PASSWORD=%s\n' "$(openssl rand -hex 24)" > .env
mkdir -p data artifacts-live

docker compose config --quiet
docker compose up -d --build
docker compose ps
curl --fail http://127.0.0.1:8787/api/health
```

Open `http://127.0.0.1:4173`. The username is `admin`; the initial password is the value in the private `.env` file. First login requires password rotation. After rotation, your persisted password hash remains in `data/control-plane.json`. Changing the bootstrap environment variable does not reset an existing password.

**Do not expose the default deployment directly on the internet.** Both published ports are bound to `127.0.0.1`. For remote installations, use a trusted authenticated reverse proxy with TLS, restrict networking, set `FINOVAUNT_SECURE_COOKIES=true`, and configure a secure external hostname/origin strategy before enabling user access.

## Build and lifecycle

```bash
docker compose config --quiet
docker compose up -d --build
docker compose logs --tail=100 api frontend
docker compose restart api frontend
docker compose down
```

The `init-data` one-shot service runs before the API, adjusts ownership of `./data` to UID 10001 (including older `control-plane.json.tmp` files), then exits. The API continues running as non-root. This avoids needing a manual host-side `sudo chown` for the control-plane path and preserves existing user credentials, accounts and billing history. The helper needs host filesystem support for ownership changes; on filesystems that reject `chown`, use a Linux filesystem path or fix host permissions before starting the API. It does not reset passwords.

`docker compose down` preserves bind-mounted `data/` and `artifacts-live/`. Avoid deleting these paths; they contain user state and scan evidence. The Docker API runs with a read-only root filesystem, no additional Linux capabilities, and a non-root UID. Its bound data directories must still be writable.

## Using AWS

AWS billing and inventory scans need a source AWS credential chain in the API runtime that can call `sts:AssumeRole` on each onboarded role. The container does **not** automatically inherit your host `~/.aws` credentials.

Prefer deploying the API on a host/orchestrator that supplies a short-lived workload identity, rather than baking AWS keys into an image or embedding them in the UI. The onboarded target IAM role must permit the necessary read-only actions:

- `sts:GetCallerIdentity` in the assumed role
- `ce:GetCostAndUsage` for Cost Explorer billing
- `ec2:DescribeInstances` and `ec2:DescribeVolumes`
- `rds:DescribeDBInstances`
- The source identity must be trusted by the target role for `sts:AssumeRole`

The GitHub Actions OIDC scanner uses its own configured AWS role and region; it is not automatically connected to every dashboard-onboarded account. Do not conflate these two collection paths.

## Live AWS Dashboard (No Mock Data)

The primary dashboard now reads **actual Cost Explorer and regional EC2/RDS/EBS collection results** from the local control-plane database. It no longer requires `cost_evidence.json`, `FINOPS_OUTPUT_DIR`, or GitHub Actions artifacts to display an onboarded account. Historical GitHub scan-artifact endpoints remain separate for compatibility.

1. Log in and complete the initial password rotation.
2. Open **Cloud Accounts → Onboard AWS account**. Provide the 12-digit account ID, a trusted read-only IAM role ARN in the target account, and the AWS region. Account onboarding does not by itself mean AWS access is working.
3. Supply an AWS **source credential chain** to the API container. The source identity must be able to call `sts:AssumeRole` on the target role; configure the target role's trust policy accordingly. The target role must allow `ce:GetCostAndUsage`, `ec2:DescribeInstances`, `ec2:DescribeVolumes`, and `rds:DescribeDBInstances`. If the role requires an External ID, enter it when collecting; the UI does not persist it.
4. Return to **Dashboard**, select the account, and click **Collect Live AWS Data**. Billing and inventory collect independently. The dashboard shows the last successful AWS responses and their timestamps; missing or failed collections remain explicitly unavailable.

For temporary local development, pass **short-lived** AWS session credentials exported in your Bash environment to Docker Compose:

```bash
export AWS_ACCESS_KEY_ID='...'
export AWS_SECRET_ACCESS_KEY='...'
export AWS_SESSION_TOKEN='...'
docker compose up -d --build --force-recreate api frontend
```

Do not commit these credentials to a file or share them in logs. Environment variables may be visible in container inspection; use an AWS instance/task/pod workload identity or an appropriate credential provider for a production deployment instead. The source identity and target assumed role must be separate where applicable. A signed-in dashboard session does not automatically confer AWS API permissions.

**Correct absence semantics:** No onboarded accounts → onboarding prompt; no completed billing collection → no amount; successful empty AWS response → zero observed resources or charges as returned; failed or permission-denied collection → descriptive error with no fabricated totals. Cost Explorer reports account/service totals only, not resource-level spend. An unattached EBS volume is a review candidate, not a verified saving. Data is persisted from AWS responses and is not a continuously streaming connection; use **Collect Live AWS Data** to capture a new snapshot.

## Diagnose AWS Billing 502 Errors

Billing errors now identify the failed stage and safe AWS error code, without exposing AWS SDK response details.

| Stage | Likely problem | Action |
| --- | --- | --- |
| `source_identity` / `CredentialsUnavailable` | API container has no usable AWS source credentials | Configure short-lived credentials/workload identity for the **API container**, not just the host |
| `assume_role` / `AccessDenied` | Source principal lacks `sts:AssumeRole`, target role trust excludes principal, or External ID is missing/mismatched | Confirm both IAM caller policy and target role trust policy |
| `assume_role` / `ExpiredToken` | AWS source session credentials are expired | Renew short-lived credentials and recreate API container |
| `verify_identity` | Assumed role identity mismatches the account or is invalid | Verify the onboarded 12-digit account ID and IAM role ARN |
| `cost_explorer` / `AccessDeniedException` | Assumed role cannot call Cost Explorer | Grant `ce:GetCostAndUsage`, and verify billing/Cost Explorer visibility for this AWS account |
| `cost_explorer` / `DataUnavailableException` | Billing service has not made data available for the requested period | Verify Cost Explorer is enabled and historical billing data has had time to populate |

To check the **actual source identity used by the container**, run this Bash command from the repository root:

```bash
docker compose exec -T api python -c \
  'import boto3; s=boto3.client("sts"); i=s.get_caller_identity(); print("Source AWS account:", i["Account"]); print("Source principal:", i["Arn"])'
```

This command displays the caller ARN but does not print AWS access keys. Never paste tokens, credentials or full error logs containing secrets into issues. Then compare the source principal with the target IAM role trust policy. An STS identity check succeeds even when the principal has no authorization to assume the target role. The account configured in the dashboard is the **target account**, not necessarily the source account.

A minimal target-role billing policy needs `ce:GetCostAndUsage` on `Resource: "*"`; add the documented regional EC2/RDS Describe permissions for inventory. The source identity separately needs `sts:AssumeRole` scoped to the exact target role ARN, and the target role must trust the source identity. Do not grant write privileges or attach AdministratorAccess just to make the collection work.

## Scan artifacts

The dashboard displays the latest synced or locally provided artifact snapshot under `artifacts-live/`. Without a real snapshot, its data endpoints deliberately report unavailable evidence rather than inventing savings.

For GitHub scan-artifact synchronization, provide a token with the minimum repository Actions read permission through `FINOVAUNT_GITHUB_TOKEN`, and configure `FINOVAUNT_GITHUB_REPOSITORY` and `FINOVAUNT_SCAN_WORKFLOW` as required. Keep this token out of source files and container images.

A verified no-resource AWS scan produces `scan_status.json` with `empty_inventory` status and zero savings. It does not generate misleading optimization proposals.

## Backup and restore

Back up both local state and scan evidence, preserving file permissions and confidentiality:

```bash
docker compose stop
umask 077
tar -czf finovaunt-backup.tar.gz data artifacts-live
docker compose start
```

Restore only after stopping the API and verifying the backup's integrity and source. Preserve ownership of the restored directories for UID 10001. A backup file may contain password hashes, account identifiers, billing history, review notes and cloud inventory; encrypt it at rest and restrict access.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Compose refuses startup | Set `FINOVAUNT_BOOTSTRAP_PASSWORD` in a private `.env` with at least 12 characters |
| Login returns 502 and logs show `PermissionError: /app/data/control-plane.json.tmp` | Recreate with `docker compose up -d --build`; check `docker compose logs init-data`. The initialization helper must finish successfully before the API starts. Never delete `data/control-plane.json` to fix permissions. |
| Login rejected | Verify persisted `data/control-plane.json`; bootstrap only applies to first setup |
| Dashboard shows unavailable scan data | Inspect `artifacts-live/`, synchronization status, and `FINOPS_OUTPUT_DIR` |
| AWS billing 502 | Read the `stage` and `aws_error_code` shown in the dashboard, then follow the AWS billing diagnostic table above |
| API unhealthy | Inspect `docker compose logs api` and mounted directory permissions |
| Frontend cannot reach API | Inspect `docker compose logs frontend`, loopback port mapping and Nginx proxy |

## Release boundary

Local Compose configuration and CI validation do not imply that images were built, inspected and deployed in a production-like environment. The security and Docker image build workflows are temporarily disabled at the owner's request. They must be restored and pass before stable v1.0.0.
