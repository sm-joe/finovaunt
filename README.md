# Finovaunt

### AWS FinOps visibility, backed by evidence.

**Finovaunt** is a self-hosted, AWS-only FinOps platform for analyzing cloud spend, investigating underutilized resources, and documenting optimization decisions. It brings account-scoped billing, infrastructure inventory, cost allocation, and review evidence together in a responsive enterprise dashboard.

[![Product CI](https://github.com/sm-joe/finovaunt/actions/workflows/build.yml/badge.svg)](https://github.com/sm-joe/finovaunt/actions/workflows/build.yml)
[![MIT License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![AWS Only](https://img.shields.io/badge/Cloud-AWS%20Only-232F3E)
![Self Hosted](https://img.shields.io/badge/Deployment-Self--Hosted-244D61)

**[Quick Start](#quick-start) · [Capabilities](#capabilities) · [Architecture](#architecture) · [Operations](docs/DOCKER.md) · [Security](SECURITY.md)**

> **Release status:** The v1.0.0 candidate passed Product CI, but the stable release has not yet been published. [Release acceptance](docs/RELEASE_V1_CHECKLIST.md) records the remaining verification required for signed publication. A green CI badge is not a production certification.

## Why Finovaunt?

Cost data is useful when teams can connect **what AWS billed**, **which resources exist**, and **what evidence supports an optimization decision**.

- **Account-aware visibility** — Service spend, historical scans, regional and activated tag allocation.
- **Operational context** — Cloud inventory alongside utilization and capacity observations.
- **Human-led decisions** — Review candidates, document reasoning and retain evidence history.
- **Read-only by default** — Everyday collection and dashboard review do not mutate AWS resources.
- **Explicit uncertainty** — Unknown access, incomplete inventory, theoretical scenarios and unverified savings are clearly distinguished.

Finovaunt is currently designed for a **private, single-administrator, AWS-only deployment**. It is not a multi-tenant SaaS service or autonomous production remediation engine.

## Capabilities

| Domain | What Finovaunt provides |
| --- | --- |
| **AWS billing** | Account-scoped Cost Explorer service spending, linked-account filtering, historical snapshots, tag and region grouping |
| **Resource inventory** | Region-scoped EC2, EBS and RDS discovery with inventory completeness and truncation indicators |
| **Optimization reviews** | CPU investigation signals, EBS attachment/pricing scenarios, Kubernetes PV checks and an auditable human review ledger |
| **Storage** | S3 buckets, location, tags and sampled storage telemetry; EBS size, attachment, provisioned attributes and indicative pricing |
| **Kubernetes** | EKS cluster inventory and optional namespace CPU/memory observations when Kubernetes RBAC and Metrics Server allow |
| **Governance** | Read existing AWS Budgets, account-scoped evidence, collector configuration revisions and historical decisions |
| **Administration** | Local administrator login, required initial password rotation, cloud account onboarding and credential diagnostics |
| **Operations** | Docker Compose deployment, persisted local state, checksum-verified offline backup and actual restore testing |

### Evidence, not invented savings

| Signal | Correct interpretation |
| --- | --- |
| Cost Explorer billing | Observed spend for the account, period and supported grouping |
| Low CPU / unattached EBS | Manual investigation candidate, never proof that a change is safe |
| EBS monthly storage estimate | Illustrative storage-only pricing scenario, not realized savings |
| S3 metrics | Capacity observations, not verified per-bucket billed costs |
| EKS namespace usage | CPU/memory usage, not attributable workload dollar spend |
| Missing permissions or truncated scans | Partial, unavailable or unknown — not an implicit zero or PASS |

**Not claimed:** automatic shutdown scheduling, per-bucket billed cost, EKS namespace dollar allocation, resource-level CUR reconciliation, verified forecasts, automatic safe rightsizing, or independently established realized savings. The separate optional non-production EC2 executor is disabled by default and is not invoked by the dashboard.

See [AWS FinOps Scope](docs/AWS_FINOPS_SCOPE.md), [Cost Evidence Report](docs/COST_EVIDENCE_REPORT.md) and [Outcome Verification](docs/OUTCOME_VERIFICATION.md).

## Product workflow

1. **Sign in** to the private administrator workspace.
2. **Add an AWS account** with its account identifier, region and intended read-only collector role.
3. **Check credentials and collect AWS data** using real source identity and service permissions.
4. **Investigate** costs, allocations, inventory, recommendations and incomplete coverage.
5. **Record a human review** without triggering changes to infrastructure.
6. **Recollect evidence** to compare what changed, with historical records kept distinct from current findings.

The existing refactored React/TypeScript frontend covers login, account management, overview, FinOps analysis, resource review and profile workflows. This documentation change does **not** modify UI code or styling.

## Architecture

~~~text
            React / TypeScript Browser
                       |
              Nginx Same-Origin Gateway
                       |
               Python Dashboard API
                /        |         \
         Administrator  Accounts   FinOps Reviews
         Authentication & Scans    and Evidence
                \        |         /
                  Persisted Local State
                       |
               AWS Credential Chain
                       |
            Read-Only AWS Role / STS
                       |
     Cost Explorer · Budgets · EC2 · EBS · RDS
              S3 · CloudWatch · EKS
~~~

**Security boundary:** Ordinary dashboard collection uses AWS read permissions. A separate explicit opt-in CLI can operate on selected non-production EC2 instances with dedicated authorization, but is **not** part of normal dashboard collection or a scheduler.

| Layer | Technology |
| --- | --- |
| Frontend | React, TypeScript and Nginx |
| Backend | Python and AWS SDK (boto3) |
| Cloud evidence | Cost Explorer, Budgets, STS, EC2/EBS/RDS, S3, CloudWatch and EKS |
| Runtime | Docker Engine and Docker Compose v2 |
| State | Local persisted accounts, scans, review and audit history |
| Quality | Backend tests, frontend checks, container builds, Chromium browser tests and Compose restore acceptance |

## Quick start

### Prerequisites

- Linux or Docker-capable host with **Bash, Git, OpenSSL, Docker Engine and Docker Compose v2**.
- For live collection, AWS CLI v2/source credentials authorized to read the intended account or assume the target read-only role.
- Python 3.11+ and [uv](https://docs.astral.sh/uv/) for optional host-side commands.

### 1. Clone and configure

~~~bash
git clone https://github.com/sm-joe/finovaunt.git
cd finovaunt

# Generate a private initial password for a NEW installation.
umask 077
printf 'FINOVAUNT_BOOTSTRAP_PASSWORD=%s\n' "$(openssl rand -hex 24)" > .env

docker compose config --quiet
~~~

**Do not replace an existing installation's environment file or delete its data directory.** The bootstrap password is for initial setup; existing deployments retain the persisted password hash.

### 2. Run the dashboard

~~~bash
docker compose up -d --build
docker compose ps
curl --fail http://127.0.0.1:8787/api/health
~~~

Open **http://127.0.0.1:4173**, sign in as **admin** using the generated private password and complete the prompted password change.

The default frontend and API bindings are **loopback-only** (ports 4173 and 8787). **Do not publicly expose either development endpoint.** For TLS and private deployment requirements, read [Security](SECURITY.md) and [Docker Operations](docs/DOCKER.md).

### 3. Connect your AWS account

In **Cloud Accounts**, add an account name, its 12-digit ID, collection region and read-only IAM role ARN. Cross-role collection requires the source principal's STS AssumeRole permission and the target role's trust policy. Supply an External ID only if the trust relationship requires it.

For a **local development environment** using an existing AWS CLI default profile:

~~~bash
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_PROFILE
aws sts get-caller-identity
eval "$(aws configure export-credentials --format env)"

# Make current session credentials available to the API container.
docker compose up -d --force-recreate api frontend
~~~

Temporary environment credentials expire, can be visible to local processes and must never be committed or logged. **Prefer rotating AWS workload identities** on AWS-hosted deployments. A source identity check alone does not prove successful target-role assumption or complete service authorization.

Use the dashboard's **Check AWS Credentials** and collection actions. Optional EKS namespace sampling requires additional cluster network access, Kubernetes Metrics Server and read-only Kubernetes RBAC.

### 4. Explore and review

Use the account-aware overview, AWS FinOps, resources and review pages to investigate current evidence and preserve manual decisions. Changing an account role or region creates a new collector revision: old scans remain historical rather than being misrepresented as fresh evidence.

See [Account Access & Billing](docs/ACCESS_AND_BILLING.md) for credentials and onboarding details.

## Operations and recovery

~~~bash
docker compose ps
docker compose logs --tail=100 api frontend
curl --fail http://127.0.0.1:8787/api/health

# Normal shutdown preserves host-mounted state.
docker compose down
~~~

For an offline backup, **stop the API** and protect the output archive:

~~~bash
docker compose stop api frontend
umask 077
python scripts/control_backup.py backup ./finovaunt-state.tar.gz
python scripts/control_backup.py verify ./finovaunt-state.tar.gz
docker compose start api frontend
~~~

Backups contain sensitive AWS metadata and administrator password hashes. The utility verifies archive checksums, **not confidentiality**; encrypt and restrict archives. Restoration can overwrite state. Follow [Docker Operations](docs/DOCKER.md) for the full restore, ownership and rollback procedure.

### Optional Python tools

~~~bash
uv sync --dev
uv run python -m src.app

# Explicit live, read-only scan.
FINOPS_DISCOVERY_MODE=aws FINOPS_OUTPUT_DIR=artifacts-live \
  uv run python scripts/run_readonly_scan.py
~~~

### Configuration reference

| Variable | Purpose |
| --- | --- |
| FINOVAUNT_BOOTSTRAP_PASSWORD | Unique initial administrator password (minimum 12 characters) |
| FINOVAUNT_SECURE_COOKIES | Enable with correctly configured HTTPS |
| AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_SESSION_TOKEN | Optional local source credentials (sensitive and typically temporary) |
| AWS_DEFAULT_REGION | Default AWS SDK region; scans also use the onboarded account's region |
| FINOVAUNT_GITHUB_TOKEN | Optional token for read-only scan artifact synchronization |
| FINOPS_DISCOVERY_MODE | AWS for live collection; mock for local simulation |
| FINOPS_OUTPUT_DIR | Restricted directory for scan artifacts |
| FINOPS_AWS_REGION / FINOPS_AWS_LOOKBACK_DAYS | Optional CLI regional scope and history window |

Consult [.env.example](.env.example). Never commit production credentials, exports, or local scan artifacts.

## Developer validation

~~~bash
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
~~~

[Product CI](https://github.com/sm-joe/finovaunt/actions/workflows/build.yml) covers application checks, security scans, container builds, actual Chromium navigation and Compose state retention/restore. It does **not** establish live AWS or prior-version upgrade/rollback acceptance.

The approval-gated stable publication workflow is configured to build OCI images, a source archive, SBOM, SHA-256 checksums and GitHub build attestations. See [Release Acceptance](docs/RELEASE_V1_CHECKLIST.md) before relying on any stable distribution.

## Documentation

| Guide | Purpose |
| --- | --- |
| [AWS FinOps Scope](docs/AWS_FINOPS_SCOPE.md) | Service implementation and evidence boundaries |
| [Account Access & Billing](docs/ACCESS_AND_BILLING.md) | IAM assumptions, onboarding and billing |
| [Docker Operations](docs/DOCKER.md) | Installation, local credentials, backup and troubleshooting |
| [Recommendation Reviews](docs/RECOMMENDATION_REVIEWS.md) | Human decision and audit workflows |
| [Cost Evidence Report](docs/COST_EVIDENCE_REPORT.md) | Spend and cost confidence |
| [Outcome Verification](docs/OUTCOME_VERIFICATION.md) | Verification before claiming realized savings |
| [CI/CD](docs/CI_CD.md) | Validation, release and provenance |
| [Release Readiness](docs/RELEASE_READINESS.md) | Pending operator acceptance |
| [Security Policy](SECURITY.md) | Confidential reports and deployment boundaries |

## Contributing and license

Changes should include a clear problem statement, relevant tests and documentation. **Do not include real AWS account data or credentials in public issues and test fixtures.** Report vulnerabilities privately using [GitHub Security Advisories](https://github.com/sm-joe/finovaunt/security/advisories).

Finovaunt is licensed under [MIT](LICENSE). Copyright © 2026 sm-joe.

---

**Finovaunt — Measure with evidence. Optimize with confidence.**
