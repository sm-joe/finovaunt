# Finovaunt

**Self-hosted cloud cost intelligence and conservative FinOps optimization.**

Finovaunt connects AWS cost evidence and cloud inventory with a read-only optimization workflow. It helps operators understand cloud spend, review EC2/RDS/EBS assets, inspect evidence-backed optimization opportunities, and record human decisions without granting Finovaunt cloud-write permissions.

> **Release status:** Active production-hardening development. The historical functional milestone is not a certified production-ready stable v1.0.0. Security and actual API/dashboard Docker image build checks are restored and required on pull requests and main. Registry publication and stable v1.0.0 remain gated on runtime acceptance, operations review and release evidence.

## What Finovaunt does

| Capability | Current implementation | Important boundary |
| --- | --- | --- |
| Account access | Local administrator login, first-use password rotation, protected cloud/billing/scan APIs | A single local administrator, not enterprise SSO/RBAC |
| AWS onboarding | Account-scoped IAM role registration, auditable collector role/region edits, direct workload role and cross-role authorization | Collector configuration changes do not delete historical evidence; a new scan is required |
| Billing | Cost Explorer month-to-date service spend, pagination, exact decimal evidence, historical saved scans | Provisional account/service spend is not verified resource-level recurring cost |
| Asset inventory | Account-scoped EC2, RDS and EBS discovery with actual EBS type, size, IOPS, throughput, tags and attachment evidence | Region-scoped and read-only |
| EBS optimization | AWS Price List gp2/gp3 storage-only scenario, optional EKS PV correlation, current and historical evidence ledger | Missing prices/PV visibility block unverified estimates, and resources are never deleted |
| Optimization engine | Conservative utilization collection, risk assessment, cost-evidence guardrails and Terraform proposal artifacts | Missing memory, seasonality or cost evidence blocks unsupported savings estimates |
| Dashboard | Live AWS spend/service breakdown, current inventory, EBS review evidence, historical optimization ledger and credential source check | Does not conflate AWS IAM credential presence with successful role assumption |
| Human review | Audit-only EBS candidate review tied to current inventory scan, with note, reviewer and timestamp | **Approval never deletes volumes or executes AWS/Kubernetes changes** |
| Automation | GitHub Actions read-only AWS scan with OIDC and artifact synchronization | Scheduled workflow uses its configured role/region, not automatic fanout to every onboarded account |
| Deployment | Docker Compose API + React dashboard; Python CLI; checksum-verified offline backup/restore | Single-administrator local-first deployment, not certified multi-user production readiness |

## Architecture

```text
Browser / React + TypeScript dashboard
                |
         Nginx same-origin proxy
                |
        Python dashboard HTTP API
           /        |         \
       Access     Billing    Inventory
       control    (STS+CE)   (STS+EC2/RDS)
           \        |         /
          Local persisted control-plane
                |
     Dashboard evidence projections
                |
    GitHub read-only scan artifacts
                |
  Python/LangGraph optimization workflow
    AWS CloudWatch + Cost Explorer
                |
  Human-reviewed Terraform proposal
  (No cloud write or Terraform apply)
```

The app keeps the optimization engine and interactive CLI separate from the HTTP dashboard. Billing and asset scans use the standard AWS credential chain. If the runtime is already using the exact onboarded role, Finovaunt uses those temporary credentials directly; otherwise it calls STS AssumeRole and verifies the result. No cloud credentials should be embedded in frontend code.

## Requirements

- Linux host or a system capable of running Docker Engine + Docker Compose v2
- Docker for the dashboard; Python 3.11+, `uv`, Terraform for the standalone optimization workflow
- For real AWS scans: a deliberately configured read-only AWS identity, cross-account IAM trust, and AWS Cost Explorer availability

## Quickstart — self-hosted dashboard (Bash)

```bash
git clone https://github.com/sm-joe/finovaunt.git
cd finovaunt

# Store the first-install password in a private, ignored .env file.
umask 077
printf 'FINOVAUNT_BOOTSTRAP_PASSWORD=%s\n' "$(openssl rand -hex 24)" > .env

docker compose config --quiet
docker compose up -d --build
docker compose ps
curl --fail http://127.0.0.1:8787/api/health
```

