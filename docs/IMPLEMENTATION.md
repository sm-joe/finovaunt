# FinOps Cost Evidence Report — Integration Instructions

This change adds a new artifact, `cost_evidence.json`, without replacing `src/agent.py` wholesale.

## Files to place in the repository

- `src/utils/cost_evidence.py` → `src/utils/cost_evidence.py`
- `tests/test_cost_evidence.py` → `tests/test_cost_evidence.py`
- `integrate_cost_evidence.py` → repository root
- `docs/COST_EVIDENCE_REPORT.md` → `docs/COST_EVIDENCE_REPORT.md`

## Apply the integration

Run these commands from the repository root in PowerShell:

```powershell
uv run python -m py_compile src\utils\cost_evidence.py tests\test_cost_evidence.py integrate_cost_evidence.py
uv run python integrate_cost_evidence.py
```

The integration script checks that expected source/test anchors occur exactly once before it writes anything. It backs up every changed file with a `.backup-cost-evidence-<UTC timestamp>` suffix. It updates `src/agent.py` to create the report and adds the report to the audit event list. It updates the manifest assertions in the approval-integrity and workflow-integration tests. If the local source differs from the expected structure, it exits with an error and does not modify files.

## Targeted validation

```powershell
uv run pytest tests\test_cost_evidence.py -v
uv run pytest tests\test_approval_artifact_integrity.py -v
uv run pytest tests\test_workflow_integration.py -v
```

The new report is written only as part of the existing approved artifact-writing path. It does not call AWS, apply Terraform, or change cloud resources. Existing manifest generation hashes `cost_evidence.json` along with the other artifacts.

## Expected new artifact

`artifacts\cost_evidence.json` (or the configured `FINOPS_OUTPUT_DIR`) contains:

- per-resource identity and utilization metrics;
- cost source, status, amount, currency, and period;
- savings estimate basis, assumptions, and classification;
- risk and approval requirements;
- data-quality warnings;
- separate account-level billing context;
- an explicit `realized_savings.status` of `not_verified`.

Account-level totals are context only. An observed 14-day EC2 amount is not converted to a monthly cost. Mock savings are marked simulated. The report does not claim realized savings.
