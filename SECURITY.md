# Security Policy

Finovaunt is a **self-hosted, AWS-only FinOps platform** designed around read-only cloud evidence collection, scoped access, protected local administration and human-reviewed optimization decisions.

**Security reports are welcome.** Please report vulnerabilities **privately** and keep credentials, account identifiers, billing records and exploit details out of public issues.

## Report a vulnerability

**Preferred channel:** [GitHub Private Vulnerability Reporting / Security Advisories](https://github.com/sm-joe/finovaunt/security/advisories).

If private reporting is unavailable, contact the repository maintainers through a nonsensitive public message to request a confidential channel. **Do not publish reproduction steps, vulnerable endpoints, secrets or unredacted evidence.**

A helpful private report includes:

1. Affected component, source commit/version and deployment configuration.
2. Description of the security impact and realistic prerequisites.
3. Minimal reproducible steps using **synthetic, sanitized** data.
4. Whether authentication, AWS IAM, cross-account trust, network exposure or Kubernetes RBAC is required.
5. A proposed mitigation, if known.

Never include actual AWS credentials, session tokens, administrator passwords, External IDs, private keys, customer billing exports or sensitive infrastructure inventories. Test only infrastructure that you own or have permission to assess.

### Response and disclosure

Maintainers review incoming reports, attempt reproduction, evaluate severity and coordinate fixes and advisories when feasible. The project currently makes **no fixed acknowledgement, remediation or disclosure SLA**. We ask reporters to coordinate disclosure privately while a safe mitigation is prepared.

## Supported versions

| Distribution | Security maintenance |
| --- | --- |
| Main branch | Best-effort review and fixes with current CI checks |
| v1.0.0 release candidate | Under release acceptance; stable publication has **not yet been verified** |
| Unmerged branches, forks and old snapshots | No guaranteed security patch or backport support |

Consult [Release Acceptance](docs/RELEASE_V1_CHECKLIST.md) and [Release Readiness](docs/RELEASE_READINESS.md) for current verification. A passing CI scan is not a guarantee of safe public deployment.

## Security architecture

Finovaunt retains sensitive cloud and business metadata even when AWS requests are read-only. Security depends on both the application boundary and **how operators configure the host, IAM roles and network**.

| Surface | Implemented or intended boundary | Operator responsibility |
| --- | --- | --- |
| **Dashboard / API** | Same-origin Nginx gateway, session-protected administrative and collection endpoints | Limit network access, configure TLS before non-local access |
| **Administrator** | Explicit bootstrap password, first-use rotation, locally persisted password hash, bounded failed-login attempts | Generate a unique secret, restrict administrator access and monitor incidents |
| **Session** | HttpOnly and SameSite=Strict cookies, origin checks and defensive response headers | Use secure cookies with HTTPS; avoid exposure to untrusted origins |
| **AWS identity** | AWS SDK credential chain and STS role identity checks for target collection | Configure narrowly scoped AWS source permissions and role trust |
| **Collector** | Read-oriented billing, inventory, Kubernetes and storage telemetry | Grant only the necessary AWS Describe/List/Get and billing read actions |
| **EKS / Kubernetes** | TLS-validated cluster API and read-only metric/PV collection where authorized | Configure separate Kubernetes RBAC and endpoint network reachability |
| **Local state** | Persisted accounts, administrator, scan evidence, history and review records | Restrict host filesystem and backups; define encryption, retention and recovery policy |
| **Optional executor** | Separate opt-in non-production CLI with dedicated role and resource/tag checks | Maintain approval and execution separation; do not grant its write rights to collectors |

### Read-only dashboard, separate execution boundary

The normal Finovaunt dashboard **does not start or stop instances, resize databases, delete volumes, change Kubernetes objects or apply Terraform**. A recorded recommendation decision does not authorize execution.

A separately configured CLI, **scripts/nonprod_executor.py**, can perform explicitly selected non-production EC2 start/stop operations when its dedicated role, environment-tag and resource checks and execution opt-in all permit the action. This is **not an automatic scheduler**. Do not attach EC2 write actions to the dashboard's read-only role.

A failure to retrieve cloud evidence must remain **unavailable, partial or not assessed**. It must never silently become a zero-cost observation, successful inventory result or verified savings claim.

## Secure deployment baseline

### Authentication and network

- Generate a unique administrator password with at least 12 characters and store the bootstrap secret privately. The bootstrap value is only for a new installation; do not delete persisted state to reset credentials.
- Keep the default Compose listener bindings on **127.0.0.1:4173 (frontend)** and **127.0.0.1:8787 (API)**. Do not publish these ports directly to the internet.
- When deploying behind a controlled private reverse proxy, configure trusted HTTPS and set **FINOVAUNT_SECURE_COOKIES=true**. Review forwarded headers and allowed origins.
- Keep the protected Nginx-to-API route; do not expose privileged API endpoints directly or bypass session protection.
- Retain container hardening: non-root API identity, read-only root filesystem, dropped Linux capabilities and no-new-privileges, together with the separate persistent-volume ownership initialization helper.
- This release targets **single-administrator private hosting**. It does not claim multi-user RBAC or hardening for arbitrary internet-facing deployments.

### AWS IAM and credentials

- Prefer automatically rotated **AWS workload identities** (instance, task or pod roles) when the runtime supports them.
- Cross-account collection requires explicit **sts:AssumeRole** authorization on the source principal and appropriate target-role trust. A role ARN alone does not grant access.
- Scope permissions to required AWS services and resource contexts as AWS permits: Cost Explorer, AWS Budgets, EC2, EBS, RDS, S3, CloudWatch and EKS read operations.
- The source identity test **sts:GetCallerIdentity** confirms who is calling but does not prove target-role assumption or service-level authorization.
- Temporary credentials exported into a local Docker Compose process may be exposed to host/container inspection and expire. Remove them when switching to an AWS-native renewing workload identity.
- Never embed access keys, session tokens, External IDs or private credentials in frontend assets, Docker images, source control, test fixtures or public logs.
- EKS IAM access and Kubernetes RBAC are **separate controls**. Do not grant cluster-admin for the sake of a namespace metrics or persistent-volume read.

See [AWS FinOps Scope](docs/AWS_FINOPS_SCOPE.md) and [Account Access & Billing](docs/ACCESS_AND_BILLING.md) for current supported collection semantics.

## Data confidentiality and recovery

Local persisted state and output may contain AWS account identifiers, role ARNs, cost observations, inventory, administrator password hashes, review records and audit trails.

- Protect the private environment file, data and scan-artifact directories, plus any copied archives, with restrictive host permissions.
- Treat generated reports and debugging output as potentially sensitive even when billing amounts are not printed.
- Encrypt offline backups at rest and during transfer. The supplied archive tool **verifies integrity but does not encrypt backups**.
- Stop the API before backing up or restoring control-plane state. Preserve the original state until recovery has been verified.
- Test recovery against a **disposable destination** before overwriting active state. A same-version container restart does not establish prior-version rollback compatibility.
- Establish a retention and deletion policy appropriate for financial and infrastructure metadata.
- Account deletion removes **local Finovaunt records**; it is not an AWS resource deletion.

Basic offline backup and verification from the repository root:

~~~bash
docker compose stop api frontend
umask 077
python scripts/control_backup.py backup ./finovaunt-state.tar.gz
python scripts/control_backup.py verify ./finovaunt-state.tar.gz
docker compose start api frontend
~~~

Follow [Docker Operations](docs/DOCKER.md) for secure restore procedures, file ownership and rollback guidance.

## Security validation and release assurance

The Product CI workflow includes:

| Check | Purpose |
| --- | --- |
| Python backend tests and source compilation | Catch regressions in API, authentication, collector and state behavior |
| Frontend lint/type/build | Confirm the refactored React UI is valid without changing its design |
| Dependency and secret scans | Detect vulnerable components and accidentally committed secrets |
| Trivy and Dockerfile checks | Surface filesystem, dependency and configuration risks |
| Docker image builds and Compose startup | Validate container packaging and service health |
| Chromium browser acceptance | Exercise login, account navigation, profile, logout and responsive login |
| Persistence, backup and restore acceptance | Verify tested state survival and recovered administrator/account data |

These results apply only to the tested commit and CI environment. The **operator-owned** release gates additionally require actual AWS IAM/service testing, installation upgrade and prior-version rollback, private-host network review and artifact provenance verification.

The configured stable release workflow aims to generate OCI images, a source archive, SBOM, checksums and GitHub build attestations. **Do not describe these as published or verified until the GitHub release and attestations actually exist.**

### Security invariants for contributors

1. **Fail closed on identity and coverage:** IAM errors, pagination limits, incomplete price evidence and unreachable Kubernetes telemetry must not silently pass.
2. **Preserve account isolation:** Linked-account billing scope and collector revision must be respected; stale scans remain historical.
3. **Never escalate the standard collector:** Dashboard discovery and review cannot gain AWS mutation permissions.
4. **Maintain human review integrity:** Review approval is not authorization to run resource-changing commands.
5. **Do not claim unmeasured savings:** S3 capacity is not per-bucket billing, EKS namespace CPU is not workload spend, and storage price scenarios are not realized reductions.
6. **Do not weaken security gates to ship:** Document exceptions and investigate failures rather than suppressing or misrepresenting them.

## Related documentation

- [README — product overview and quick start](README.md)
- [Docker Operations](docs/DOCKER.md)
- [Account Access & Billing](docs/ACCESS_AND_BILLING.md)
- [AWS FinOps Scope](docs/AWS_FINOPS_SCOPE.md)
- [CI/CD and publication](docs/CI_CD.md)
- [Release Acceptance](docs/RELEASE_V1_CHECKLIST.md)

---

**Responsible disclosure, least-privilege access and explicit evidence boundaries are core to Finovaunt's design.**
