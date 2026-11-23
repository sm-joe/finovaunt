# Finovaunt — Docker Deployment and Operations

Finovaunt provides a self-hosted React dashboard and a Python API using two Docker Compose services. The API stores user/account metadata and scan history in a bind-mounted `data/` directory, and dashboard scan artifacts in `artifacts-live/`.

## Requirements

- Linux with Docker Engine and Docker Compose v2
- OpenSSL for generating a first-install password
- TCP 4173 and 8787 available on local loopback
- Sufficient write access to `data/` and `artifacts-live/` by the API container's UID 10001

## Quickstart (Bash only)

From the repository root:

```bash
umask 077
printf 'FINOVAUNT_BOOTSTRAP_PASSWORD=%s\n' "$(openssl rand -hex 24)" > .env
mkdir -p data artifacts-live
sudo chown -R 10001:10001 data artifacts-live

docker compose config --quiet
docker compose up -d --build
docker compose ps
curl --fail http://127.0.0.1:8787/api/health
```

Open `http://127.0.0.1:4173`. The username is `admin`; the initial password is the value in the private `.env` file. First login requires password rotation. After rotation, your persisted password hash remains in `data/control-plane.json`. Changing the bootstrap environment variable does not reset an existing password.

**Do not expose the default deployment directly on the internet.** Both published ports are bound to `127.0.0.1`. For remote installations, use a trusted authenticated reverse proxy with TLS, restrict networking, set `FINOVAUNT_SECURE_COOKIES=true`, and configure a secure external hostname/origin strategy before enabling user access.

## Build and lifecycle

```bash
docker compose config --quiet
docker compose up -d --build
docker compose logs --tail=100 api frontend
docker compose restart api frontend
docker compose down
```

`docker compose down` preserves bind-mounted `data/` and `artifacts-live/`. Avoid deleting these paths; they contain user state and scan evidence. The Docker API runs with a read-only root filesystem, no additional Linux capabilities, and a non-root UID. Its bound data directories must still be writable.

## Using AWS

AWS billing and inventory scans need a source AWS credential chain in the API runtime that can call `sts:AssumeRole` on each onboarded role. The container does **not** automatically inherit your host `~/.aws` credentials.

Prefer deploying the API on a host/orchestrator that supplies a short-lived workload identity, rather than baking AWS keys into an image or embedding them in the UI. The onboarded target IAM role must permit the necessary read-only actions:

- `sts:GetCallerIdentity` in the assumed role
- `ce:GetCostAndUsage` for Cost Explorer billing
- `ec2:DescribeInstances` and `ec2:DescribeVolumes`
- `rds:DescribeDBInstances`
- The source identity must be trusted by the target role for `sts:AssumeRole`

The GitHub Actions OIDC scanner uses its own configured AWS role and region; it is not automatically connected to every dashboard-onboarded account. Do not conflate these two collection paths.

## Scan artifacts

The dashboard displays the latest synced or locally provided artifact snapshot under `artifacts-live/`. Without a real snapshot, its data endpoints deliberately report unavailable evidence rather than inventing savings.

For GitHub scan-artifact synchronization, provide a token with the minimum repository Actions read permission through `FINOVAUNT_GITHUB_TOKEN`, and configure `FINOVAUNT_GITHUB_REPOSITORY` and `FINOVAUNT_SCAN_WORKFLOW` as required. Keep this token out of source files and container images.

A verified no-resource AWS scan produces `scan_status.json` with `empty_inventory` status and zero savings. It does not generate misleading optimization proposals.

## Backup and restore

Back up both local state and scan evidence, preserving file permissions and confidentiality:

```bash
docker compose stop
umask 077
tar -czf finovaunt-backup.tar.gz data artifacts-live
docker compose start
```

Restore only after stopping the API and verifying the backup's integrity and source. Preserve ownership of the restored directories for UID 10001. A backup file may contain password hashes, account identifiers, billing history, review notes and cloud inventory; encrypt it at rest and restrict access.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Compose refuses startup | Set `FINOVAUNT_BOOTSTRAP_PASSWORD` in a private `.env` with at least 12 characters |
| Login rejected | Verify persisted `data/control-plane.json`; bootstrap only applies to first setup |
| Dashboard shows unavailable scan data | Inspect `artifacts-live/`, synchronization status, and `FINOPS_OUTPUT_DIR` |
| AWS billing/inventory 502 | Check source credentials, trust policy, target account ID and read-only IAM permissions |
| API unhealthy | Inspect `docker compose logs api` and mounted directory permissions |
| Frontend cannot reach API | Inspect `docker compose logs frontend`, loopback port mapping and Nginx proxy |

## Release boundary

Local Compose configuration and CI validation do not imply that images were built, inspected and deployed in a production-like environment. The security and Docker image build workflows are temporarily disabled at the owner's request. They must be restored and pass before stable v1.0.0.
