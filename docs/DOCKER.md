# Finovaunt local Docker deployment

This first Docker package runs the existing read-only dashboard API and builds the existing Vite/React frontend as static assets. It deliberately does not change `frontend/src/App.tsx` or `frontend/src/styles.css`.

## Prerequisites

- Docker Desktop with Docker Compose v2
- Existing project checkout with `frontend/package-lock.json`
- Scan artifacts in the repository's `artifacts-live/` directory for populated dashboard data

## Start (Windows PowerShell)

Run at the repository root after copying these files into their listed paths:

```powershell
docker compose config
docker compose build
docker compose up -d
docker compose ps
```

Open the dashboard at `http://localhost:4173`. The read-only API health endpoint is `http://localhost:8787/api/health`.

## Stop / logs

```powershell
docker compose logs --tail 100
docker compose down
```

`docker compose down` preserves host scan artifacts. Do not use `docker compose down -v` as part of routine shutdown.

## Artifact behavior

`./artifacts-live-validation` is mounted read-only into the API container at `/app/artifacts-live-validation`, matching the validation scan output directory used during the recent project work. Live evidence is not copied into the image. If the directory is absent or does not contain `cost_evidence.json`, copy the actual scan output directory into this path or update both `FINOPS_OUTPUT_DIR` and the volume mapping to the directory that contains the real artifact. Do not create a fabricated `cost_evidence.json`. Health can pass while overview/assets endpoints report that scan evidence is unavailable; this is intentional and avoids inventing placeholder data.

## Security boundaries

- API and frontend ports are published on `127.0.0.1` only.
- API container runs as a non-root user and mounts evidence read-only.
- Containers drop Linux capabilities and enable `no-new-privileges`.
- The API remains read-only and has no AWS credentials mounted into it.
- Do not expose this dashboard publicly without authentication, TLS, access controls, and deployment-specific hardening.

## v1 scope boundary

The existing FinOps scan agent and scheduled GitHub Actions OIDC workflow remain on their existing `uv`/GitHub Actions execution path in this first Docker package. This keeps the dashboard container free of AWS credentials and avoids changing the established approval, report-only, and cloud-write boundaries. The scan agent is not claimed to be containerized by these files.

## Validation status

The Docker files have not been built or run against the user's actual checkout in this environment. Validate the Compose configuration and build locally before relying on the container deployment. A successful image build does not certify AWS scan behavior or production readiness; see `RELEASE_READINESS.md`.
