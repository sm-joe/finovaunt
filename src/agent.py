"""LangGraph FinOps workflow: collect, optimize, assess, approve, branch."""
import json, os, re, subprocess, uuid
from pathlib import Path
from typing import Any, TypedDict
from langgraph.graph import END, START, StateGraph
from src.tools.cloud_metrics import collect_mock_metrics
from src.utils.guardrails import ResourceMetric, OptimizationProposal, scrub_sensitive_text, validate_hcl_locally

class AgentState(TypedDict, total=False):
    """Serializable state. Never store credentials here."""
    run_id: str
    metrics: list[dict[str, Any]]
    proposals: list[dict[str, Any]]
    generated_hcl: str
    validation_error: str
    risk_summary: list[str]
    approved: bool
    approval_reason: str
    output_path: str
    git_branch: str
    status: str
    events: list[str]

def _event(s, message):
    return [*s.get("events", []), scrub_sensitive_text(message)]

def collect_data(s: AgentState) -> AgentState:
    metrics = collect_mock_metrics()
    return {"run_id":s.get("run_id") or uuid.uuid4().hex[:12],"metrics":[m.model_dump(mode="json") for m in metrics],"events":_event(s,f"Collected {len(metrics)} mock metrics"),"status":"data_collected"}

def optimize(s: AgentState) -> AgentState:
    """Generate structured recommendations with conservative deterministic policy."""
    proposals = []
    for raw in s.get("metrics", []):
        m = ResourceMetric.model_validate(raw)
        eligible = m.resource_type == "compute" and m.environment in {"dev","test"} and m.avg_cpu_percent < 10 and m.peak_cpu_percent < 35 and not m.production_critical
        if eligible:
            p = OptimizationProposal(resource_id=m.resource_id,provider=m.provider,action="rightsize",rationale=f"Non-production compute averages {m.avg_cpu_percent:.1f}% CPU and peaks at {m.peak_cpu_percent:.1f}%; review a one-step reduction.",estimated_monthly_savings_usd=round(m.monthly_cost_usd*.30,2),risk="medium",proposed_instance_type="smaller-compatible-size; verify provider catalog")
        else:
            hot = m.peak_cpu_percent >= 80 or m.production_critical
            p = OptimizationProposal(resource_id=m.resource_id,provider=m.provider,action="no_change" if hot else "review_only",rationale=f"Peak CPU is {m.peak_cpu_percent:.1f}%; conservative policy blocks automatic rightsizing.",estimated_monthly_savings_usd=0,risk="critical" if hot else "high")
        proposals.append(p.model_dump(mode="json"))
    # Keep the proposal artifact valid and clean under default TFLint rules:
    # declare the supported Terraform version and expose review metadata as an output
    # instead of an unused local. This file does not modify cloud resources.
    hcl = """# Proposal metadata only; no cloud changes.
terraform {
  required_version = ">= 1.5.0"
}

output "finops_review" {
  description = "Human review metadata; this proposal does not change cloud resources."
  value = {
    owner  = "platform"
    status = "requires-human-review"
  }
}
"""
    return {"proposals":proposals,"generated_hcl":hcl,"events":_event(s,f"Generated {len(proposals)} proposals"),"status":"optimized"}

def assess_risk(s: AgentState) -> AgentState:
    risks=[]; metrics={m["resource_id"]:ResourceMetric.model_validate(m) for m in s.get("metrics",[])}
    for raw in s.get("proposals",[]):
        p=OptimizationProposal.model_validate(raw); m=metrics[p.resource_id]
        if m.environment=="prod" or m.production_critical: risks.append(f"{p.resource_id}: production requires review")
        if p.risk in {"high","critical"}: risks.append(f"{p.resource_id}: {p.risk} risk")
    try: hcl=validate_hcl_locally(s.get("generated_hcl",""))
    except (ValueError,RuntimeError,subprocess.TimeoutExpired) as exc:
        return {"validation_error":scrub_sensitive_text(exc),"risk_summary":risks+["HCL validation failed; branch writing blocked"],"events":_event(s,"HCL validation failed"),"status":"validation_failed"}
    return {"generated_hcl":hcl,"risk_summary":risks,"events":_event(s,f"Risk assessment complete: {len(risks)} flags"),"status":"ready_for_approval"}

def route_assessment(s): return "reject" if s.get("validation_error") else "approval"

