# Per-resource Cost Evidence Report

## Purpose

`cost_evidence.json` records the evidence behind each resource recommendation. It is generated with the existing artifacts after explicit human approval and before the manifest is written. The existing manifest logic hashes all files in the output directory except `manifest.json`, so the report is included automatically.

## Evidence classifications

- `verified_monthly_cost`: a source explicitly identified as verified monthly resource cost. Only this category can populate `monthly_cost_usd` in the evidence report.
- `simulated_monthly_cost`: mock input. It is explicitly marked as simulation and is not a production forecast.
- `observed_period_cost_only`: observed resource-level cost for a specific period. It is not normalized to monthly cost and is not used as a monthly savings baseline.
- `observed_period_cost_non_usd`: observed non-USD amount, not converted or used for USD savings.
- `cost_unavailable`, `ambiguous_resource_cost`, and `invalid_resource_cost`: insufficient evidence to attribute a defensible cost.

## Savings classifications

- `simulated_estimate`: derived from mock inputs.
- `estimated_from_monthly_resource_cost`: estimate based on a verified monthly resource cost; still subject to compatibility, pricing, and workload assumptions.
- `not_estimable_from_available_evidence`: no defensible monthly resource-cost baseline is available.
- `not_applicable`: no-change or otherwise non-applicable recommendation.

Every record marks realized savings as `not_verified`. This workflow does not apply cloud changes or verify post-change billing, so it must not claim realized savings.

## Account-level billing

`account_billing_context` contains account-level billing period and totals for context only. Those totals are never copied into individual resource records or used to calculate resource-level savings. The account billing period and the EC2 resource-cost collection period may differ and must be reviewed separately.

## Integration

The integration script adds a call to `build_cost_evidence_report(state)` inside `src/agent.py`'s artifact writer. It validates unique anchors and writes a timestamped backup before modifying the file. The report is generated before the manifest so the manifest includes its SHA-256 digest.
