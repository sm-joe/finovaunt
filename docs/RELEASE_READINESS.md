# Autonomous FinOps Cost Optimization Agent — Release Readiness

**Status: NOT FROZEN — local validation evidence is pending.**

This checklist defines the evidence required before calling the current implementation frozen. A behavior is not marked verified merely because a test was authored or passed in a separate environment.

## Safety guarantees and required evidence

| Area | Intended guarantee | Evidence required before marking verified |
|---|---|---|
| Human approval | Only the literal Boolean `True` authorizes write operations; rejected or unapproved proposals must not create artifacts, branches, or commits. | `tests/test_approval_artifact_integrity.py` and `tests/test_workflow_integration.py` pass in the project environment. |
| AWS collection boundary | Live AWS discovery failures stop the workflow before approval or writes. Cost collection failures do not discard successfully collected metrics. | `tests/test_workflow_integration.py` and `tests/test_agent_billing_regression.py` pass in the project environment. |
| Cost attribution | EC2 cost attribution requires an unambiguous resource-ID and region match. Period-specific observed spend is not silently treated as verified monthly spend. Mock savings are identified as simulated. | `tests/test_cost_attribution.py`, `tests/test_ec2_resource_costs.py`, and `tests/test_aws_costs_regression.py` pass in the project environment. |
| HCL validation | Invalid generated HCL blocks proposal writing; validation runs locally and does not apply Terraform. | Existing HCL/guardrail tests pass, and the workflow integration test passes. |
| Git rollback | A staging or commit failure restores the original branch and removes the temporary proposal state without deleting pre-existing user artifacts. | `tests/test_write_branch_rollback.py` passes in the project environment. |
| Artifact integrity | `manifest.json` records SHA-256 hashes for the generated `proposal.json`, `main.tf`, `audit.json`, and `billing.json`; changing an artifact causes a digest mismatch. | `tests/test_approval_artifact_integrity.py` and the approved-workflow integration test pass in the project environment. |
| Local-only execution | The workflow does not apply Terraform, call cloud write APIs, push Git branches, or create hosted pull requests. | Review implementation and subprocess/API call sites; tests alone are not sufficient to prove absence of every external write path. |

## Validation commands (PowerShell)

Run from the repository root. Stop and investigate at the first failing command; do not freeze or commit based on partial results.

```powershell
uv run python -m py_compile src\agent.py src\tools\cloud_metrics.py src\tools\aws_costs.py src\utils\guardrails.py
uv run pytest tests/test_cost_attribution.py -v
uv run pytest tests/test_aws_costs_regression.py -v
uv run pytest tests/test_ec2_resource_costs.py -v
uv run pytest tests/test_agent_billing_regression.py -v
uv run pytest tests/test_write_branch_rollback.py -v
uv run pytest tests/test_approval_artifact_integrity.py -v
uv run pytest tests/test_workflow_integration.py -v
uv run pytest -v
uv run ruff check src tests
git diff --check
```

If a listed test file does not exist in the checkout, add the reviewed test file first. Do not interpret a missing test file as a passing test.

## Freeze criteria

Freeze only after all of the following are true:

- All validation commands above pass in the target repository and environment.
- Any failing tests are fixed and rerun; no failures are waived silently.
- The working tree diff is reviewed, including generated files and test changes.
- A clean Git status is confirmed before creating the freeze commit.
- The documentation is updated to distinguish tested behavior from architectural intent and known limitations.

Useful final checks:

```powershell
git status --short
git diff --stat
git diff --check
```

## Known limitations

- Mock savings are illustrative and must remain explicitly labeled as simulated.
- Cost Explorer period totals are not, by themselves, verified per-resource monthly costs.
- Regex-based secret scrubbing is defense-in-depth, not complete data-loss prevention.
- A test suite provides evidence for tested cases, not a mathematical proof of all safety properties.
- This document does not claim the test suite has passed. Update the status only after recording results from the target project environment.
