# Finovaunt — post-change outcome verification

This feature compares a baseline `cost_evidence.json` report with a post-change `cost_evidence.json` report and explicit change evidence. It produces a separate `outcome_verification.json`; it does not mutate infrastructure or rewrite the source evidence reports.

## Required change evidence

See `change-evidence.example.json`. A record must identify the change, show explicit human approval, show that deployment was applied/deployed, include a timezone-aware deployment timestamp, and include a deployment evidence reference (for example, a Terraform run URL or run ID). Missing evidence fails closed.

## Cost comparison rules

- Resource matching uses provider + region + resource ID.
- Both billing windows must have explicit timezone-aware start/end timestamps, be non-overlapping, have equal duration, and be on the correct side of the deployment timestamp.
- `verified_monthly_cost` in USD can support a verified monthly cost reduction only when the above checks pass.
- `observed_period_cost_only` in USD can support a verified reduction for that exact observed period. It is not annualized, converted to monthly savings, or reported as recurring realized savings.
- Simulated, unavailable, non-USD, account-level, undated, or mismatched cost evidence cannot verify resource savings.
- A verified reduction is temporally associated with the deployment; the cost comparison alone does not prove causal attribution.

The current cost-evidence builder emits null period dates for `verified_monthly_cost` records. Those records therefore remain unverified until the evidence source supplies dated billing windows. Live observed-period evidence with explicit dates can show a period cost reduction, but realized monthly savings remains unverified.

## Run from repository root (PowerShell)

Copy files to the listed paths, then run:

```powershell
uv run python -m py_compile src\utils\outcome_verification.py scripts\verify_outcome.py tests\test_outcome_verification.py
uv run pytest tests\test_outcome_verification.py -v
```

To generate an outcome report after a change, keep the baseline report from before deployment, collect a new post-change report, and create a change record based on the example. Then run:

```powershell
uv run python scripts\verify_outcome.py --baseline artifacts-baseline\cost_evidence.json --after artifacts-after\cost_evidence.json --change change-evidence.json --output artifacts-after\outcome_verification.json
```

The baseline and post-change files must come from distinct runs. Do not fabricate dates, deployment evidence, approval, or cost values. Preserve the original source reports for audit.
