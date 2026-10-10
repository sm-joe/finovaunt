# Finovaunt v1 — Release Closure Record

**Release decision:** v1 is complete as a functional, conservative FinOps analysis and dashboard milestone. This is not a certification of production readiness.

**Closure date:** 2026-10-10

## Included in v1

- AWS resource/metrics collection and cost-evidence handling.
- Conservative recommendation behavior when cost or utilization evidence is incomplete.
- Human approval boundary for infrastructure proposal writes.
- Proposal/artifact integrity and rollback safeguards covered by the project's tests.
- Read-only dashboard API over scan artifacts and a Vite/React dashboard.
- Existing GitHub Actions read-only scan workflow using AWS OIDC.

## Validation record

The developer reported that tests passed after restoring the missing `src/tools/cloud_metrics.py` and `src/utils/cost_evidence.py` modules on 2026-10-10. The exact test command, collected-test count, and final output were not captured in this closure record. Therefore, this document does not claim that the entire test suite or every release-readiness command was independently verified here.

Previously observed AWS evidence:

- EC2 resource: `i-02dd62b24cadeccce` in `eu-central-1` (`euc1-vpn`).
- CPU telemetry: 336 of 336 expected hourly datapoints across 14 days; average CPU 0.15%, peak 46.69%.
- Memory telemetry was not available in the observed evidence.
- Cost Explorer resource amount for 2026-09-26 through (exclusive) 2026-10-10 was `$0.0000012271` USD. This is observed-period evidence, not a verified monthly resource cost.
- September account-level billing was `$15.2449304707`; it was grouped by service/region and must not be attributed to the individual EC2 resource.
- The conservative recommendation for the example resource was `no_change`, critical risk, human approval required, and `$0` savings.

These figures describe the observed scan only and are not a current billing statement.

## Known limitations — explicitly accepted for v1

1. **Memory coverage:** memory telemetry was absent for the observed EC2 resource. CPU alone is insufficient to prove safe downsizing.
2. **Cost attribution:** the observed resource-level amount is for a specific period and is not verified recurring monthly spend. Account-level totals are contextual only.
3. **Seasonality and workload:** workload stability, peak-season behavior, and application-level SLO impact have not been established by the recorded evidence.
4. **Realized savings:** a recommendation or cost delta does not prove realized savings. Verified outcomes require dated baseline/after evidence and explicit change/deployment evidence.
5. **Production execution:** the v1 workflow is designed to report and propose, not automatically apply Terraform or modify AWS resources. Human approval and a separate deployment process remain required.
6. **Dashboard access control:** the local read-only dashboard API has no user authentication. Keep it bound to loopback for local use; do not expose it publicly without an authenticated front door and deployment hardening.
7. **Operational validation:** the most recent full integrated AWS-to-dashboard run, scheduled-workflow health, backup/recovery, alerting, and production deployment were not independently confirmed as part of this closure.
8. **Test evidence:** tests were reported passing after source restoration, but the exact full-suite result was not recorded here. Do not infer coverage for tests that are absent from a checkout.

## Release policy

- No new v1 features or refactors are planned in this closure pass.
- Do not weaken guardrails to produce a non-zero savings estimate.
- Treat unknown or missing evidence as unknown; do not manufacture cost, dates, telemetry, approval, or deployment evidence.
- Keep the existing scheduled scan workflow and AWS OIDC permissions read-only.
- Dockerization is a packaging/deployment step and must not change the agent's approval or cloud-write behavior.

## v1 status

**Functional v1: declared complete.**

**Production readiness: not certified; limitations above are documented and accepted for this milestone.**
