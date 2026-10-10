"""Run a non-interactive, read-only Finovaunt scan and write proposal artifacts.

This entry point deliberately does not call the interactive approval node,
create a Git branch, commit, push, or apply Terraform.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import _write_artifacts, assess_risk, collect_data, optimize  # noqa: E402

_GENERATED_FILES = {
    "proposal.json",
    "main.tf",
    "audit.json",
    "billing.json",
    "cost_evidence.json",
    "cost_history.json",
    "manifest.json",
}


def main() -> int:
    output_name = os.getenv("FINOPS_OUTPUT_DIR", "artifacts-live").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", output_name):
        print("ERROR: FINOPS_OUTPUT_DIR must contain only letters, digits, '_' or '-'.", file=sys.stderr)
        return 2

    output_dir = (ROOT / output_name).resolve()
    if output_dir.parent != ROOT:
        print("ERROR: output directory must be directly under the repository root.", file=sys.stderr)
        return 2

    # Keep history for comparison, but remove known outputs from an earlier run
    # so the new manifest cannot accidentally include stale reports.
    if output_dir.exists():
        unexpected = [p.name for p in output_dir.iterdir() if p.is_dir() or p.name not in _GENERATED_FILES]
        if unexpected:
            print(
                "ERROR: output directory contains unexpected entries; refusing to delete them: "
                + ", ".join(sorted(unexpected)),
                file=sys.stderr,
            )
            return 2
        for path in output_dir.iterdir():
            if path.name != "cost_history.json":
                path.unlink()

    state: dict = {"run_id": uuid.uuid4().hex[:12], "events": []}
    collected = collect_data(state)
    state.update(collected)
    if state.get("validation_error") or state.get("status") == "collection_failed":
        print("ERROR: collection failed; no proposal artifacts written.", file=sys.stderr)
        for event in state.get("events", []):
            print(f"- {event}", file=sys.stderr)
        return 1

    state.update(optimize(state))
    state.update(assess_risk(state))
    if state.get("validation_error") or state.get("status") == "validation_failed":
        print("ERROR: risk/HCL assessment failed; no proposal artifacts written.", file=sys.stderr)
        # assess_risk already sanitizes validation_error; expose it so CI logs
        # identify missing executables or the exact formatter/linter failure.
        validation_error = state.get("validation_error")
        if validation_error:
            print(f"- Validation detail: {validation_error}", file=sys.stderr)
        for event in state.get("events", []):
            print(f"- {event}", file=sys.stderr)
        return 1

    # Require the evidence/history integrations before automated use. Do not
    # silently publish an incomplete report set.
    try:
        _write_artifacts(output_dir, state)
    except Exception as exc:  # surfaced without printing state/secrets
        print(f"ERROR: artifact generation failed ({type(exc).__name__}).", file=sys.stderr)
        return 1

    required = {"proposal.json", "main.tf", "audit.json", "billing.json", "cost_evidence.json", "cost_history.json", "manifest.json"}
    missing = sorted(name for name in required if not (output_dir / name).is_file())
    if missing:
        print(
            "ERROR: required artifact integrations are missing: " + ", ".join(missing)
            + ". Install the cost-evidence and proposal-history integrations first.",
            file=sys.stderr,
        )
        return 1

    print(f"Read-only scan completed: run_id={state['run_id']}")
    print(f"Artifacts: {output_dir.relative_to(ROOT)}")
    print("No approval was granted; no Git branch, commit, push, or infrastructure change was performed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