Open **http://127.0.0.1:4173**. Sign in as `admin` with the generated password from `.env`, then rotate it when prompted. Keep `.env` private; it is not committed. Existing installations retain their persisted password hash in `data/control-plane.json`.

The dashboard may initially show no scan artifacts. This is not permission to fabricate recommendations or savings. To run a live AWS billing or inventory scan, the backend runtime must have valid AWS source credentials. When using your local `demo-user` profile, its credentials must be made available to Docker and must be authorized to assume the onboarded read-only role; the role must trust that principal. For optional EBS storage pricing and Kubernetes PV checks, also allow `pricing:GetProducts`, `eks:ListClusters`, `eks:DescribeCluster`, plus EKS cluster RBAC read access to persistent volumes. If these checks cannot complete, evidence is marked unavailable rather than assumed.

```bash
docker compose logs --tail=100 api frontend
docker compose down
```

Normal `docker compose down` preserves host-mounted control-plane and scan-artifact directories. See [Docker deployment](docs/DOCKER.md) for TLS, persistent data, and operating boundaries.

## Manage existing collectors and recover state

Use **Cloud Account Onboarding → Edit Collector** to change the role ARN or region without deleting your original billing and inventory history. Each modification records a reason and starts a new configuration revision; current evidence must be recollected under the new scope. In the dashboard, **Check AWS Credentials** reports whether the container has a source identity, whether that identity already matches the collector role, or whether it still needs `sts:AssumeRole`. It does not test or claim cross-role trust until a collection succeeds.

For local Docker Compose, export your existing default `demo-user` credentials before recreating the API:

```bash
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_PROFILE
aws sts get-caller-identity
eval "$(aws configure export-credentials --format env)"
docker compose up -d --force-recreate api frontend
```

Local `demo-user` credentials are a development option rather than a production prerequisite. Admin-level source keys are available inside the API container when injected this way; do not expose this deployment publicly. For AWS-hosted production, use a read-only workload IAM role with automatically rotated credentials.

An offline backup/restore utility, `scripts/control_backup.py`, validates SHA-256 checksums before recovery. Stop the API before copying or restoring its local state; see [Docker backup and restore operations](docs/DOCKER.md). The CI suite verifies both clean installs and persisted account/password state across container recreation.

## AWS FinOps scope

Finovaunt focuses on frequently used AWS services: Cost Explorer, AWS Budgets, EC2/EBS, RDS, S3, CloudWatch and Amazon EKS. The **AWS FinOps** dashboard runs separate read-only collectors for cost allocation tags, conservative EC2/RDS utilization reviews, S3 bucket inventory/storage telemetry, EKS discovery with optional Kubernetes namespace CPU/memory samples, and existing AWS budgets. Missing evidence remains **not assessed**, never fabricated spend, rightsizing or verified savings.

Optional EC2 non-production power changes live in an **isolated, disabled-by-default executor** with a dedicated IAM role and explicit instance/tag allowlists. Finovaunt's dashboard collector stays read-only. This does not enable automatic night/weekend shutdowns on installation.

See [AWS-only product scope, current implementation and remaining milestones](docs/AWS_FINOPS_SCOPE.md) for the precise M1–M6 status, limitations and least-privilege permissions.

## Run the Python optimization workflow

```bash
uv sync --dev
uv run pytest
uv run python -m src.app
```

The interactive legacy CLI retains a `mock` **test-only simulation mode**, which is not connected to the live AWS dashboard. Scheduled and manually dispatched GitHub scans now require actual AWS OIDC credentials and never deliberately emit mock evidence. To run a real read-only scan locally:

```bash
FINOPS_DISCOVERY_MODE=aws FINOPS_OUTPUT_DIR=artifacts-live \
  uv run python scripts/run_readonly_scan.py
```

The interactive CLI requires explicit approval before writing proposal artifacts or a local Git branch. It does **not** push code, open hosted pull requests, execute `terraform apply`, or mutate AWS resources.

## Safety and evidence rules

