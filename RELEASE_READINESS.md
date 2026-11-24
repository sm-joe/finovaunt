# Finovaunt — Stable v1.0.0 Release Evidence

**Status: RELEASE CANDIDATE HARDENING — STABLE PUBLICATION BLOCKED ON LIVE ACCEPTANCE.**

This file is a live release gate. Do not substitute past test success or development CI for current production evidence. Historical functional closure is documented separately in `docs/RELEASE_READINESS.md`.

## Implemented development increments

- M1: protected scan endpoints; secure first-run credential; expiring sessions; verified empty-inventory no-op.
- M2: verified, paginated Cost Explorer billing with exact decimal evidence; cloud account lifecycle and deletion.
- M3 (partial): account-scoped single-region EC2, RDS, EBS read-only inventory, EBS pricing/PV evidence, explicit truncation metrics and historical optimization ledger.
- M4 (partial): signed-in live AWS dashboard, account billing, service breakdown, inventory, evidence-backed EBS reviews and historical findings.
- M5 (partial): account/scan-scoped EBS review approvals/rejections and durable audit history with no AWS deletion or Terraform apply.
- M6 (partial): Docker Compose, Bash operations guide, security audits, image builds, clean-start HTTP smoke acceptance, checksum-verified offline backup/restore, and persisted account/password acceptance across container recreation.

## Blocking work before stable publication

- M2: transactional durable backend data store, migrations, reliable multi-user session/role management and backup recovery.
- M3: fully integrated account/region scan dispatch, utilization evidence pipeline, verified resource cost attribution and broader safe optimization policies.
- M4: real Chromium browser smoke covers login, dashboard, AWS accounts, profile, logout and mobile login. Accessibility and broader interactive/cross-browser acceptance remain required for internet-exposed deployments.
- M5: durable scheduled jobs, proposal history integration, role-based review and verified outcome lifecycle.
- M6: CI now tests clean install, password/account persistence, real offline backup **and restore**, and recovered application state. Remaining: release-to-release upgrade/rollback on target installations, stable distribution versioning and live operations acceptance.
- Final audit: security and Docker build gates restored, vulnerable `certifi` upgraded, login throttling and browser/recovery acceptance added. Remaining: verify live AWS Pricing/EKS PV RBAC under the target role, full regional coverage, release-to-release upgrades and signed/published immutable artifacts.

## Scoped v1.0.0 Candidate

A frozen, **single-administrator, private/self-hosted AWS-only v1.0.0 scope** is defined in [Release Candidate Acceptance](docs/RELEASE_V1_CHECKLIST.md). Richer FinOps cost attribution, automated scheduling, and multi-user capabilities are explicitly deferred and not represented as complete v1.0.0 features.

PR and push checks now include backend tests, frontend build, Compose configuration, secret and dependency audits, Trivy Dockerfile/filesystem/IaC scans and both actual Docker builds. A real clean-start Compose HTTP smoke test, persisted-state upgrade exercise and verified offline backup check are included. This still does not replace AWS acceptance, persisted upgrade/rollback, reliability/security review or a verified release distribution.

## Stable artifact publication

A manually dispatched, operator-attested publication workflow in `.github/workflows/publish-stable.yml` is prepared to build verified source and OCI artifacts, publish an SPDX SBOM and Sigstore-backed GitHub provenance, and create the immutable release. It is **not run by PR CI** and must not be dispatched until live AWS acceptance, target-host upgrade/rollback and security review are independently evidenced.

## Release decision

**Do not publish `v1.0.0` until every blocker above has corresponding current, reproducible evidence.** Keep the safe read-only and human-approval boundaries throughout development.
