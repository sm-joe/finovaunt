# Autonomous FinOps Cost Optimization Agent

Local-first, open-source reference project that converts cloud utilization metadata into validated FinOps recommendations and Terraform proposal artifacts. **It never applies Terraform or calls cloud write APIs.**

## Architecture

| Stage | Implementation | Boundary |
|---|---|---|
| Data collection | Mock AWS/GCP metrics | No credentials or SDKs |
| Optimization | Conservative deterministic policy | Pydantic v2 output schemas |
| Risk assessment | Production/high-risk checks and HCL validation | Failed validation blocks branch writing |
| Human gate | Interactive terminal approval | EOF/Ctrl+C reject |
| Execution | Local Git branch and commit | No push, cloud writes, or hosted PR creation |

## Guardrails

- Subprocesses use fixed argument arrays, `shell=False`, and timeouts; generated strings never become shell commands.
- `terraform fmt` validates HCL in a temporary directory. TFLint runs when installed; set `FINOPS_REQUIRE_TFLINT=true` to require it.
- Regex scrubbing redacts common AWS keys, Google API keys, bearer tokens, secret/token assignments, and 12-digit account IDs. This is defense-in-depth, not complete DLP.
- Git branch mode refuses a dirty checkout. It creates a branch and commit only after explicit approval.
- Sample HCL is a harmless `locals` block. Recommendations and savings are illustrative, not billing forecasts.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `FINOPS_OUTPUT_DIR` | `artifacts` | Relative artifact folder |
| `FINOPS_GIT_REPO` | `.` | Git repository; otherwise local artifacts |
| `FINOPS_GIT_BRANCH_PREFIX` | `finops/optimization` | Proposal branch prefix |
| `FINOPS_REQUIRE_TFLINT` | `false` | Require TFLint installation |

## Three-command quickstart

Requires Python 3.11+, [uv](https://docs.astral.sh/uv/), Terraform CLI; TFLint is recommended.

```bash
uv sync --extra dev
uv run pytest
uv run python -m src.app
```

Type `approve` to write artifacts. In a clean Git repository, this creates a branch and commit. Push it and open a PR through your normal review workflow; this tool deliberately does not push or create hosted PRs.

## Mock boundary cases

- AWS dev EC2: 3.8% average CPU and $286.40/month.
- AWS production database: 94% peak CPU; no automatic rightsizing.
- GCP test compute: 8.2% average CPU.
- GCP production database: 89% peak CPU; no automatic rightsizing.

## Validation

```bash
terraform version
tflint --version
uv run ruff check src tests
uv run pytest
```

MIT License.
