"""Safely integrate cost_history.json into the FinOps artifact writer.

Run from the repository root after installing src/utils/proposal_history.py.
The script preflights all expected source/test anchors before writing anything,
and creates timestamped backups for every changed file.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import shutil


def main() -> int:
    agent_path = Path("src/agent.py")
    if not agent_path.is_file():
        raise SystemExit("ERROR: src/agent.py was not found. Run from repository root.")

    import_anchor = "\n\nclass AgentState(TypedDict, total=False):"
    import_line = "from src.utils.proposal_history import build_proposal_history"
    evidence_write_anchor = '''    (directory / "cost_evidence.json").write_text(
        json.dumps(evidence_report, indent=2, allow_nan=False) + "\\n",
        encoding="utf-8",
    )
'''
    history_write = '''    history_path = directory / "cost_history.json"
    previous_history = None
    if history_path.is_file():
        try:
            previous_history = json.loads(history_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            # Never silently append to a corrupt history file; fail the artifact
            # write so the caller's existing rollback protection can restore it.
            raise RuntimeError("Existing cost_history.json is unreadable; refusing to overwrite it")
    history_document = build_proposal_history(evidence_report, previous_history)
    history_path.write_text(
        json.dumps(history_document, indent=2, allow_nan=False) + "\\n",
        encoding="utf-8",
    )
'''
    manifest_anchor = "    # Record hashes of all generated files except the manifest itself.\n"

    source = agent_path.read_text(encoding="utf-8")
    already = import_line in source and '"cost_history.json"' in source
    if not already:
        if import_line in source or '"cost_history.json"' in source:
            raise SystemExit("ERROR: partial cost history integration detected; no files changed.")
        if source.count(import_anchor) != 1:
            raise SystemExit("ERROR: AgentState import anchor was not found exactly once; no files changed.")
        if source.count(evidence_write_anchor) != 1:
            raise SystemExit("ERROR: cost_evidence.json writer anchor was not found exactly once. Install the previous cost-evidence feature first; no files changed.")
        if source.count(manifest_anchor) != 1:
            raise SystemExit("ERROR: manifest anchor was not found exactly once; no files changed.")
        updated = source.replace(import_anchor, f"\n\n{import_line}{import_anchor}", 1)
        updated = updated.replace(evidence_write_anchor, evidence_write_anchor + "\n" + history_write, 1)
        replacements: dict[Path, str] = {agent_path: updated}
    else:
        replacements = {}

    expected_old = '''assert set(manifest["files"]) == {
        "audit.json",
        "billing.json",
        "cost_evidence.json",
        "main.tf",
        "proposal.json",
    }'''
    expected_new = '''assert set(manifest["files"]) == {
        "audit.json",
        "billing.json",
        "cost_evidence.json",
        "cost_history.json",
        "main.tf",
        "proposal.json",
    }'''

    for test_path in (Path("tests/test_approval_artifact_integrity.py"), Path("tests/test_workflow_integration.py")):
        if not test_path.is_file():
            continue
        test_source = test_path.read_text(encoding="utf-8")
        if expected_new in test_source:
            test_updated = test_source
        else:
            count = test_source.count(expected_old)
            if count != 1:
                raise SystemExit(f"ERROR: expected one cost-evidence manifest assertion in {test_path}, found {count}; no files changed.")
            test_updated = test_source.replace(expected_old, expected_new, 1)

        if test_path.name == "test_workflow_integration.py":
            assertions = '''    history = json.loads(
        (artifacts / "cost_history.json").read_text(encoding="utf-8")
    )
    assert history["latest_run_id"] == "workflow-integration"
    assert history["run_count"] == 1
    assert history["runs"][-1]["resources"][0]["savings"]["realized_savings_status"] == "not_verified"
'''
            if assertions not in test_updated:
                anchor = '''    assert proposals[0]["estimated_monthly_savings_usd"] == 30
'''
                if test_updated.count(anchor) != 1:
                    raise SystemExit(f"ERROR: workflow proposal assertion anchor not found exactly once in {test_path}; no files changed.")
                test_updated = test_updated.replace(anchor, anchor + assertions, 1)
        if test_updated != test_source:
            replacements[test_path] = test_updated

    if not replacements:
        print("No change: proposal history integration and test expectations are already present.")
        return 0

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backups: list[tuple[Path, Path]] = []
    for target, updated in replacements.items():
        backup = target.with_name(f"{target.name}.backup-proposal-history-{stamp}")
        shutil.copy2(target, backup)
        backups.append((target, backup))
        target.write_text(updated, encoding="utf-8", newline="\n")

    for target, backup in backups:
        print(f"Updated: {target} (backup: {backup})")
    print("cost_history.json is generated before manifest creation and is included in its SHA-256 hashes.")
    print("History compares only verified monthly resource costs; proposed savings remain estimates and realized savings remain unverified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
