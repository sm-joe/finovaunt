# Finovaunt automatic scan artifact sync fix

This fixes a recovery bug in `scripts/scan_artifact_sync.py`: when `.finovaunt-sync.json` already recorded the latest GitHub run, the sync worker returned `unchanged` even if `artifacts-live/cost_evidence.json` had been deleted or was invalid. The worker now verifies that the local evidence file exists and matches the marker's scan run ID before skipping the download. If it is missing/corrupt, the same successful GitHub artifact is downloaded and validated again.

## Apply from repository root (PowerShell)

Stop the running API with Ctrl+C first. Extract this ZIP into a temporary directory, then copy the two scripts and test file into the repository, preserving paths. For example, if the ZIP is in the repository root:

```powershell
Expand-Archive .\finovaunt-readonly-scan-automation-fix.zip .\_scan-sync-fix -Force
Copy-Item .\_scan-sync-fix\finovaunt-readonly-scan-automation-fix\scripts\scan_artifact_sync.py .\scripts\scan_artifact_sync.py -Force
Copy-Item .\_scan-sync-fix\finovaunt-readonly-scan-automation-fix\scripts\dashboard_api.py .\scripts\dashboard_api.py -Force
Copy-Item .\_scan-sync-fix\finovaunt-readonly-scan-automation-fix\tests\test_scan_artifact_sync.py .\tests\test_scan_artifact_sync.py -Force

uv run python -m py_compile scripts\scan_artifact_sync.py scripts\dashboard_api.py
uv run pytest tests\test_scan_artifact_sync.py -v
```

Restart the API with the existing environment variables for the GitHub token, repository, workflow, and `FINOPS_OUTPUT_DIR=artifacts-live`. The worker will retry sync automatically at its configured interval (60 seconds by default; minimum 30 seconds). Check `/api/sync-status` once after startup for the real sync status; do not manually copy scan files.
