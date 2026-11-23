# Finovaunt

**Self-hosted cloud cost intelligence and conservative FinOps optimization.**

Finovaunt connects AWS cost evidence and cloud inventory with a read-only optimization workflow. It helps operators understand cloud spend, review EC2/RDS/EBS assets, inspect evidence-backed optimization opportunities, and record human decisions without granting Finovaunt cloud-write permissions.

> **Release status:** Active production-hardening development. The historical functional milestone is not a certified production-ready stable v1.0.0. The automated security and Docker-image publishing jobs are temporarily disabled during the product-improvement phase; backend tests, frontend builds and Compose configuration checks remain enabled. Reinstate the security/image release gates before publishing v1.0.0.

## What Finovaunt does

| Capability | Current implementation | Important boundary |
| --- | --- | --- |
| Account access | Local administrator login, first-use password rotation, protected cloud/billing/scan APIs | A single local administrator, not enterprise SSO/RBAC |
| AWS onboarding | Read-only cross-account IAM role registration | Finovaunt does not create AWS roles or store long-lived AWS keys in the browser |
| Billing | Cost Explorer month-to-date service spend, pagination, exact decimal evidence, historical saved scans | Provisional account/service spend is not verified resource-level recurring cost |
| Asset inventory | Account-scoped EC2, RDS and EBS discovery for a selected region | Unattached EBS is review-only, not a deletion instruction |
| Optimization engine | Conservative utilization collection, risk assessment, cost-evidence guardrails and Terraform proposal artifacts | Missing memory, seasonality or cost evidence blocks unsupported savings estimates |
| Dashboard | Overview, opportunities, assets, scan history, account management and billing | Dashboard scan artifacts and on-demand account inventory are separate data sources today |
| Human review | Approve/reject opportunity with a note, reviewer, timestamp and run ID | **Approval is audit-only. It does not apply Terraform or make AWS changes** |
| Automation | GitHub Actions read-only AWS scan with OIDC and artifact synchronization | Scheduled workflow uses its configured role/region, not automatic fanout to every onboarded account |
| Deployment | Docker Compose API + React dashboard; Python CLI and scan workflow | Local-first, no claim of independently certified multi-user production readiness |

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

The app keeps the optimization engine and interactive CLI separate from the HTTP dashboard. Billing and asset scans use source AWS credentials that can assume the onboarded read-only role; no cloud credentials should be embedded in frontend code.

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

The dashboard may initially show no scan artifacts. This is not permission to fabricate recommendations or savings. To run a live AWS billing or inventory scan, the backend runtime must also have an AWS source identity permitted to assume the selected account role.

```bash
docker compose logs --tail=100 api frontend
docker compose down
```

Normal `docker compose down` preserves host-mounted control-plane and scan-artifact directories. See [Docker deployment](docs/DOCKER.md) for TLS, persistent data, and operating boundaries.

## Run the Python optimization workflow

```bash
uv sync --dev
uv run pytest
uv run python -m src.app
```

The default `FINOPS_DISCOVERY_MODE=mock` is a simulation. To collect real AWS data, choose `FINOPS_DISCOVERY_MODE=aws` and configure AWS credentials and a region. The noninteractive read-only scan can be run with:

```bash
FINOPS_DISCOVERY_MODE=mock FINOPS_OUTPUT_DIR=artifacts-live \
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
| `FINOPS_DISCOVERY_MODE` | `mock` (default) or `aws` |
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
- `POST /api/inventory-scans`, `GET /api/inventory-scans/{account_id}`
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

Automated backend/frontend/Compose CI runs on PRs and pushes. Security scanning and Docker image builds are temporarily deferred at the user's direction. **The final release audit must restore and pass those checks before a stable release.** Read [CI/CD](docs/CI_CD.md) and [Release Readiness](RELEASE_READINESS.md).

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
