# Finovaunt scheduled automation

This workflow runs a read-only scan daily at 03:30 UTC and can also be triggered manually from **GitHub → Actions → Finovaunt read-only cost scan → Run workflow**. Manual runs can choose `aws` or `mock`; scheduled runs use AWS.

## Prerequisites

1. Install the `cost_evidence.json` and `cost_history.json` integrations and commit them before enabling the workflow.
2. Ensure the repository has `pyproject.toml` and the `uv sync --dev` command works locally.
3. In GitHub repository **Settings → Secrets and variables → Actions → Variables**, create `FINOPS_AWS_ROLE_ARN` containing the IAM role ARN. This is a role ARN, not a secret access key.
4. Configure the IAM role trust policy for GitHub OIDC with the exact repository and allowed branch/ref. Grant only the read-only permissions required by the EC2 metrics and Cost Explorer collectors. Do not grant `ec2:Modify*`, `ec2:TerminateInstances`, or Terraform deployment permissions.
5. The default branch must contain `.github/workflows/finovaunt-scan.yml`. The workflow uses the default branch's schedule when enabled.

## Safety behavior

- The automated entry point invokes collection, proposal generation, and risk/HCL assessment without invoking the interactive approval node.
- It writes reports only; it does not create a Git branch, commit, push, or apply Terraform.
- It fails if the evidence/history integrations are absent, so it cannot silently upload an incomplete report set.
- It restores only `cost_history.json` from the most recent successful workflow artifact, then uploads the new scan artifact with 30-day retention.
- Artifact access is governed by repository access. Treat billing and resource metadata as operationally sensitive; adjust repository access and retention to your requirements.
- Observed-period reductions are not converted to recurring monthly savings. Actual post-change verification still requires explicit change evidence and suitable billing windows.

## Files

- `.github/workflows/finovaunt-scan.yml` → `.github/workflows/finovaunt-scan.yml`
- `scripts/run_readonly_scan.py` → `scripts/run_readonly_scan.py`

## Local validation (PowerShell)

```powershell
uv run python -m py_compile scripts\run_readonly_scan.py
uv run pytest tests\test_cost_evidence.py tests\test_proposal_history.py tests\test_outcome_verification.py -v
```

The automated workflow does not push code or generated reports to a Git branch. It publishes reports as a retained GitHub Actions artifact. Approval and infrastructure deployment remain a separate human-controlled process.
