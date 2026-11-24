# Finovaunt v1.0.0

**First stable, self-hosted AWS FinOps release.** Finovaunt offers a unified, account-scoped workspace for AWS billing, utilization evidence, optimization review and accountable cost investigation.

## In this release

- Enterprise React dashboard with coherent login, logout, account administration and profile experience.
- AWS-only read-only collection using scoped role-based AWS IAM authorization.
- Cost Explorer billing by linked account/service, observed month-to-date snapshots, Team/Project/Environment/Region allocation.
- EC2, EBS and RDS inventory and human review candidates, with EBS optimization evidence and audit history.
- S3 bucket/tags and sampled StandardStorage data, without invented bucket-level charges.
- Amazon EKS cluster discovery with optional Kubernetes Metrics API namespace CPU and memory samples; not namespace dollar spend.
- Read-only display of existing AWS Budgets.
- Persisted account settings, collector revision history, read-only optimization evidence, offline checksum-verified backup and restore.
- Docker Compose deployment with loopback-only defaults and a non-root API; backend/frontend/security/image and browser/restore acceptance checks.

## Scope and limitations

This release targets a **single-administrator self-hosted deployment** on a trusted local or private host. It is not a publicly exposed multi-tenant SaaS, and does not guarantee complete AWS Organizations data, all-region inventory, or cost data from unavailable services. Privileged non-production EC2 execution is a separate opt-in CLI and is **not** an automatic shutdown scheduler.

No claim is made that forecast values, theoretical pricing scenarios, or CPU-only investigation candidates represent realized verified savings. S3 storage observations and EKS usage are not charge attribution. Features outside this scope remain future work.

## Installation and verification

Use the verified source bundle and release [README](../README.md) with Docker Compose, a private `FINOVAUNT_BOOTSTRAP_PASSWORD`, and an existing read-only AWS collector role. For local source credentials, use the standard AWS CLI profile chain; never publish secret keys. See [Docker Operations](DOCKER.md) and [Security](../SECURITY.md).

Verify the release artifact's SHA-256 checksum and GitHub signed build provenance:

```bash
sha256sum -c SHA256SUMS
gh attestation verify finovaunt-v1.0.0.tar.gz -R sm-joe/finovaunt
gh attestation verify finovaunt-v1.0.0.spdx.json -R sm-joe/finovaunt
```

OCI images, if published in the same approved release run, are pinned at `ghcr.io/sm-joe/finovaunt-api:v1.0.0` and `ghcr.io/sm-joe/finovaunt-dashboard:v1.0.0`. Match image provenance to its immutable digest when deploying.

**Publication prerequisite:** All items in [v1.0.0 Release Acceptance](RELEASE_V1_CHECKLIST.md) must have verified operator evidence before the stable publication workflow is authorized.