def approval(s: AgentState) -> AgentState:
    print("\n=== Human approval gate ===")
    print(f"Run {s.get('run_id')} | estimated savings ${sum(p['estimated_monthly_savings_usd'] for p in s.get('proposals',[])):.2f}/month")
    for p in s.get("proposals",[]): print(f"- {p['provider']} {p['resource_id']}: {p['action']} ({p['risk']}; ${p['estimated_monthly_savings_usd']:.2f}/mo)")
    for risk in s.get("risk_summary",[]): print("REVIEW:",risk)
    try: answer=input("Type 'approve' to create local proposal branch; anything else rejects: ").strip().lower()
    except (EOFError,KeyboardInterrupt): answer="reject"
    ok=answer=="approve"
    return {"approved":ok,"approval_reason":"interactive approval" if ok else "not approved","status":"approved" if ok else "rejected"}

def route_approval(s): return "write" if s.get("approved") else "reject"

def _write_artifacts(directory: Path, s: AgentState):
    directory.mkdir(parents=True,exist_ok=True)
    (directory/"proposal.json").write_text(json.dumps({"run_id":s.get("run_id"),"proposals":s.get("proposals",[]),"risk_summary":s.get("risk_summary",[])},indent=2)+"\n",encoding="utf-8")
    (directory/"main.tf").write_text(s.get("generated_hcl",""),encoding="utf-8")
    (directory/"audit.json").write_text(json.dumps({"events":s.get("events",[])},indent=2)+"\n",encoding="utf-8")

def write_branch(s: AgentState) -> AgentState:
    """Write branch and commit only; never push or call cloud APIs."""
    repo=Path(os.getenv("FINOPS_GIT_REPO",".")).resolve(); out_name=os.getenv("FINOPS_OUTPUT_DIR","artifacts")
    if not re.fullmatch(r"[A-Za-z0-9_-]+",out_name): return {"status":"write_blocked","events":_event(s,"Invalid output directory")}
    def git(*args,env=None):
        return subprocess.run(["git",*args],cwd=repo,capture_output=True,text=True,timeout=30,shell=False,check=False,env=env or {**os.environ,"GIT_TERMINAL_PROMPT":"0"})
    if not (repo/".git").exists():
        out=Path(out_name).resolve(); _write_artifacts(out,s)
        return {"output_path":str(out),"status":"artifacts_written","events":_event(s,"Local artifacts written; no Git repository found")}
    dirty=git("status","--porcelain")
    if dirty.returncode or dirty.stdout.strip(): return {"status":"write_blocked","events":_event(s,"Repository must be clean before branch operation")}
    prefix=re.sub(r"[^A-Za-z0-9/_-]","-",os.getenv("FINOPS_GIT_BRANCH_PREFIX","finops/optimization")).strip("/")
    branch=f"{prefix}/{s['run_id']}"
    if not git("branch","--show-current").stdout.strip(): return {"status":"write_blocked","events":_event(s,"Cannot determine current branch")}
    if git("switch","-c",branch).returncode: return {"status":"write_blocked","events":_event(s,"Branch creation failed")}
    out=repo/out_name; _write_artifacts(out,s)
    if git("add","--",out_name).returncode: return {"status":"write_blocked","git_branch":branch,"events":_event(s,"Git add failed")}
    name=os.getenv("FINOPS_GIT_AUTHOR_NAME","FinOps Optimization Agent"); email=os.getenv("FINOPS_GIT_AUTHOR_EMAIL","finops-agent@example.invalid")
    env={**os.environ,"GIT_TERMINAL_PROMPT":"0","GIT_AUTHOR_NAME":name,"GIT_AUTHOR_EMAIL":email,"GIT_COMMITTER_NAME":name,"GIT_COMMITTER_EMAIL":email}
    if git("commit","-m",f"chore(finops): proposal {s['run_id']}",env=env).returncode: return {"status":"write_blocked","git_branch":branch,"events":_event(s,"Git commit failed")}
    return {"output_path":str(out),"git_branch":branch,"status":"branch_committed","events":_event(s,f"Committed {branch}; no remote push")}

def reject(s: AgentState) -> AgentState:
    return {"status":"validation_failed" if s.get("validation_error") else "rejected","events":_event(s,"Stopped without writing artifacts")}

def build_graph():
    graph=StateGraph(AgentState)
    for name,fn in [("collect_data",collect_data),("optimize",optimize),("assess_risk",assess_risk),("approval",approval),("write",write_branch),("reject",reject)]: graph.add_node(name,fn)
    graph.add_edge(START,"collect_data"); graph.add_edge("collect_data","optimize"); graph.add_edge("optimize","assess_risk")
    graph.add_conditional_edges("assess_risk",route_assessment,{"approval":"approval","reject":"reject"})
    graph.add_conditional_edges("approval",route_approval,{"write":"write","reject":"reject"})
    graph.add_edge("write",END); graph.add_edge("reject",END)
    return graph.compile()
finops_graph=build_graph()
