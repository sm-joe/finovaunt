# Finovaunt — Stable v1.0.0 Release Evidence

**Status: NOT READY FOR STABLE PUBLICATION.**

This file is a live release gate. Do not substitute past test success or development CI for current production evidence. Historical functional closure is documented separately in `docs/RELEASE_READINESS.md`.

## Implemented development increments

- M1: protected scan endpoints; secure first-run credential; expiring sessions; verified empty-inventory no-op.
- M2: verified, paginated Cost Explorer billing with exact decimal evidence; cloud account lifecycle and deletion.
- M3 (partial): account-scoped EC2, RDS, EBS read-only inventory with dashboard visualization.
- M4 (partial): signed-in dashboard with overview, opportunities, assets, scan history and account onboarding.
- M5 (partial): human review decisions and audit history with no Terraform apply.
- M6 (partial): Docker Compose configuration, Bash operations guide and product/security documentation.

## Blocking work before stable publication

- M2: transactional durable backend data store, migrations, reliable multi-user session/role management and backup recovery.
- M3: fully integrated account/region scan dispatch, utilization evidence pipeline, verified resource cost attribution and broader safe optimization policies.
- M4: production UX acceptance, accessibility, error states, interaction QA and Playwright end-to-end suite.
- M5: durable scheduled jobs, proposal history integration, role-based review and verified outcome lifecycle.
- M6: clean-install Docker runtime and upgrade/rollback acceptance, stable distribution versioning and comprehensive operations docs.
- Final audit: restore disabled dependency/security scans and Docker builds, update vulnerable `certifi` lock, validate images, run AWS read-only acceptance, and sign/verifiably publish artifacts.

## Development CI

PR and push checks currently run backend tests, frontend build and Compose configuration. Security scanning and Docker image building are **temporarily disabled at the owner's direction**. This does not qualify for stable release readiness.

## Release decision

**Do not publish `v1.0.0` until every blocker above has corresponding current, reproducible evidence.** Keep the safe read-only and human-approval boundaries throughout development.
