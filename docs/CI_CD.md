# Finovaunt CI/CD and v1.0.0 Release Gates

Finovaunt's default branch is `main`. Normal PR and main pushes run the complete [Finovaunt Product CI](../.github/workflows/build.yml) workflow. Production releases are gated separately. **Green development CI does not, by itself, authorize v1.0.0 publication.**

## Required PR and main checks

| Gate | Implementation |
| --- | --- |
| Backend | Python 3.13, locked `uv` install, syntax checks, pytest |
| Frontend | Locked npm install and TypeScript / Vite production build |
| Configuration | Docker Compose validation |
| Secrets and dependency security | Dedicated reusable security workflow |
| Container security | Trivy scans and real API and dashboard image builds |
| Clean installation | Docker Compose boot and authenticated HTTP health |
| Persistent installation | Login, administrator password change, AWS role configuration revision, container recreation |
| Browser acceptance | Real headless Chromium sign-in, dashboard, AWS accounts, profile, logout, session rejection, mobile login |
| Recovery | Offline backup and checksum verification, then **actual restore**, container recreation and recovered state acceptance |

The application workflow uses [`build.yml`](../.github/workflows/build.yml), [`ci.yml`](../.github/workflows/ci.yml) and [`security.yml`](../.github/workflows/security.yml). Docker image publication does not run automatically for a PR.

## Release blockers not simulated in CI

A production v1.0.0 candidate must also pass all of the following on the intended self-hosted installation:

1. **Live AWS read-only acceptance:** source identity, exact target role assumption, Cost Explorer linked-account billing, EC2/EBS/RDS enumeration, S3 discovery and EKS discovery; partial coverage is not a successful acceptance result. Run `scripts/acceptance_live_aws.py` with authorized credentials.
2. **IAM and EKS authorization review:** check IAM read-only privileges, protected default source credentials, optional EKS Kubernetes metrics RBAC, and no AWS write calls in dashboard collection.
3. **Security and threat-model review:** same-origin login/mutations, request throttling, session expiration/rotation, private network binding, network and proxy hardening, sensitive-state storage and restore permissions.
4. **Release-to-release upgrade and rollback:** a real prior deployment upgraded with persisted data, then recovered using a verified pre-upgrade snapshot. A same-commit container recreation does not demonstrate compatibility between released versions.
5. **Distribution and provenance:** commit SHA, version metadata, immutable release/tag, build provenance, signed verifiable artifacts, SBOM/release notes and installation verification.

If an acceptance prerequisite is unavailable, mark it **NOT VERIFIED**, not PASS. Do not publish a stable release on the strength of mocked responses or browser-only smoke tests.

## Local developer verification (Bash)

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

For full Compose acceptance on a disposable test host, follow the steps in `build.yml`. Browser acceptance uses a real Chromium engine via Python Playwright; CI installs it in a separate temporary virtual environment. Development state and browser fixtures contain synthetic AWS accounts only and do not call AWS.

## Scheduled cloud scan workflow

[`finovaunt-scan.yml`](../.github/workflows/finovaunt-scan.yml) is the separate scheduled read-only scan workflow and uses AWS credential mechanisms configured for that workflow. It is **not** an automatic non-production start/stop scheduler. No read-only scan, review, or dashboard endpoint may modify infrastructure.

## Stable publication policy

Publish `v1.0.0` only after a final release candidate has green CI, the operator-owned live acceptance evidence is recorded, real backup/recovery and version-upgrade evidence exists, and release artifacts have verified signing/provenance. Do not move an existing stable tag after publication. Maintain a clear changelog and explicit unsupported-feature boundaries.
