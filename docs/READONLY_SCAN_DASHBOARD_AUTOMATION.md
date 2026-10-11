# Finovaunt read-only scan → dashboard automation

This patch connects the existing scheduled/manual GitHub Actions scan to the existing local dashboard without committing scan data to Git or changing AWS infrastructure.

## Behavior

- `.github/workflows/finovaunt-scan.yml` remains the scan producer and uploads the `finovaunt-scan` artifact.
- The dashboard API polls the GitHub Actions workflow for its latest successful, non-expired `finovaunt-scan` artifact every 60 seconds by default.
- Downloaded files are restricted to the known JSON artifact names and validated against `manifest.json` SHA-256 hashes before being installed into `artifacts-live`.
- The dashboard frontend refreshes API data every 30 seconds and displays whether automatic sync is enabled or has an error.
- The sync is read-only against GitHub and AWS: it downloads artifacts only. It does not trigger scans, create branches/commits, approve proposals, or apply Terraform.
- The existing scan workflow still runs on its existing daily schedule and can still be manually triggered.

## One-time local configuration (PowerShell)

Create a GitHub fine-grained personal access token restricted to the `sm-joe/finovaunt` repository with **Actions: read-only** and repository metadata read access. Keep it out of source control and do not put it in frontend/Vite variables.

```powershell
$env:FINOVAUNT_GITHUB_TOKEN = Read-Host "Paste the GitHub token"
$env:FINOVAUNT_GITHUB_REPOSITORY = "sm-joe/finovaunt"
$env:FINOVAUNT_SCAN_WORKFLOW = "finovaunt-scan.yml"
$env:FINOPS_OUTPUT_DIR = "artifacts-live"
uv run python scripts/dashboard_api.py
```

Keep this API terminal open. In another terminal, start the existing frontend using its normal development command. The API syncs the latest successful artifact; the frontend picks up refreshed data automatically. The token is held in the current PowerShell process environment only, not written to a file.

Optional settings:

```powershell
$env:FINOVAUNT_SYNC_INTERVAL_SECONDS = "60"
```

Values below 30 seconds are clamped to 30 seconds. If the GitHub token is absent, the API remains usable with local `artifacts-live` files, but automatic GitHub sync is disabled. Check `GET http://127.0.0.1:8787/api/sync-status` for the sync state.

## Validation (PowerShell)

```powershell
uv run python -m py_compile scripts\scan_artifact_sync.py scripts\dashboard_api.py
uv run pytest tests\test_scan_artifact_sync.py -v
Invoke-RestMethod http://127.0.0.1:8787/api/health
Invoke-RestMethod http://127.0.0.1:8787/api/sync-status | ConvertTo-Json -Depth 5
Invoke-RestMethod http://127.0.0.1:8787/api/overview | ConvertTo-Json -Depth 8
Invoke-RestMethod http://127.0.0.1:8787/api/scans | ConvertTo-Json -Depth 8
```

A `403` from GitHub means the token does not have Actions read permission for the repository. A `404` or no-artifact message may mean the workflow has no successful run with an unexpired `finovaunt-scan` artifact. Do not grant write permissions to resolve these errors.
