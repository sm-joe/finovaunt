# FinOps proposal history implementation

## Files

- `src/utils/proposal_history.py` — pure history snapshot/comparison builder.
- `tests/test_proposal_history.py` — six focused regression tests.
- `integrate_proposal_history.py` — guarded integration into `src/agent.py` and existing artifact-integrity/workflow tests.
- `docs/PROPOSAL_HISTORY.md` — schema intent and safety rules.

## Apply on Windows PowerShell

Copy the files to the matching paths in the existing `autonomous-finops-agent` checkout. Keep the already-installed `cost_evidence.py` and its integration in place.

From the repository root, run in this order:

```powershell
uv run python -m py_compile src\utils\proposal_history.py tests\test_proposal_history.py integrate_proposal_history.py
uv run python integrate_proposal_history.py
uv run pytest tests\test_proposal_history.py -v
uv run pytest tests\test_approval_artifact_integrity.py -v
uv run pytest tests\test_workflow_integration.py -v
```

The integration script checks every required source/test anchor before making edits. It creates timestamped backups of modified files. If it reports an anchor mismatch, stop and inspect the current file rather than forcing the patch.

## Result

Approved artifact writes produce `cost_history.json` before `manifest.json`, so the current SHA-256 manifest includes it. Each new run compares against the last prior distinct run found in the existing output directory. The history is carried forward in that directory as the next run's starting point; it is not a centralized database and is not guaranteed to survive manual deletion of output artifacts.
