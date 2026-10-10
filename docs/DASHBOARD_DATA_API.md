# Finovaunt dashboard data API — first implementation

This implementation adds a **read-only** local API over the existing scan artifacts. It does not add cloud permissions, run scans, approve changes, or apply Terraform.

## Files

- `src/utils/dashboard_data.py` — pure projection layer over the current artifact schemas.
- `scripts/dashboard_api.py` — HTTP server using only the Python standard library.
- `tests/test_dashboard_data.py` — tests for summary semantics, opportunities, assets, and scan history.
- `tests/test_dashboard_api.py` — HTTP health and read-only method tests.

## Endpoints

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | API health; works before scan artifacts exist |
| `GET /api/overview` | Executive KPIs, account billing context, opportunity counts, evidence-backed and simulated savings separated |
| `GET /api/opportunities` | Prioritized recommendations with risk, confidence, missing evidence, and savings classification |
| `GET /api/assets` | Discovered resource inventory and utilization/cost evidence |
| `GET /api/scans` | Scan history |
| `GET /api/scans/latest` | Most recent scan record |
| `GET /api/scans/{run_id}` | Scan detail from history |

All non-health endpoints return HTTP 503 with a clear message if the evidence artifact is not present or is malformed. They do not fabricate placeholder data.

## Financial semantics

- `potential_monthly_savings_usd` only sums records classified as `estimated_from_monthly_resource_cost`.
- `simulated_monthly_savings_usd` is reported separately.
- Account-level billing is displayed as context only; it is never attributed to resources.
- Realized savings is always `not_verified` with a null amount unless a future implementation explicitly connects verified outcome reports.
- Unknown/negative/non-finite estimates are excluded from totals.
- API methods are read-only; write methods return HTTP 405.
- CORS is restricted to the local Vite development/preview origins.

## Run from the repository root (PowerShell)

The API reads `artifacts-live` by default, matching the scheduled scan workflow. Set `FINOPS_OUTPUT_DIR` to the directory containing the latest scan's artifacts if yours differs.

```powershell
uv run python -m py_compile src\utils\dashboard_data.py scripts\dashboard_api.py tests\test_dashboard_data.py
uv run pytest tests\test_dashboard_data.py -v
$env:FINOPS_OUTPUT_DIR = "artifacts-live"
uv run python scripts\dashboard_api.py
```

Keep the API terminal open. In a second PowerShell terminal, check:

```powershell
Invoke-RestMethod http://127.0.0.1:8787/api/health
Invoke-RestMethod http://127.0.0.1:8787/api/overview | ConvertTo-Json -Depth 8
Invoke-RestMethod http://127.0.0.1:8787/api/opportunities | ConvertTo-Json -Depth 8
Invoke-RestMethod http://127.0.0.1:8787/api/assets | ConvertTo-Json -Depth 8
Invoke-RestMethod http://127.0.0.1:8787/api/scans | ConvertTo-Json -Depth 8
```

If the current scan artifacts are in a different directory, change `FINOPS_OUTPUT_DIR` before starting the server. The API is bound to `127.0.0.1` by default and should not be exposed publicly without authentication and deployment hardening.
