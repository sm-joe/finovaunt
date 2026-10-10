"""Safely integrate cost_evidence.json into the agent and regression tests.

Run from the repository root. Every anchor is validated before any file is
modified, and a timestamped backup is written for each changed file.
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
    import_line = "from src.utils.cost_evidence import build_cost_evidence_report"
    audit_anchor = "    audit_document = {\n        \"events\": state.get(\"events\", []),\n    }\n"
    audit_replacement = (
        "    evidence_report = build_cost_evidence_report(state)\n"
        "    audit_events = [\n"
        "        *state.get(\"events\", []),\n"
        "        f\"Cost evidence report generated for {evidence_report['summary']['resource_count']} resources\",\n"
        "    ]\n"
        "    audit_document = {\n"
        "        \"events\": audit_events,\n"
        "    }\n"
    )
    manifest_anchor = "    # Record hashes of all generated files except the manifest itself.\n"
    report_write = (
        "    (directory / \"cost_evidence.json\").write_text(\n"
        "        json.dumps(evidence_report, indent=2, allow_nan=False) + \"\\n\",\n"
        "        encoding=\"utf-8\",\n"
        "    )\n\n"
    )

    replacements: dict[Path, str] = {}
    agent_source = agent_path.read_text(encoding="utf-8")
    agent_already_integrated = (
        import_line in agent_source and "cost_evidence.json" in agent_source
    )
    if not agent_already_integrated:
        if import_line in agent_source:
            raise SystemExit(
                "ERROR: import exists but artifact integration is absent; inspect src/agent.py manually."
            )
        if "cost_evidence.json" in agent_source:
            raise SystemExit(
                "ERROR: cost_evidence.json already appears in src/agent.py; inspect before retrying."
            )
        if agent_source.count(import_anchor) != 1:
            raise SystemExit(
                "ERROR: expected AgentState import anchor was not found exactly once; no files changed."
            )
        if agent_source.count(audit_anchor) != 1:
            raise SystemExit(
                "ERROR: expected audit document anchor was not found exactly once; no files changed."
            )
        if agent_source.count(manifest_anchor) != 1:
            raise SystemExit(
                "ERROR: expected manifest anchor was not found exactly once; no files changed."
            )
        updated_agent = agent_source.replace(
            import_anchor, f"\n\n{import_line}{import_anchor}", 1
        )
        updated_agent = updated_agent.replace(audit_anchor, audit_replacement, 1)
        updated_agent = updated_agent.replace(manifest_anchor, report_write + manifest_anchor, 1)
        replacements[agent_path] = updated_agent

    expected_old = '''assert set(manifest["files"]) == {
        "audit.json",
        "billing.json",
        "main.tf",
        "proposal.json",
    }'''
    expected_new = '''assert set(manifest["files"]) == {
        "audit.json",
        "billing.json",
        "cost_evidence.json",
        "main.tf",
        "proposal.json",
    }'''

    for test_path in (
        Path("tests/test_approval_artifact_integrity.py"),
        Path("tests/test_workflow_integration.py"),
    ):
        if not test_path.exists():
            continue
        test_source = test_path.read_text(encoding="utf-8")
        if expected_new in test_source:
            updated_test = test_source
        else:
            count = test_source.count(expected_old)
            if count != 1:
                raise SystemExit(
                    f"ERROR: expected one manifest file-set assertion in {test_path}, found {count}; no files changed."
                )
            updated_test = test_source.replace(expected_old, expected_new, 1)

        if test_path.name == "test_workflow_integration.py":
            evidence_anchor = '''    assert proposals[0]["estimated_monthly_savings_usd"] == 30
'''
            evidence_assertions = evidence_anchor + '''    evidence = json.loads(
        (artifacts / "cost_evidence.json").read_text(encoding="utf-8")
    )
    assert evidence["summary"]["resource_count"] == 1
    assert evidence["resources"][0]["savings_evidence"]["classification"] == "simulated_estimate"
    assert evidence["resources"][0]["savings_evidence"]["realized_savings"]["status"] == "not_verified"
'''
            if evidence_assertions not in updated_test:
                if updated_test.count(evidence_anchor) != 1:
                    raise SystemExit(
                        f"ERROR: expected workflow evidence assertion anchor in {test_path} was not found exactly once; no files changed."
                    )
                updated_test = updated_test.replace(evidence_anchor, evidence_assertions, 1)
        if updated_test != test_source:
            replacements[test_path] = updated_test

    if not replacements:
        print("No change: source integration and manifest test expectations already appear to be present.")
        return 0

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backups: list[tuple[Path, Path]] = []
    for target, updated in replacements.items():
        backup = target.with_name(f"{target.name}.backup-cost-evidence-{stamp}")
        shutil.copy2(target, backup)
        backups.append((target, backup))
        target.write_text(updated, encoding="utf-8", newline="\n")

    if agent_already_integrated:
        print("Agent integration already present; updated missing test expectations.")
    else:
        print(f"Integrated cost_evidence.json into {agent_path}.")
    for target, backup in backups:
        print(f"Updated: {target} (backup: {backup})")
    print("The existing manifest generation automatically hashes cost_evidence.json.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
