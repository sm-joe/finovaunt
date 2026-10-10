"""CLI entry point for the Autonomous FinOps Agent."""

import json

from dotenv import load_dotenv

from src.agent import finops_graph
from src.utils.guardrails import scrub_sensitive_text


def main() -> int:
    load_dotenv()

    try:
        result = finops_graph.invoke({"events": []})
    except Exception as exc:
        print("Run failed:", scrub_sensitive_text(exc))
        return 1

    proposals = result.get("proposals", [])

    summary = {
        "run_id": result.get("run_id"),
        "status": result.get("status"),
        "git_branch": result.get("git_branch"),
        "output_path": result.get("output_path"),
        "estimated_monthly_savings_usd": round(
            sum(
                proposal.get("estimated_monthly_savings_usd", 0)
                for proposal in proposals
            ),
            2,
        ),
        "billing_summary": result.get(
            "billing_summary",
            {"status": "not_collected"},
        ),
        "risk_summary": result.get("risk_summary", []),
        "validation_error": result.get("validation_error"),
        "events": result.get("events", []),
    }

    print(json.dumps(summary, indent=2))

    return (
        0
        if result.get("status")
        in {
            "branch_committed",
            "artifacts_written",
            "rejected",
            "validation_failed",
        }
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())