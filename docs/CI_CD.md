# Finovaunt CI/CD

## Workflows

- `.github/workflows/ci.yml` compiles and tests the Python project, builds the Vite/TypeScript frontend, and validates the Docker Compose configuration.
- `.github/workflows/security.yml` checks repository history for secrets, audits Python and npm dependencies, and scans source/configuration with Trivy.
- `.github/workflows/build.yml` calls the CI and Security workflows as reusable workflows. The API and dashboard image jobs each declare `needs: [ci, security]`; either failure or cancellation prevents both image jobs from running.

CI and Security also run independently on pushes and pull requests. The Docker workflow runs on pushes and manual dispatches, but its image jobs are restricted to the repository's default branch.

## Images

The workflow builds two separate local images on GitHub-hosted runners:

- API: root `Dockerfile`, tagged `finovaunt-api:<commit-sha>`
- Dashboard: `frontend/Dockerfile`, tagged `finovaunt-dashboard:<commit-sha>`

Images are not pushed to a registry and are not retained after the GitHub-hosted runner is disposed. Registry publishing is intentionally not enabled.

## Security gate behavior

- Gitleaks fails the workflow when its secret-detection policy reports a finding.
- `pip-audit` fails on detected Python dependency vulnerabilities.
- `npm audit --audit-level=high` fails on high or critical npm advisories.
- Trivy scans vulnerabilities, secrets, and misconfiguration, failing on HIGH or CRITICAL findings that are not ignored as unfixed.

A scan can expose existing findings in the repository or dependency lockfiles. Fix or explicitly review such findings rather than weakening the gate just to obtain a green run.

## GitHub branch protection

For pull-request enforcement, configure a branch ruleset for the default branch requiring the `Finovaunt CI` and `Finovaunt Security` checks to pass before merge. The Docker workflow itself builds only on the default branch after re-running both reusable gates for the exact pushed commit.
