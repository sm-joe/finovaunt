# Finovaunt — Stable v1.0.0 Release Evidence

**Status: NOT READY FOR STABLE PUBLICATION.**

This file is a live release gate. Do not substitute past test success or development CI for current production evidence. Historical functional closure is documented separately in `docs/RELEASE_READINESS.md`.

## Implemented development increments

- M1: protected scan endpoints; secure first-run credential; expiring sessions; verified empty-inventory no-op.
- M2: verified, paginated Cost Explorer billing with exact decimal evidence; cloud account lifecycle and deletion.
- M3 (partial): account-scoped single-region EC2, RDS, EBS read-only inventory, EBS pricing/PV evidence, explicit truncation metrics and historical optimization ledger.
- M4 (partial): signed-in live AWS dashboard, account billing, service breakdown, inventory, evidence-backed EBS reviews and historical findings.
- M5 (partial): account/scan-scoped EBS review approvals/rejections and durable audit history with no AWS deletion or Terraform apply.
- M6 (partial): Docker Compose configuration, Bash operations guide, security audits, container image builds and clean-start Compose smoke acceptance.

## Blocking work before stable publication

- M2: transactional durable backend data store, migrations, reliable multi-user session/role management and backup recovery.
- M3: fully integrated account/region scan dispatch, utilization evidence pipeline, verified resource cost attribution and broader safe optimization policies.
- M4: production UX acceptance, accessibility, error states, interaction QA and Playwright end-to-end suite.
- M5: durable scheduled jobs, proposal history integration, role-based review and verified outcome lifecycle.
- M6: verify real end-to-end clean-install and persistent upgrade/rollback acceptance in target environments, stable distribution versioning and comprehensive operations docs.
- Final audit: security and Docker build gates restored, and vulnerable `certifi` upgraded. Remaining: verify live AWS Pricing/EKS PV RBAC under the target role, full regional coverage, clean install and upgrades, and reproducibly signed/published artifacts.

## Development CI

PR and push checks now include backend tests, frontend build, Compose configuration, secret and dependency audits, Trivy Dockerfile/filesystem/IaC scans and both actual Docker builds. A real clean-start Compose HTTP smoke test was added. This still does not replace AWS acceptance, persisted upgrade/rollback, reliability/security review or a verified release distribution.

## Release decision

**Do not publish `v1.0.0` until every blocker above has corresponding current, reproducible evidence.** Keep the safe read-only and human-approval boundaries throughout development.
