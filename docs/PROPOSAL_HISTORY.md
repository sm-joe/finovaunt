# Proposal history and outcome tracking

The agent writes `cost_history.json` alongside `cost_evidence.json`. It stores a sequence of run snapshots and per-resource comparisons against the immediately previous distinct run.

## What is tracked

- Resource identity scoped by provider and region.
- Average/peak CPU and average memory deltas in percentage points when both snapshots contain valid numbers.
- Resource monthly-cost delta only when both snapshots carry `verified_monthly_cost` in USD.
- Explicit non-comparable states for missing costs, simulated costs, and observed-period costs.
- Recommendation/action changes and changes in the proposed monthly savings estimate.
- Account billing context kept separate from resource-level cost.

## Safety rules

- A change in a proposed savings estimate is not a realized saving.
- Observed-period cost is not normalized into a monthly cost.
- Simulated costs are never presented as verified production cost.
- `realized_savings` stays `not_verified` and `amount_usd` stays null. This feature does not infer deployment from approval, a Git commit, or a changed recommendation.
- The history file is included in the existing SHA-256 artifact manifest.
- Re-running the same `run_id` replaces that run's snapshot rather than adding a duplicate. A corrupt existing history file causes artifact writing to fail rather than silently destroying the history.

## Installation

Copy `src/utils/proposal_history.py` and `tests/test_proposal_history.py` into the repository at those paths. Copy `integrate_proposal_history.py` to the repository root. Run the exact commands in `IMPLEMENTATION.md`.

The integration script expects the earlier `cost_evidence.json` feature to be installed. It preflights source anchors and makes timestamped backups before changing files.
