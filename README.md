# Finovaunt

**AWS FinOps intelligence, cost visibility, and evidence-first optimization — in one self-hosted workspace.**

[![Product CI](https://github.com/sm-joe/finovaunt/actions/workflows/build.yml/badge.svg)](https://github.com/sm-joe/finovaunt/actions/workflows/build.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![AWS Only](https://img.shields.io/badge/Cloud-AWS%20Only-233c67)
![Release](https://img.shields.io/badge/Release-Development-f5aa42)

Finovaunt brings AWS billing, cloud inventory, cost allocation, Kubernetes usage, and optimization evidence into a cohesive dashboard. It is designed for teams that need to **understand where cloud spend goes, investigate waste, and document decisions** without letting ordinary analytics silently modify infrastructure.

Its collector is **read-only by default**. Findings are supported by observed AWS data; incomplete evidence is labeled accordingly, and recommendations are not misrepresented as realized savings.

> **Release status** — Active development and production hardening. Green CI indicates tested source, **not** a supported, signed, publicly released stable `v1.0.0`. Review [Release Readiness](RELEASE_READINESS.md) before considering production use.

## At a glance

| | |
| --- | --- |
| **Cloud scope** | AWS only: Cost Explorer, AWS Budgets, EC2, EBS, RDS, S3, CloudWatch, and Amazon EKS |
| **Experience** | React + TypeScript enterprise dashboard; cohesive login, account, profile, and reporting pages |
| **Collection** | Python AWS collectors using the SDK credential chain, STS, region/account scopes, and persisted evidence |
| **Optimization** | Conservative EC2/RDS utilization reviews, EBS lifecycle/pricing/PV correlation, historical review ledger |
| **Governance** | Team, project, environment, and region allocation; existing AWS Budgets; human review decisions |
| **Deployment** | Docker Compose with same-origin Nginx frontend and non-root Python API |
| **License** | [MIT](LICENSE) |

## Product experience

The Finovaunt workspace is organized around an account-aware FinOps dashboard:

- **Overview** — Month-to-date spend, cost drivers, historical observed snapshots, allocation coverage, optimization review queue, EKS usage, S3 inventory, and AWS Budgets.
- **Cost Explorer** — Account-scoped service spending, with preserved historical billing evidence.
- **AWS FinOps** — Team / Project / Environment / Region cost allocation, EC2/RDS utilization investigations, S3 storage observations, EKS metrics, and existing budgets.
- **Resources and recommendations** — EC2, RDS, and EBS inventory; evidence-backed manual review candidates and EBS scenario estimates.
- **Cloud Accounts** — AWS onboarding, collector role/region editing with audit reason, billing/inventory collection, and current configuration details.
- **Profile and security** — Administrator sign-in, first-login password rotation, session-aware logout, and credential management.

The interface uses a responsive navy-and-white enterprise design. All displayed financial values must be grounded in saved AWS evidence: no invented forecasts, per-bucket costs, namespace dollar charges, or realized savings.

### AWS coverage and evidence boundaries

| Service / domain | Available now | Not yet claimed |
| --- | --- | --- |
| **Cost Explorer** | Linked-account-filtered service billing, month-to-date totals, historical scans, tag and region grouping | Reconciled CUR/Data Exports resource charges or verified forecast |
| **EC2** | Regional inventory, CPU-based investigation candidates | Fully priced/safe executable rightsizing from CPU alone |
| **EBS** | Attachments, size/type/provisioning, storage-only gp2/gp3 price scenarios, Kubernetes PV cross-checks, review history | Automated deletion or independently verified realized savings |
| **RDS** | Regional inventory and CPU review evidence | Memory/IO-complete automated resizing |
| **S3** | Bucket discovery, location, tags, sampled StandardStorage capacity | Reliable per-bucket billed cost, all storage classes, and lifecycle savings |
| **EKS** | Cluster discovery and optional read-only namespace CPU/memory samples | Accounted namespace or workload dollar allocation |
| **AWS Budgets** | Read existing AWS budgets and observed spend | Create/update budgets or originate notifications |
| **Non-production EC2** | Isolated manual planning/executor subsystem, explicitly disabled for execution by default | Automatic night/weekend shutdown jobs |

Cost allocation by `Team`, `Project`, and `Environment` requires those **AWS cost allocation tags to be activated**. Untagged or unsupported data remains unallocated rather than disappearing from the analysis. EKS namespace sampling requires Kubernetes Metrics Server, access to the cluster endpoint, and appropriate Kubernetes RBAC in addition to AWS IAM.

For implementation details and milestone gaps, see [AWS FinOps Scope](docs/AWS_FINOPS_SCOPE.md).

## Architecture

```text
                   Browser · React + TypeScript
                               │
                   Nginx · Same-Origin Gateway
                               │
                   Python Dashboard API
                  ┌────────────┼─────────────┐
                  │            │             │
            Authentication   FinOps       Inventory
            & Accounts       Billing      & Reviews
                  │            │             │
                  └────────────┼─────────────┘
                               │
               Local Persistent Control-Plane
               Accounts · Scans · Audit History
                               │
                     AWS Read-Only Role
                               │
               CE · EC2 · EBS · RDS · S3
                    CloudWatch · EKS
```

The dashboard, AWS read-only collector, Python optimization workflow, and optional non-production execution CLI have distinct responsibilities. The **dashboard does not invoke the privileged EC2 executor**. Interactive Terraform proposals and review records do not execute `terraform apply` or modify AWS resources.

For a local installation, Finovaunt can use source credentials from the default AWS CLI profile (including `demo-user` on an existing developer workstation) to assume the onboarded read-only role. On AWS-hosted workloads, SDK-provided short-lived role credentials are preferable. A role ARN alone is never a credential.

## Quick start

### Prerequisites

- Docker Engine and Docker Compose v2 on Linux or another Docker-capable host.
- Git, Bash, and `openssl` for initial local setup.
- For live AWS collection: AWS CLI v2 / SDK credentials with permission to use the configured read-only IAM role, plus the applicable service-read permissions.
- For standalone Python tooling: Python 3.11+ and `uv`.

### 1. Clone and configure

```bash
git clone https://github.com/sm-joe/finovaunt.git
cd finovaunt

# Generate a private first-install administrator password.
umask 077
printf 'FINOVAUNT_BOOTSTRAP_PASSWORD=%s\n' "$(openssl rand -hex 24)" > .env

docker compose config --quiet
```

**Do not overwrite an existing installation's `.env` or `data/` directory.** The bootstrap password initializes a new administrator; existing installations retain their persisted password hash.

### 2. Start the dashboard

```bash
docker compose up -d --build
docker compose ps
curl --fail http://127.0.0.1:8787/api/health
```

Open **http://127.0.0.1:4173**. Sign in as `admin` using the generated password in your private `.env`, then change it when prompted.

The default Compose bindings are loopback-only: dashboard `127.0.0.1:4173`, API `127.0.0.1:8787`. **Do not expose these development ports publicly.**

### 3. Connect an AWS account

Open **Cloud Accounts → Add AWS Account**, then provide its display name, 12-digit account ID, regional scope, and read-only IAM role ARN. For separate source and target IAM identities, both the `sts:AssumeRole` permission and the target role's trust policy must allow the operation. Supply an External ID only when the trust policy requires one.

To use an existing **default AWS profile** on a local Bash host with Docker Compose:

```bash
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_PROFILE
aws sts get-caller-identity

# Exports your existing default profile credentials into the current shell.
eval "$(aws configure export-credentials --format env)"

# Recreate the API to pass the new source credentials into Compose.
docker compose up -d --force-recreate api frontend
```

This development approach makes the source credentials available inside the API container. Restrict the credentials and local host; never commit, log, screenshot, or paste keys. Prefer narrowly scoped, automatically rotating workload identities for production. Temporary credentials may expire and require re-export and container recreation.

Use **Check AWS Credentials** for source-identity diagnostics and **Collect AWS Data / Collect FinOps Evidence** to obtain live evidence. A source-credential check does not by itself prove the target role can be assumed or that service permissions are complete.

### 4. Inspect or update evidence

Use **Overview**, **AWS FinOps**, **Resources**, and **Review Candidates** to inspect observed data and manual review opportunities. Changing an account's collector role or region requires a documented reason and creates a new configuration revision. Old scan evidence is retained as history but is not presented as current for the revised scope.

When AWS evidence is incomplete, expect explicit `not_assessed`, unknown, partial, or not-estimable status—not invented zero spend or savings.

## Day-to-day operations

```bash
# Logs and health
docker compose logs --tail=100 api frontend
docker compose ps
curl --fail http://127.0.0.1:8787/api/health

# Rebuild from current main without deleting persisted host data
git checkout main
git pull --ff-only origin main
docker compose up -d --build --force-recreate api frontend

# Stop services; normal down preserves host-mounted data
docker compose down
```

For the exact backup/restore procedure, stop the API first and use the checksum-verified `scripts/control_backup.py` utility. Backups include sensitive control-plane metadata and password hashes; encrypt and restrict them. See [Docker Operations](docs/DOCKER.md) for verified Bash commands, ownership considerations, and troubleshooting.

### Optional Python CLI and read-only scanning

```bash
uv sync --dev
uv run python -m src.app

# Explicit live AWS discovery; mock is reserved for local tests.
FINOPS_DISCOVERY_MODE=aws FINOPS_OUTPUT_DIR=artifacts-live \
  uv run python scripts/run_readonly_scan.py
```

The optional **non-production EC2 executor** is separate from the dashboard collector and requires a dedicated role, exact resource IDs, non-production tags, and an explicit execution opt-in. It is **not a scheduled shutdown service**; consult [AWS FinOps Scope](docs/AWS_FINOPS_SCOPE.md) before considering it.

## Configuration

| Setting | Purpose |
| --- | --- |
| `FINOVAUNT_BOOTSTRAP_PASSWORD` | Required initial administrator password (minimum 12 characters) |
| `FINOVAUNT_SECURE_COOKIES` | Set `true` behind properly configured HTTPS |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN` | Optional local AWS SDK source credentials passed to API via Compose; keep private |
| `AWS_DEFAULT_REGION` | API AWS SDK default region; account scans use onboarded regional scope |
| `FINOVAUNT_GITHUB_TOKEN` | Optional GitHub token for read-only scan artifact synchronization |
| `FINOPS_DISCOVERY_MODE` | `aws` for live CLI/scheduled collection; `mock` only for development simulation |
| `FINOPS_OUTPUT_DIR` | Restricted local directory for scan output |
| `FINOPS_AWS_REGION` | Region for the separate CLI/scheduled scan workflow |
| `FINOPS_AWS_LOOKBACK_DAYS` | CloudWatch history window for the CLI workflow |

For other settings and their constraints, see [`.env.example`](.env.example) and [Account Access & Billing](docs/ACCESS_AND_BILLING.md).

## Security and safety model

- **Least privilege** — Onboarded IAM roles should only grant required read actions; SDK credentials and External IDs are never frontend form secrets.
- **Protected workspace** — Initial administrator password rotation, session cookies, authenticated scan/review APIs, and account configuration audit records.
- **No implicit execution** — Cost collection, inventory, optimization reviews, and the dashboard are read-only. Privileged non-production EC2 actions are isolated behind a separately configured opt-in CLI.
- **Honest cost evidence** — A theoretical storage scenario or low CPU is not a verified saving. EKS and S3 telemetry do not establish directly attributable dollar charges.
- **Data protection** — Restrict `.env`, `data/`, `artifacts-live/`, backup archives, exported credentials, and API access.
- **Release verification** — CI performs backend/frontend tests, security checks, actual Docker builds, and Compose startup/persistence acceptance. This does not replace live AWS security review, release-to-release rollback validation, or signed publication.

Review [Security Policy](SECURITY.md) for private vulnerability reporting, deployment restrictions, trust boundaries, and remaining hardening requirements.

## Development and validation

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

GitHub Actions checks run on pull requests and `main`. The current product is **not** certified for multi-user internet-facing operation or published as a stable `v1.0.0`. Remaining work and release acceptance are tracked in [Release Readiness](RELEASE_READINESS.md).

## API surface

The dashboard uses a same-origin HTTP API. Representative endpoints:

| Area | Endpoints |
| --- | --- |
| Health | `GET /api/health` |
| Authentication | `POST /api/auth/login`, `POST /api/auth/logout`, `POST /api/auth/password`, `GET /api/auth/session` |
| AWS accounts | `GET /api/cloud-accounts`, `POST /api/cloud-accounts`, `POST /api/cloud-accounts/{account_id}/configuration`, `DELETE /api/cloud-accounts/{account_id}` |
| Billing | `POST /api/billing-scans`, `GET /api/billing-scans/{account_id}` |
| Inventory | `POST /api/inventory-scans`, `GET /api/inventory-scans/{account_id}` |
| FinOps assessments | `POST /api/finops-assessments`, `GET /api/finops-assessments?account_id=...` |
| Current dashboard | `GET /api/live-dashboard?account_id=...` |
| AWS source credentials | `GET /api/aws-credential-status?account_id=...` |
| Reviews and decisions | `GET /api/ebs-reviews`, `POST /api/ebs-reviews`, recommendation-decision endpoints |

Sensitive operations require a valid signed-in session. Configuration updates, reviews, and scan persistence are local operations; AWS resource power changes are **not** exposed by these dashboard endpoints.

## Documentation

| Guide | Covers |
| --- | --- |
| [AWS FinOps Scope](docs/AWS_FINOPS_SCOPE.md) | Supported services, implemented milestones, evidence limitations, optional executor |
| [Docker Operations](docs/DOCKER.md) | Installation, local AWS credentials, TLS considerations, recovery, troubleshooting |
| [Account Access & Billing](docs/ACCESS_AND_BILLING.md) | Sign-in, onboarding, IAM roles, billing data |
| [Recommendation Reviews](docs/RECOMMENDATION_REVIEWS.md) | Human review and audit trail |
| [Cost Evidence Report](docs/COST_EVIDENCE_REPORT.md) | Coverage and cost semantics |
| [Outcome Verification](docs/OUTCOME_VERIFICATION.md) | Verification before savings are realized |
| [CI/CD](docs/CI_CD.md) | Validation and release gates |
| [Release Readiness](RELEASE_READINESS.md) | Current stable-release blockers |
| [Security Policy](SECURITY.md) | Vulnerability reporting and deployment boundaries |

## Contributing and license

Issues and pull requests should include a focused problem statement, tests for behavior changes, and documentation updates where appropriate. Never add real AWS credentials, billing exports, account-specific inventory, or sensitive artifacts to test fixtures.

Finovaunt is distributed under the [MIT License](LICENSE). Copyright © 2026 sm-joe.

---

**Finovaunt — Measure with evidence. Optimize with confidence.**
