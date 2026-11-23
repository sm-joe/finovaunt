# Security Policy

Finovaunt is an AWS-only, self-hosted FinOps platform that emphasizes **read-only collection, scoped authorization, traceable cost evidence, and explicit operator control**.

Security reports are welcome. Please use **private disclosure** and do not expose exploitable findings or customer/cloud data in public issues.

## Report a vulnerability

**Preferred confidential channel:** [GitHub Private Vulnerability Reporting / Security Advisories](https://github.com/sm-joe/finovaunt/security/advisories).

If the repository's private vulnerability reporting option is unavailable, **do not open a public issue containing exploit details**. Request a private reporting channel from the repository maintainers using a nonsensitive public message, without including vulnerability details or secrets.

A useful report includes:

1. The affected component, commit or development version, and deployment scenario.
2. A clear description of the vulnerability and its security impact.
3. Reproduction steps and a minimal, sanitized proof of concept.
4. Any required preconditions, such as AWS IAM permissions, network exposure, or authentication state.
5. Potential mitigations or remediation suggestions, if known.

**Never include** real credentials, session tokens, private keys, IAM External IDs, administrator passwords, live billing exports, AWS account identifiers, sensitive inventory, or customer data. Use synthetic identifiers and redact logs. Do not perform destructive testing against systems you do not own or administer.

### Coordinated handling

Maintainers will review submitted advisories, attempt to reproduce relevant reports, assess the impact, and coordinate a patch and disclosure as appropriate. The project does **not** currently promise a fixed acknowledgement, remediation, or disclosure service-level agreement. Please avoid public disclosure until a safe mitigation or coordinated advisory is available.

## Supported versions and release status

| Version / branch | Security support |
| --- | --- |
| `main` (active development) | Best-effort security fixes and current CI checks; **not an SLA-backed production release** |
| Development branches and unmerged PRs | Not supported distributions |
| Stable `v1.0.0` | **Not published**; maintenance policy will be specified when released |
| Older source snapshots / local forks | No guaranteed patch backports |

Refer to [Release Readiness](RELEASE_READINESS.md) for outstanding production gates. A passing security scan or Docker build is not a guarantee that the deployment is secure.

## Threat model and trust boundaries

Finovaunt processes sensitive AWS account metadata, billing observations, inventory details, administrator authentication data, and optimization review records. Treat its state as confidential even when every AWS API call is read-only.

| Surface | Current security boundary | Operator responsibility |
| --- | --- | --- |
| **Browser and API** | Session-authenticated account, collection, and review endpoints; same-origin dashboard gateway | Keep the service local/private; deploy HTTPS and security controls before wider access |
| **Local administrator** | Explicit bootstrap password; mandatory first-use rotation; persisted password hash | Generate a unique initial password and protect administrator access |
| **Session cookies** | HttpOnly and SameSite=Strict; optional secure-cookie flag | Enable secure cookies with TLS and restrict session access |
| **AWS source identity** | Standard SDK credential chain; scoped target-role assumption and identity verification | Supply valid credentials securely; do not grant unnecessary privileges |
| **Read-only collector** | Cost Explorer, AWS Budgets, EC2/EBS/RDS, S3, CloudWatch and EKS inspection | Restrict IAM policy to the required AWS API actions and onboarded account |
| **Kubernetes / EKS** | Signed EKS authentication and TLS-verified cluster API; read-only metrics/PV inspection | Provide only the necessary Kubernetes RBAC; do not grant cluster-admin |
| **Persisted state** | Local control-plane, scan evidence, account configuration audit and review history | Restrict host mounts, encrypted backups, access permissions and retention |
| **Optional EC2 executor** | Separate disabled-by-default CLI with dedicated IAM role, tag/resource checks, explicit execution flag | Keep execution credentials separate and enforce approvals and deployment controls |

The normal dashboard collector **does not require AWS write access** and does not call the non-production executor. Dashboard reviews only record decisions; they do not run Terraform, delete volumes, change Kubernetes objects, or start/stop EC2 instances.

### Optional privileged execution is a different security domain

`scripts/nonprod_executor.py` is **not** a dashboard feature or automatic scheduler. It can invoke EC2 start/stop APIs only after explicit opt-in with a separately trusted, narrowly scoped `Finovaunt-NonProd-Executor-Role`, individually selected instance IDs, permitted non-production environment tags, and the required execution flag. It rejects EKS/Kubernetes and Auto Scaling-managed targets in its inspected inventory. This is **not** a substitute for independent change approval, runtime authorization, event logging, expiry of approvals, or scheduling safety.

Never add `ec2:StartInstances`, `ec2:StopInstances`, or other cloud-modifying actions to the standard Finovaunt read-only collector role merely to make dashboard collection work.

## AWS credentials and IAM guidance

- Prefer short-lived AWS workload role credentials where the runtime supports them. Use STS and narrowly scoped role trust for cross-account collection.
- For **local Docker Compose**, the default AWS CLI profile may provide source credentials to the API container when deliberately exported into the host shell. Those credentials can be visible to container processes and are captured during container creation. If temporary, they must be refreshed after expiry.
- A role ARN stored during onboarding is **not** proof of identity or a credential. Validate STS role assumption, account isolation, and individual service access before considering evidence complete.
- Never put AWS access keys, secret keys, session tokens, External IDs, profile contents, or private certificate material into source control, frontend code, public CI logs, screenshots, or issue descriptions.
- A missing service permission must result in unavailable or not-assessed evidence, not simulated resources or fabricated cost.
- Cost Explorer tag data may require activation of cost allocation tags; namespace costs and S3 per-bucket billing must not be inferred from incomplete telemetry.

IAM authorization and Kubernetes RBAC are independent. EKS `DescribeCluster` access does not grant cluster metrics or PV access. Grant only the Kubernetes read verbs and resources required for the configured assessment.

## Authentication, network and deployment

- **Use a unique bootstrap password.** `FINOVAUNT_BOOTSTRAP_PASSWORD` initializes a new deployment; first-login password rotation is required. Do not delete the state file to reset credentials.
- **Use private network access.** The default Compose configuration binds the frontend to `127.0.0.1:4173` and API to `127.0.0.1:8787`. Do not publish either endpoint to the internet or expose the backend independently of the same-origin gateway.
- **Require HTTPS outside localhost.** Terminate TLS using a trusted reverse proxy and set `FINOVAUNT_SECURE_COOKIES=true`. Ensure forwarded headers and allowed origins match the deployed access model.
- **Protect browser sessions.** Session cookies use HttpOnly and SameSite=Strict. Existing origin checks are useful safeguards but are not a substitute for a complete production CSRF threat review, request-rate controls, multi-user RBAC, auditability, and security testing.
- **Use least privilege at runtime.** The API runs as a non-root service, has a read-only container filesystem, drops Linux capabilities, and uses no-new-privileges. A separate, short-lived Compose initialization helper adjusts persistent data ownership. Keep these controls enabled.
- **Limit untrusted network and webhook exposure.** Only access configured AWS/EKS endpoints; do not make the local API publicly reachable as a debugging shortcut.

See [Docker Deployment and Operations](docs/DOCKER.md) for the supported current configuration.

## Sensitive data, backups and logging

Finovaunt's local persisted state can include password hashes, AWS account IDs, IAM role ARNs, inventory findings, billing and optimization records, reviewer names, and other sensitive business metadata.

- Restrict `.env`, `data/`, `artifacts-live/`, backup archives, and the host's AWS credential chain. Avoid copying these files into public repositories, Docker build contexts that publish them, or unprotected shared folders.
- The offline backup utility `scripts/control_backup.py` supports checksum verification, unsafe-path rejection, and explicit restore. Backups are **not encrypted by the tool**; encrypt at rest and in transit and limit access to the archive.
- Stop the API before taking an offline backup or restoring state. Confirm backup validity and preserve the original state until recovery is verified.
- Minimize application and CI logs; never enable debug logging that exposes raw credentials or session tokens. Sanitize resource/account identifiers and billing details before publishing diagnostics.
- Treat copied production data used for testing as confidential. Prefer synthetic fixtures.
- Establish an operator-owned retention, recovery, and deletion policy appropriate to the sensitivity of AWS billing and infrastructure metadata.

**Account deletion affects locally persisted Finovaunt history; it does not delete AWS resources.** Confirm backups and intended evidence retention before deleting accounts or restoring older archives.

## Security checks and validation

The repository's product CI currently checks:

| Gate | Purpose |
| --- | --- |
| Python backend tests and compilation | Prevent API, credential, collector, and persistence regressions |
| React / TypeScript frontend validation and build | Detect UI integration and type errors |
| Secret scanning | Identify accidentally committed sensitive material |
| Python and Node dependency checks | Identify vulnerable dependencies |
| Trivy filesystem, IaC and Dockerfile checks | Surface known image/configuration/security issues |
| API and dashboard Docker image builds | Confirm both runtime artifacts build |
| Compose configuration and clean-start smoke | Validate API/frontend startup and HTTP health |
| Persisted-state recreation and backup verification | Guard against state loss during tested container recreation |

CI results are tied to the checked commit and do not certify independent production security. Do not weaken required checks, suppress actionable findings without documented analysis, or publish unsigned/unvalidated artifacts merely to obtain a passing badge.

Important outstanding production-security gates include stronger CSRF and rate-limit defenses, robust multi-user authorization, transactional persisted storage and migration/rollback testing, live IAM/EKS acceptance, security-focused frontend end-to-end tests, operational monitoring, and verified signed distributions.

## Security design invariants

Security fixes and new features must preserve these rules:

1. **Fail closed:** incomplete AWS identity, trust, pricing, Kubernetes visibility, or pagination evidence must not silently become a PASS, a verified zero, or a savings claim.
2. **Preserve account scope:** AWS billing requests must be linked-account-scoped; role/region changes invalidate the current view of old-scoped evidence without deleting the audit trail.
3. **No write escalation:** ordinary inventory, collection, dashboards, and review workflows never acquire AWS mutation permissions.
4. **Keep history trustworthy:** reviews record the collector revision and source evidence; a review approval is not execution authorization.
5. **Disclose uncertainty:** S3 storage metrics are not billed bucket charges; EKS CPU/memory samples are not namespace spending; scenario savings are not realized savings.
6. **Maintain separation of duties:** any later automated shutdown or write workflow must use a separately authorized subsystem, explicit opt-in, auditable approvals, and safeguards for production workloads.

## Useful references

- [README and secure local setup](README.md)
- [AWS-only collection and executor scope](docs/AWS_FINOPS_SCOPE.md)
- [Docker deployment and recovery](docs/DOCKER.md)
- [Release-readiness gates](RELEASE_READINESS.md)
- [CI/CD validation](docs/CI_CD.md)

---

**Security is a continuous process.** Report suspected vulnerabilities privately, use least-privilege credentials, keep the deployment inaccessible to untrusted networks, and do not interpret a successful read-only scan as a guarantee of infrastructure safety.
