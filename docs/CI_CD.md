# Finovaunt CI/CD and Release Gates

## Temporary product-development mode

During the M1–M6 enhancement phase, the owner requested disabling **security scans and Docker image builds** on every pull request and push. The current `.github/workflows/build.yml` therefore invokes the reusable `.github/workflows/ci.yml` as the lightweight product CI.

The product CI checks:
- Python package install, syntax compilation and backend tests
- Locked npm installation and React/TypeScript production build
- Docker Compose **configuration** validation (`docker compose config --quiet`, not an image build)

The `.github/workflows/security.yml` file remains in the repository but is not invoked by the product-development workflow. Docker image publication to GHCR is likewise disabled for PRs and pushes. This is temporary and **does not imply security approval**.

## Before stable v1.0.0

Restore the complete release pipeline with all of the following gates:

1. Backend tests, type-checking and linting.
2. Frontend TypeScript validation, ESLint, build and Playwright end-to-end tests.
3. Secret scanning, Python and npm dependency audits, and Trivy filesystem/IaC scans.
4. Reproducible API/dashboard Docker image builds and vulnerability checks.
5. Self-hosted clean-install, login, AWS role onboarding, billing, inventory, and recommendation review acceptance.
6. Durable backup/restore tests and recovery of interrupted scan jobs.
7. Live read-only AWS acceptance, including empty inventories, missing telemetry and cost attribution boundaries.
8. Verified release artifacts, version metadata, release notes and license/security documents.

The previous security workflow identified an outdated vulnerable `certifi 2026.7.22` dependency lock; the repaired version must be resolved into `uv.lock` and audited before release. Do not hide a high/critical finding to obtain a green release badge.

## CLI validation (Bash)

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

If any command fails, correct the implementation and rerun all affected checks. GitHub status must be based on the exact commit being merged or tagged.

## Historical scan workflow

`.github/workflows/finovaunt-scan.yml` remains the separately scheduled AWS read-only scanner, using GitHub OIDC. It can report empty inventory as a no-op but must never fabricate asset utilization or savings. Successful scan artifacts may be synchronized by the dashboard when an appropriate GitHub token is configured.

## Publication policy

Only publish signed, verified, immutable release artifacts after all release gates are reinstated and passing. Development green CI is **not** proof of stable release readiness.
