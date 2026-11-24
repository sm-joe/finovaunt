# Finovaunt v1.0.0 — Release Readiness

**Release status: CODE FROZEN; PUBLICATION BLOCKED pending operator acceptance.**

This page describes the source and CI baseline for the first stable, self-hosted, single-administrator, AWS-only FinOps release. The authoritative evidence register and publication criteria are in [Release v1 Checklist](RELEASE_V1_CHECKLIST.md). Never interpret successful mocked tests or same-version restart checks as proof of live AWS compatibility or prior-version rollback.

## Verified on the release candidate main commit

The GitHub Actions product CI validates backend tests, frontend compilation, Docker images, configuration, dependency and secret scans, a signed-in Chromium browser journey, and Compose state retention. The Compose job also verifies checksum-backed state backup, actual restore, and recovered administrator login/account evidence.

The latest validated candidate must be rechecked against the immutable commit ultimately published as `v1.0.0`. CI status at another commit is not release evidence.

## Operator evidence still required

- Live AWS: source identity, target-role assumption, linked-account Cost Explorer, EC2/EBS/RDS inventory, S3 and EKS read-only collection, service permission-denied and empty-inventory behavior.
- Upgrade and rollback: back up a **previous working deployment**, upgrade to the exact release candidate without data loss, restore a saved snapshot to a disposable destination, then verify that the prior known-good version can read its recovered state.
- Security: IAM least privilege, local administrator credentials, host/network exposure, runtime permissions, and acceptance of operational limitations.
- Final publication: approved release reference, immutable `v1.0.0` tag, SBOM, SHA-256 checksums, GitHub build attestations, OCI images, and downloadable release assets.

Do not check these off without dated, reproducible evidence. Do not commit AWS access keys, billing details, customer identifiers, or unsanitized logs.

## Release commands (Bash)

From the repository root:

```bash
uv sync --dev
uv run python -m pytest -q
cd frontend
npm ci
npm run lint
npm run typecheck
npm run build
cd ..
FINOVAUNT_BOOTSTRAP_PASSWORD=local-validation-only docker compose config --quiet
git diff --check
git status --short
```

For live AWS verification, follow the read-only command in [Release v1 Checklist](RELEASE_V1_CHECKLIST.md). For installation, backup/restore, and rollback, follow [Docker Operations](DOCKER.md). See [Security Policy](../SECURITY.md) for deployment boundaries.

## Stable-release decision

The [Publish Stable Release workflow](../.github/workflows/publish-stable.yml) requires operator confirmations and an evidence reference; do not set these to true before the corresponding acceptance evidence exists. It must be triggered from `main` only after all release blockers are cleared. Keep the published tag immutable and handle later requests through new PRs.
