# Finovaunt v1.0.0 — Release Candidate Acceptance

**Release type:** stable, self-hosted, single-administrator, AWS-only FinOps dashboard.

**Status: BLOCKED until operator live AWS and release-to-release upgrade evidence is recorded.**
A successful source build, mocked CI test, and same-version restart are not substitutes for these gates.

## v1.0.0 product contract

The version includes account-scoped Cost Explorer service/tag/region spend, EC2/EBS/RDS inventory and manual review, S3 storage telemetry, EKS cluster and optional namespace usage, AWS Budgets read, a cohesive enterprise dashboard and auditable accounts, and local verified backup/restore.

Not claimed in v1.0.0: verified per-bucket billed cost, EKS namespace dollar allocation, automated non-production scheduling, externally validated instance rightsizing, forecast, realized savings, multi-user RBAC or internet-exposed production hosting. Default collection never performs AWS write actions.

## Release acceptance register

| Gate | Automated evidence | Additional required evidence | Decision |
| --- | --- | --- | --- |
| Source, dependencies, secrets, images | PR/main `build.yml` successful | Same immutable SHA for final build | CI-managed |
| Browser acceptance | Real Chromium login, dashboard, account navigation, profile, logout, mobile login | Confirm final UI in intended browser/resolution | CI-managed + operator |
| State retention | Compose restart, configuration revision and password rotation | Existing deployment / older version compatibility | Partially verified |
| Recovery | Offline checksum-verified backup, real restore, recovered account and login | Prior-version rollback on target host | Partially verified |
| AWS authentication | STS role trust/identity unit tests | Actual source credential → target role assumption | **NOT VERIFIED** |
| Cost Explorer | Paged linked-account filtering unit tests | Live month-to-date account data and empty/denied checks | **NOT VERIFIED** |
| EC2 / EBS / RDS | Read-only collector and inventory cap tests | Live complete enumeration, IAM and pagination acceptance | **NOT VERIFIED** |
| S3 / EKS | Explicit partial/unknown contracts and RBAC tests | Live service permissions, optional cluster visibility and errors | **NOT VERIFIED** |
| Security | Threat boundary, origin and login throttling tests, Trivy/dependency/secret scans | Operator IAM/network/runtime hardening review | **NOT VERIFIED** |
| Stable artifacts | Release workflow/attestation must be verified | Immutable tag, signed provenance, SBOM/checksums, release notes | **NOT VERIFIED** |

Mark only verifiable evidence as passing. Empty AWS inventory is valid when enumeration completes without truncation. Missing API authorization, unreadable evidence, wrong role or pagination truncation is **not** a passing acceptance result.

## Operator live AWS acceptance (Bash)

Do not commit the output or any AWS credentials. Use the existing default AWS CLI profile and the intended read-only target role.

```bash
aws sts get-caller-identity
export FINOVAUNT_EXTERNAL_ID='' # only needed if your existing role trust requires one

uv sync --dev
uv run python scripts/acceptance_live_aws.py \
  --account-id YOUR_12_DIGIT_AWS_ACCOUNT_ID \
  --role-arn arn:aws:iam::YOUR_12_DIGIT_AWS_ACCOUNT_ID:role/Finovaunt-RO-Scan-Role \
  --region us-east-1
```

This check uses the real production collector and returns a sanitized summary containing per-service status, counts and no billing amounts. It does not create, modify, start, stop or delete AWS resources. It cannot verify Kubernetes Metrics Server permissions from EKS control-plane inspection alone: verify optional namespace telemetry separately using a cluster with the necessary RBAC and network reachability.

## Deployment / rollback acceptance

1. **Back up** a known working Finovaunt installation, stop services, verify its archive and record its commit/tag.
2. Upgrade to the exact candidate commit and rebuild both images without removing `data/` or `artifacts-live/`.
3. Verify administrator login, account registrations, role edits, scan history, review records and dashboard integrity.
4. Stop the API, verify the backup, **restore** to a disposable recovery destination, and verify the original known-good application version reads the recovered state without loss.
5. Keep the original backup and record the tested commits, command exit statuses and failures. Do not treat a same-commit container recreation as release-to-release rollback evidence.

See [Docker Operations](DOCKER.md), [Security Policy](../SECURITY.md), and [CI/CD](CI_CD.md).

## Publication sequence (after all gates pass)

1. Merge only a reviewed release-hardening PR with all checks green and no unresolved release blockers.
2. Record operator live AWS acceptance and upgrade/recovery results, scrub any sensitive content, and review them against this register.
3. Freeze a commit and align application/package metadata with `1.0.0`.
4. Produce immutable release artifacts and SBOM, sign provenance with GitHub attestations, verify signatures with `gh attestation verify`, and record SHA-256 checksums.
5. Publish GitHub stable `v1.0.0` only for the verified commit; confirm downloadable assets, installation and documentation.
6. Move feature requests into separate future issues/PRs; never rewrite the published stable tag.

**Release policy:** an unverified item is a blocker, not a provisional PASS. No GitHub release should be published solely because the latest development CI is green.
