"""CLI entry point."""
import json
from dotenv import load_dotenv
from src.agent import finops_graph
from src.utils.guardrails import scrub_sensitive_text

def main() -> int:
    load_dotenv()
    try: result=finops_graph.invoke({"events":[]})
    except Exception as exc:
        print("Run failed:",scrub_sensitive_text(exc)); return 1
    summary={"run_id":result.get("run_id"),"status":result.get("status"),"git_branch":result.get("git_branch"),"output_path":result.get("output_path"),"estimated_monthly_savings_usd":round(sum(p.get("estimated_monthly_savings_usd",0) for p in result.get("proposals",[])),2),"risk_summary":result.get("risk_summary",[]),"validation_error":result.get("validation_error"),"events":result.get("events",[])}
    print(json.dumps(summary,indent=2))
    return 0 if result.get("status") in {"branch_committed","artifacts_written","rejected","validation_failed"} else 1
if __name__=="__main__": raise SystemExit(main())