- No unsupported cost attribution: monthly service totals never become per-resource savings.
- Utilization gaps, missing CloudWatch memory, unknown workload stability, and insufficient history must be disclosed.
- Simulated costs and simulated savings are labeled separately from live evidence.
- Live changes require explicit human review outside Finovaunt; recorded approval is never equivalent to deployment.
- Realized savings require a dated post-change comparison and change evidence.
- AWS errors fail closed; verified empty inventory is reported as a successful no-op without fabricated assets.
- Terraform HCL is validated locally; shell execution uses fixed argv and timeouts rather than interpolated commands.
- Local control-plane JSON contains password hashes and cloud metadata; back it up and restrict filesystem access.

## Environment variables

| Variable | Meaning |
| --- | --- |
| `FINOVAUNT_BOOTSTRAP_PASSWORD` | Mandatory secure password for a *new* control-plane installation, at least 12 characters |
| `FINOVAUNT_SECURE_COOKIES` | Set to `true` when running behind HTTPS |
| `FINOVAUNT_GITHUB_TOKEN` | Optional token for syncing read-only GitHub scan artifacts |
| `FINOPS_OUTPUT_DIR` | Safe output directory directly under the repository root |
| `FINOPS_DISCOVERY_MODE` | Use `aws` for real scheduled/CLI scans; `mock` is available only for offline development/test workflows |
| `FINOPS_AWS_REGION` | AWS region for the legacy scheduled/CLI scan workflow |
| `FINOPS_AWS_LOOKBACK_DAYS` | CloudWatch lookback window |
| `FINOPS_REQUIRE_TFLINT` | Fail HCL validation without TFLint when enabled |

See [`.env.example`](.env.example) and [Account Access and Billing](docs/ACCESS_AND_BILLING.md).

## API overview

The local HTTP API provides:

- `GET /api/health` — public service liveness
- `POST /api/auth/login`, `POST /api/auth/logout`, `POST /api/auth/password`
- `GET /api/auth/session` — current session metadata
- `GET /api/cloud-accounts`, `POST /api/cloud-accounts`, `DELETE /api/cloud-accounts/{account_id}`
- `POST /api/billing-scans`, `GET /api/billing-scans/{account_id}`
- `POST /api/inventory-scans`, `GET /api/inventory-scans/{account_id}`\n- `GET /api/live-dashboard?account_id=...` — actual account-scoped AWS evidence and EBS scenario estimates\n- `GET /api/ebs-reviews?account_id=...`, `POST /api/ebs-reviews` — audit-only candidate reviews
- `GET /api/overview`, `GET /api/assets`, `GET /api/opportunities`, `GET /api/scans`
- `GET /api/recommendation-decisions`, `POST /api/recommendation-decisions`

Sensitive endpoints require authentication. Every state-changing operation is application-local unless explicitly documented otherwise.

## Testing

```bash
uv sync --dev
uv run python -m compileall -q src scripts tests
uv run python -m pytest -q

cd frontend
npm ci
npm run lint
npm run typecheck
npm run build
cd ..

docker compose config --quiet
```

Automated backend/frontend/Compose CI, security scans, and real API/dashboard Docker image builds run on PRs and pushes. A clean-start Compose API/frontend HTTP smoke test is also a release gate. **A stable release still requires verified upgrade/rollback, real AWS acceptance, supported artifact publication and release evidence.** Read [CI/CD](docs/CI_CD.md) and [Release Readiness](RELEASE_READINESS.md).

## Documentation

- [Deployment and operations](docs/DOCKER.md)
- [Authentication, accounts and AWS billing](docs/ACCESS_AND_BILLING.md)
- [Human recommendation review](docs/RECOMMENDATION_REVIEWS.md)
- [Cost-evidence report model](docs/COST_EVIDENCE_REPORT.md)
- [Outcome verification](docs/OUTCOME_VERIFICATION.md)
- [CI/CD](docs/CI_CD.md)
- [Security policy](SECURITY.md)

## License

Finovaunt is distributed under the [MIT License](LICENSE). No official stable v1.0.0 release is claimed by this document.
