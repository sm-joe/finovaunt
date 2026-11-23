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

## Required CI security gates

Security checking is restored on pull requests and main pushes. The required workflow includes secret scanning, Python/Node dependency audits, Trivy Dockerfile and filesystem/IaC checks, plus actual API/dashboard Docker image builds. The previously vulnerable `certifi` lock was upgraded to a PyPI-verified November 2026 release.

A passing CI pipeline does not by itself establish safe production deployment: strong CSRF controls, rate limiting, TLS reverse proxy configuration, rotation of runtime AWS credentials, EKS RBAC verification, clean upgrades and independent runtime acceptance remain important. No automated AWS or Kubernetes resource deletion is supported.

