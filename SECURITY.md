# Security Policy

Finovaunt is a self-hosted, read-only AWS FinOps analysis product under active development. Do not grant the application AWS write permissions or expose its local development API directly to the internet.

## Reporting vulnerabilities

For confidential vulnerabilities, open a private security advisory in the GitHub repository's **Security** tab rather than publishing an issue containing exploit details, tokens, cloud account identifiers, billing data, or credentials. Include a concise description, affected versions, reproduction steps, impact, and a safe proof of concept if possible.

## Support policy

No stable public v1.0.0 release has been declared. Development branches and functional milestones are not security-supported production releases. A stable version will have a defined maintenance and vulnerability-response policy after the release audit.

## Security boundaries

- AWS collection uses short-lived STS credentials and least-privilege role assumption. No AWS resource writes are required for discovery, billing or inventory.
- Local login requires an explicit bootstrap secret on first install. Password hashes, cloud metadata, scan history, and review decisions are persisted in a local control-plane file with restricted filesystem permissions.
- Session cookies are HttpOnly and SameSite=Strict. Configure `FINOVAUNT_SECURE_COOKIES=true` behind HTTPS; terminate TLS with a trusted proxy for any network deployment.
- Scan artifact and recommendation endpoints require authentication. Same-origin checks protect state-changing browser requests; production deployments should also implement robust CSRF and rate-limiting controls.
- Human recommendation decisions do not apply Terraform, push branches, or change AWS resources.
- Cost Explorer account totals are contextual billing data. Do not report them as resource-level cost attribution or verified savings.
- Keep `.env`, `data/`, scan artifacts, and AWS credentials out of public repositories and container images.

## Temporary CI development mode

At the product owner's request, automated dependency/security scans and Docker image builds are temporarily disabled on PRs and pushes while product functionality is developed. Backend tests, frontend build, and Compose configuration validation remain active. This is **not a security approval or permanent waiver**.

Before any stable release, restore and pass secret scanning, dependency audits (including remediation of the identified vulnerable `certifi` pin), container and filesystem/IaC scans, runtime image builds, and deployment verification. Do not label a release production ready based on development CI alone.

## Deployment recommendations

Prefer a private network or authenticated reverse proxy, a secure TLS configuration, a dedicated read-only IAM role, durable encrypted backups of local state, filesystem isolation, monitoring, and documented restoration tests. Self-hosted installations should remain bound to loopback unless these protections are implemented and validated.
