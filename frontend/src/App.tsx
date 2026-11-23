import { useCallback, useEffect, useState } from "react";
import { Activity, AlertCircle, ArrowUpRight, BarChart3, Bell, Boxes, Cloud, CircleDollarSign, Database, HardDrive, Home, Layers3, LogOut, PackageSearch, RefreshCw, Search, Settings2, ShieldCheck, Target, UserRound, Wallet, Zap } from "lucide-react";
import FinovauntOverview from "./FinovauntOverview";
import FinopsEvidence, { type FinOpsAssessment } from "./FinopsEvidence";

type Account = { id: string; account_id: string; name: string; provider: string; role_arn: string; region: string; status: string };
type ServiceCost = { service: string; amount: number; amount_exact?: string; currency: string };
type Billing = { id: string; scanned_at: string; status: string; total_cost: number; total_cost_exact?: string; currency: string; period_start: string; period_end_exclusive: string; services: ServiceCost[]; is_final: boolean };
type Asset = { id: string; type: string; name: string; state: string; size: string; region: string; recommendation: string; cost_status: string };
type Inventory = { id: string; scanned_at: string; status: string; region: string; asset_count: number; truncated: boolean; observed_total?: number; resource_cap?: number; observed_counts?: Record<string,number>; collected_counts?: Record<string,number>; assets: Asset[] };
type History = { id: string; scanned_at: string; period_start: string; total_cost: number; currency: string; status: string };
type Candidate = { resource_id: string; name: string; type: string; region: string; reason: string; estimated_monthly_savings: string | null; possible_monthly_storage_reduction_usd?: string | null; verified_savings: null; confidence: string; risk: string; action: string; inventory_scan_id: string; pricing?: {source: string; usd_per_gb_month: string; unit: string; volume_type: string} | null; kubernetes?: {status: string; discovery_status?: string; pv_references?: {cluster:string;pv:string;pvc?:string;namespace?:string;reclaim_policy?:string}[]; tags?: Record<string,string>}; evidence?: string[]; assumptions?: string[]; can_auto_delete: false };
type HistoricEbs = { account_id: string; region: string; resource_id: string; name: string; first_seen_at: string; last_seen_at: string; lifecycle: string; observations: number; latest_evidence?: {size_gib?: number; volume_type?: string; potential_storage_reduction_usd?: string | null; estimated_savings_usd?: string | null}; savings_verified_usd: null };
type AwsSourceStatus = { status: "direct_role_ready" | "assume_role_required"; source_account_id: string; source_principal_arn: string; target_role_arn: string; note: string; checked_at: string; role_assumption_verified: boolean };
type Review = { id: string; inventory_scan_id: string; resource_id: string; decision: string; note: string; reviewed_by: string; reviewed_at: string; infrastructure_applied: false };
type Dashboard = { source: "aws_collected"; account: Account; billing: Billing | null; inventory: Inventory | null; billing_history: History[]; review_candidates: Candidate[]; ebs_reviews: Review[]; optimization_history: HistoricEbs[]; potential_ebs_savings_usd?: string | null; ebs_price_coverage?: {priced_candidates:number; total_candidates:number}; estimated_savings: null; realized_savings: null; billing_status: string; inventory_status: string };
type Tab = "Overview" | "Assets" | "Cost Breakdown" | "AWS FinOps" | "Review Candidates" | "Scan History";
const tabs: Tab[] = ["Overview", "Assets", "Cost Breakdown", "AWS FinOps", "Review Candidates", "Scan History"];

function formatMoney(amount: number | null | undefined, currency?: string) {
  if (amount == null || !Number.isFinite(amount)) return "Not available";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: currency || "USD", maximumFractionDigits: 2 }).format(amount);
}
function formatTime(value?: string) {
  if (!value) return "Not collected";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    credentials: "same-origin",
    headers: { Accept: "application/json", ...(init?.body ? { "Content-Type": "application/json" } : {}) },
    ...init,
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof body.message === "string" ? body.message : "Request failed (" + response.status + ")");
  return body as T;
}
function Empty({ children }: { children: React.ReactNode }) {
  return <div className="empty-state" style={{ padding: 28, textAlign: "center" }}>{children}</div>;
}
function Metric({ label, value, detail, Icon }: { label: string; value: string; detail: string; Icon: typeof Wallet }) {
  return <article className="metric-card"><div className="metric-icon"><Icon size={19}/></div><span>{label}</span><strong style={{display: "block",fontSize: 27,margin: "9px 0"}}>{value}</strong><small>{detail}</small></article>;
}

export default function App({ onOpenCloud, onOpenProfile, onSignOut, username }: { onOpenCloud: () => void; onOpenProfile: () => void; onSignOut: () => void; username: string }) {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [accountId, setAccountId] = useState("");
  const [data, setData] = useState<Dashboard | null>(null);
  const [tab, setTab] = useState<Tab>("Overview");
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState("");
  const [scanErrors, setScanErrors] = useState<string[]>([]);
  const [sourceStatus, setSourceStatus] = useState<AwsSourceStatus | null>(null);
  const [sourceError, setSourceError] = useState("");
  const [finops, setFinops] = useState<FinOpsAssessment | null>(null);
  const [finopsBusy, setFinopsBusy] = useState(false);
  const [finopsError, setFinopsError] = useState("");
  const [checkingSource, setCheckingSource] = useState(false);
  const [externalId, setExternalId] = useState("");
  const [reviewResource, setReviewResource] = useState("");
  const [reviewNote, setReviewNote] = useState("");
  const [reviewDecision, setReviewDecision] = useState<"approved_for_manual_review" | "rejected">("approved_for_manual_review");
  const [reviewBusy, setReviewBusy] = useState(false);
  const [reviewMessage, setReviewMessage] = useState("");
  const [lastRefresh, setLastRefresh] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  const loadAccounts = useCallback(async () => {
    try {
      const response = await request<{items: Account[]}>("/api/cloud-accounts");
      setAccounts(response.items);
      setAccountId(current => response.items.some(a => a.account_id === current) ? current : (response.items[0]?.account_id || ""));
    } catch (err) { setError(err instanceof Error ? err.message : "Unable to load cloud accounts."); }
  }, []);

  const loadDashboard = useCallback(async (id: string) => {
    if (!id) { setData(null); setLoading(false); return; }
    setLoading(true); setError("");
    try {
      const response = await request<Dashboard>("/api/live-dashboard?account_id=" + encodeURIComponent(id));
      setData(response); setLastRefresh(new Date().toISOString());
    } catch (err) {
      setData(null);
      setError(err instanceof Error ? err.message : "Unable to load AWS data.");
    } finally { setLoading(false); }
  }, []);

  const loadFinops = useCallback(async (id: string) => {
    if (!id) { setFinops(null); return; }
    try {
      const response = await request<{latest: FinOpsAssessment | null}>("/api/finops-assessments?account_id=" + encodeURIComponent(id));
      setFinops(response.latest);
    } catch { setFinops(null); }
  }, []);

  async function collectFinops() {
    if (!accountId || finopsBusy) return;
    setFinopsBusy(true); setFinopsError("");
    try {
      const result = await request<FinOpsAssessment>("/api/finops-assessments", {
        method: "POST", body: JSON.stringify({account_id: accountId, external_id: externalId}),
      });
      setFinops(result);
    } catch (err) {
      setFinopsError(err instanceof Error ? err.message : "FinOps assessment unavailable.");
    } finally { setFinopsBusy(false); }
  }

  useEffect(() => { void loadAccounts(); }, [loadAccounts]);
  useEffect(() => { void loadDashboard(accountId); void loadFinops(accountId); }, [accountId, loadDashboard, loadFinops]);

  async function checkSource() {
    if (!accountId || checkingSource) return;
    setCheckingSource(true); setSourceError(""); setSourceStatus(null);
    try {
      const status = await request<AwsSourceStatus>("/api/aws-credential-status?account_id=" + encodeURIComponent(accountId));
      setSourceStatus(status);
    } catch (err) {
      setSourceError(err instanceof Error ? err.message : "AWS source credentials are unavailable.");
    } finally { setCheckingSource(false); }
  }

  async function collectAWS() {
    if (!accountId || scanning) return;
    setScanning(true); setScanErrors([]); setError("");
    const result = await Promise.allSettled([
      request("/api/billing-scans", { method: "POST", body: JSON.stringify({ account_id: accountId, external_id: externalId }) }),
      request("/api/inventory-scans", { method: "POST", body: JSON.stringify({ account_id: accountId, external_id: externalId }) }),
    ]);
    const failures = result.flatMap((item, index) => item.status === "rejected" ?
      [(index === 0 ? "Cost Explorer: " : "Inventory: ") + (item.reason instanceof Error ? item.reason.message : "AWS request failed")] : []);
    setScanErrors(failures);
    await loadDashboard(accountId);
    setScanning(false);
  }

  async function submitReview(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!data?.inventory || !reviewResource || reviewNote.trim().length < 10) return;
    setReviewBusy(true); setReviewMessage("");
    try {
      await request("/api/ebs-reviews", { method: "POST", body: JSON.stringify({
        account_id: accountId, inventory_scan_id: data.inventory.id,
        resource_id: reviewResource, decision: reviewDecision, note: reviewNote.trim(),
      }) });
      setReviewNote("");
      setReviewMessage("Review recorded. No AWS or Kubernetes changes were made.");
      await loadDashboard(accountId);
    } catch (err) {
      setReviewMessage(err instanceof Error ? err.message : "Review could not be saved.");
    } finally { setReviewBusy(false); }
  }

  const billing = data?.billing;
  const inventory = data?.inventory;
  const noEvidence = !billing && !inventory;

  return <div className="app-shell fv-shell">
    <aside className="sidebar fv-sidebar">
      <div className="brand fv-brand"><div className="brand-symbol fv-logo"><Layers3 size={23}/></div><div><strong>Finovaunt</strong><span>AWS FinOps Platform</span></div></div>
      <nav className="nav-list fv-nav" aria-label="Dashboard sections">
        <span className="fv-nav-label">WORKSPACE</span>
        {([
          ["Overview", Home, "Overview"],
          ["Review Candidates", Zap, "Recommendations"],
          ["Assets", Boxes, "Resources"],
          ["Cost Breakdown", BarChart3, "Cost Explorer"],
          ["AWS FinOps", Layers3, "Cost Allocation & EKS"],
          ["Scan History", Activity, "Scan History"],
        ] as const).map(([value,Icon,label])=><button key={value} className={"nav-item "+(tab===value?"active":"")} aria-current={tab===value?"page":undefined} onClick={()=>setTab(value)}><Icon size={18}/><span>{label}</span></button>)}
        <span className="fv-nav-label fv-nav-label-secondary">ACCOUNT</span>
        <button className="nav-item" onClick={onOpenCloud}><Cloud size={18}/><span>AWS Accounts</span></button>
        <button className="nav-item" onClick={onOpenProfile}><Settings2 size={18}/><span>Settings & Profile</span></button>
      </nav>
      <div className="sidebar-bottom fv-sidebar-bottom">
        <div className="fv-workload-box"><span className="fv-workload-mark">aws</span><div><strong>AWS Only</strong><small>Read-only collector</small></div><ShieldCheck size={17}/></div>
        <span className="version">FINOVAUNT · COST INTELLIGENCE</span>
      </div>
    </aside>
    <main className="main fv-main">
      <header className="topbar fv-topbar">
        <div className="fv-toolbar-left">
          <label className="fv-toolbar-field fv-account-select"><span>Account Scope</span>
            <select aria-label="AWS account scope" value={accountId} onChange={e=>{setAccountId(e.target.value);setScanErrors([]);setExternalId("");setSourceStatus(null);setSourceError("");setSearch("");}}>
              {!accounts.length&&<option value="">No AWS accounts connected</option>}
              {accounts.map(a=><option value={a.account_id} key={a.account_id}>{a.name} · {a.account_id}</option>)}
            </select>
          </label>
          <div className="fv-toolbar-field fv-region-tag"><span>AWS Region</span><strong>{accounts.find(a=>a.account_id===accountId)?.region||"Not selected"}</strong></div>
          <div className="fv-toolbar-field fv-period-tag"><span>Billing Period</span><strong>Current Month</strong></div>
        </div>
        <div className="fv-toolbar-right">
          <label className="fv-toolbar-search"><Search size={16}/><input aria-label="Search collected services and recommendations" placeholder="Search services or resources…" value={search} onChange={e=>setSearch(e.target.value)}/></label>
          <button type="button" className="fv-icon-action" title="Refresh dashboard evidence" aria-label="Refresh dashboard evidence" disabled={!accountId||loading} onClick={()=>{void loadDashboard(accountId);void loadFinops(accountId);}}><RefreshCw size={17}/></button>
          <div className="fv-user-menu"><button type="button" className="fv-avatar-button" onClick={onOpenProfile} title="Open profile"><span className="fv-avatar">{(username||"A").slice(0,2).toUpperCase()}</span><UserRound size={14}/></button>
            <button type="button" className="fv-icon-action fv-signout" onClick={onSignOut} title="Sign out" aria-label="Sign out"><LogOut size={16}/></button></div>
        </div>
      </header>
      <div className="page-content fv-page">
        <section className="page-heading fv-heading"><div><div className="fv-heading-title"><h1>{tab==="Overview"?"FinOps Overview":tab==="AWS FinOps"?"AWS FinOps Evidence":tab==="Review Candidates"?"Optimization Recommendations":tab==="Assets"?"AWS Resources":tab==="Cost Breakdown"?"Cost Explorer":"Scan History"}</h1><span className="fv-aws-tag">AWS</span></div><p>Spend, optimization and resource evidence across the selected AWS account.</p></div>
          <div className="fv-heading-actions"><span className="fv-readonly"><ShieldCheck size={15}/> Read-only collector</span><button className="fv-outline-button" onClick={onOpenCloud}><Cloud size={16}/> Manage Accounts</button><button className="fv-primary-button" onClick={()=>void collectAWS()} disabled={!accountId||scanning}><RefreshCw size={16}/>{scanning?"Collecting…":"Collect AWS Data"}</button></div>
        </section>
        {!accounts.length?<section className="panel fv-connect-panel"><Cloud size={24}/><div><h2>Connect your first AWS account</h2><p>Onboard the existing read-only collector role to begin cost and inventory collection.</p></div><button className="fv-primary-button" onClick={onOpenCloud}>Connect AWS <ArrowUpRight size={15}/></button></section>:
        <details className="fv-collector-details"><summary><ShieldCheck size={16}/> Connection & Collection Settings <span>{accounts.find(a=>a.account_id===accountId)?.name} · {data?.account?.region||"AWS"}</span></summary>
          <div className="fv-collector-controls"><label>IAM External ID (only when required)<input type="password" autoComplete="off" placeholder="Not saved" value={externalId} onChange={e=>setExternalId(e.target.value)}/></label>
            <button className="fv-outline-button" type="button" onClick={()=>void checkSource()} disabled={checkingSource||!accountId}>{checkingSource?"Checking…":"Check AWS Credentials"}</button>
            <button className="fv-outline-button" type="button" onClick={()=>void collectFinops()} disabled={finopsBusy||!accountId}>{finopsBusy?"Collecting…":"Collect FinOps Evidence"}</button>
          </div>
        </details>}
        {sourceStatus && <section className="panel" style={{marginBottom: 16}} aria-live="polite"><strong>AWS Source Identity</strong><p>{sourceStatus.status === "direct_role_ready" ? "Direct collector role ready" : "Source credentials found; target role assumption still needs verification"} · {sourceStatus.source_account_id}</p><small>{sourceStatus.source_principal_arn}</small><p>{sourceStatus.note}</p></section>}
        {sourceError && <div className="error-banner" role="alert"><AlertCircle size={18}/><div><strong>AWS Credentials Unavailable</strong><span>{sourceError}</span></div></div>}
        {error && <div className="error-banner" role="alert"><AlertCircle size={18}/><div><strong>Unable to Load Account Data</strong><span>{error}</span></div></div>}
        {scanErrors.map(message => <div key={message} className="error-banner" role="alert"><AlertCircle size={18}/><div><strong>AWS Collection Failed</strong><span>{message}</span><small>Verify the source AWS credential chain, sts:AssumeRole trust, External ID, and read-only permissions.</small></div></div>)}
        {loading && <p role="status">Loading persisted AWS evidence…</p>}
        {accountId && !loading && noEvidence && !error && <section className="panel" style={{marginBottom: 20}}><h2>No AWS Data Collected Yet</h2><p>This account has been onboarded, but neither Cost Explorer nor inventory collection has completed. Click <strong>Collect Live AWS Data</strong> after configuring the API container's AWS credentials. No spend or resource count is assumed.</p></section>}
        {data && <div style={{marginBottom: 15,fontSize: 13,opacity: .8}}>Account: {data.account.account_id} · Region: {data.account.region} · Billing: {billing ? formatTime(billing.scanned_at) : "Not collected"} · Inventory: {inventory ? formatTime(inventory.scanned_at) : "Not collected"}{lastRefresh ? " · Dashboard refreshed " + formatTime(lastRefresh) : ""}</div>}
        {tab === "Overview" && <FinovauntOverview
          billing={billing} history={data?.billing_history||[]} inventory={inventory}
          candidates={data?.review_candidates||[]} finops={finops}
          potentialStorageSavings={data?.potential_ebs_savings_usd||null}
          reviewedCount={data?.ebs_reviews?.length||0}
          search={search} onNavigate={setTab}
        />}
        {tab === "AWS FinOps" && <section className="panel table-panel">
          <h2>AWS FinOps · Cost Allocation and Optimization</h2>
          <p>Read-only assessment for AWS Cost Explorer tags, EC2/RDS utilization, S3 storage, EKS clusters and existing AWS Budgets. This does not execute shutdowns or claim unverified savings.</p>
          <button className="primary-button" disabled={finopsBusy || !accountId} onClick={() => void collectFinops()}>{finopsBusy ? "Collecting Read-Only Evidence…" : "Collect AWS FinOps Evidence"}</button>
          {finopsError && <p role="alert">{finopsError}</p>}
          <FinopsEvidence report={finops}/>
        </section>}
        {tab === "Assets" && <section className="panel table-panel"><h2>Observed AWS Resources</h2>{inventory ? inventory.assets.length ? <div className="table-scroll"><table><thead><tr><th>Resource</th><th>Type</th><th>State</th><th>Size</th><th>Region</th><th>Monthly Cost</th></tr></thead><tbody>{inventory.assets.map(a => <tr key={a.type + a.id}><td><strong>{a.name}</strong><small className="subline">{a.id}</small></td><td>{a.type.toUpperCase()}</td><td>{a.state}</td><td>{a.size}</td><td>{a.region}</td><td>Not attributed</td></tr>)}</tbody></table></div> : <Empty>AWS returned zero EC2, RDS, or EBS resources in the selected region.</Empty> : <Empty>Inventory not collected. Run an AWS collection to list actual resources.</Empty>}</section>}
        {tab === "Cost Breakdown" && <section className="panel table-panel"><h2>Account-Level Billing · Cost Explorer</h2>{billing ? <><p>Unblended cost from {billing.period_start} through {billing.period_end_exclusive} (exclusive). Current month values are provisional.</p><div className="table-scroll"><table><thead><tr><th>AWS Service</th><th>Observed Spend</th><th>Currency</th></tr></thead><tbody>{[...billing.services].sort((a,b) => b.amount - a.amount).map(s => <tr key={s.service}><td>{s.service}</td><td>{formatMoney(s.amount, s.currency)}</td><td>{s.currency}</td></tr>)}</tbody></table></div></> : <Empty>No Cost Explorer billing collected for this account.</Empty>}</section>}
        {tab === "Review Candidates" && <section className="panel table-panel">
          <h2>EBS Optimization · Evidence and Human Review</h2>
          <p>Potential monthly storage reductions are estimates from AWS Price List OnDemand GB-month rates, not realized savings. EKS/PV evidence, retained data, snapshots, IOPS and throughput may block or change a recommendation. Finovaunt never deletes resources.</p>
          <div className="snapshot-row"><span>Potential monthly EBS storage reduction (priced subset)</span><strong>{data?.potential_ebs_savings_usd == null ? "Not estimable" : formatMoney(Number(data.potential_ebs_savings_usd))}</strong></div>
          <div className="snapshot-row"><span>Verified or realized savings</span><strong>Not verified</strong></div>
          <div className="snapshot-row"><span>Pricing coverage</span><strong>{data?.ebs_price_coverage?.priced_candidates ?? 0} of {data?.ebs_price_coverage?.total_candidates ?? 0} candidates</strong></div>
          {inventory ? data?.review_candidates.length ? <div className="table-scroll"><table><thead><tr><th>Resource / Volume ID</th><th>Region</th><th>Potential Storage / Month</th><th>EKS PV Correlation</th><th>Risk / Confidence</th><th>Evidence</th></tr></thead><tbody>{data.review_candidates.map(c => <tr key={c.resource_id}>
            <td><strong>{c.name}</strong><small className="subline">{c.resource_id}</small></td>
            <td>{c.region}</td>
            <td>{c.estimated_monthly_savings == null ? "Not estimable" : formatMoney(Number(c.estimated_monthly_savings))}<small className="subline">Storage-only scenario, not verified</small></td>
            <td>{c.kubernetes?.status || "not_verified"}<small className="subline">{c.kubernetes?.discovery_status || "No EKS evidence"}</small>{c.kubernetes?.pv_references?.map((pv, i) => <small className="subline" key={i}>{pv.cluster} / PV {pv.pv} / PVC {pv.namespace || "?"}/{pv.pvc || "?"}</small>)}</td>
            <td>{c.risk} risk<small className="subline">{c.confidence} confidence</small></td>
            <td><details><summary>View evidence and assumptions</summary><p>{c.reason}</p><ul>{(c.evidence || []).map((e,i) => <li key={i}>{e}</li>)}</ul><small>Pricing: {c.pricing ? `${c.pricing.source}; ${c.pricing.usd_per_gb_month} USD/${c.pricing.unit}` : "Unavailable"}</small><ul>{(c.assumptions || []).map((a,i) => <li key={i}>{a}</li>)}</ul></details></td>
          </tr>)}</tbody></table></div> : <Empty>No unattached EBS candidates identified in this inventory.</Empty> : <Empty>Collect real AWS inventory to review EBS volumes.</Empty>}
          {data?.review_candidates.length ? <form onSubmit={e => void submitReview(e)} className="fin-settings-form" style={{marginTop: 24, display: "grid", gap: 12, maxWidth: 700}}>
            <h3>Record Human Review (Audit Only)</h3>
            <label>Unattached EBS volume<select required value={reviewResource} onChange={e => setReviewResource(e.target.value)}>
              <option value="">Select a candidate</option>{data.review_candidates.map(c => <option key={c.resource_id} value={c.resource_id}>{c.name} · {c.resource_id}</option>)}
            </select></label>
            <label>Decision<select value={reviewDecision} onChange={e => setReviewDecision(e.target.value as "approved_for_manual_review" | "rejected")}>
              <option value="approved_for_manual_review">Approve for External Manual Investigation (No Deletion)</option><option value="rejected">Reject Candidate</option>
            </select></label>
            <label>Evidence-Based Review Note<textarea required minLength={10} maxLength={2000} rows={3} value={reviewNote} onChange={e => setReviewNote(e.target.value)} placeholder="Document ownership, Kubernetes PV/PVC references, backup/retention verification, and risk." /></label>
            <button className="primary-button" disabled={reviewBusy || reviewNote.trim().length < 10 || !reviewResource}>{reviewBusy ? "Recording…" : "Save Review (No AWS Changes)"}</button>
            {reviewMessage && <p role="status">{reviewMessage}</p>}
          </form> : null}
          <h3 style={{marginTop: 22}}>Historical EBS Optimization Findings</h3>
          <p>Findings persist after a volume disappears from subsequent inventories. Absence from a complete scan is not proof of deletion or verified financial savings.</p>
          {data?.optimization_history?.length ? <div className="table-scroll"><table><thead><tr><th>Volume</th><th>Region</th><th>Last Observed</th><th>Lifecycle</th><th>Historic Storage Scenario</th><th>Verified Savings</th></tr></thead><tbody>{[...data.optimization_history].reverse().map(h => <tr key={h.region + h.resource_id}><td><strong>{h.name}</strong><small className="subline">{h.resource_id}</small></td><td>{h.region}</td><td>{formatTime(h.last_seen_at)}<small className="subline">{h.observations} observations</small></td><td>{h.lifecycle.replaceAll("_", " ")}</td><td>{h.latest_evidence?.potential_storage_reduction_usd == null ? "Not estimable" : formatMoney(Number(h.latest_evidence.potential_storage_reduction_usd))}<small className="subline">Historic estimate, not accrued savings</small></td><td>Not verified</td></tr>)}</tbody></table></div> : <Empty>No historical EBS candidates recorded yet. Legacy scans are not retroactively inferred.</Empty>}
          <h3 style={{marginTop: 22}}>Review Audit History</h3>
          {data?.ebs_reviews?.length ? <div className="table-scroll"><table><thead><tr><th>Volume</th><th>Decision</th><th>Reviewer / Date</th><th>Note</th><th>AWS Changes</th></tr></thead><tbody>{[...data.ebs_reviews].reverse().map(r => <tr key={r.id}><td>{r.resource_id}</td><td>{r.decision}</td><td>{r.reviewed_by}<small className="subline">{formatTime(r.reviewed_at)}</small></td><td>{r.note}</td><td>None</td></tr>)}</tbody></table></div> : <Empty>No review decisions recorded.</Empty>}
        </section>}
        {tab === "Scan History" && <section className="panel table-panel"><h2>Persisted AWS Collection History</h2>{data?.billing_history.length ? <div className="table-scroll"><table><thead><tr><th>Collected At</th><th>Month</th><th>Month-to-Date Spend</th><th>Status</th></tr></thead><tbody>{[...data.billing_history].reverse().map(s => <tr key={s.id}><td>{formatTime(s.scanned_at)}</td><td>{s.period_start}</td><td>{formatMoney(s.total_cost,s.currency)}</td><td>{s.status}</td></tr>)}</tbody></table></div> : <Empty>No Cost Explorer collection history exists for this account.</Empty>}{inventory && <p>Latest inventory collection: {formatTime(inventory.scanned_at)} · {inventory.asset_count} regional resources · {inventory.status}</p>}</section>}
        <footer className="footer"><span>Finovaunt · Read-only AWS Evidence</span><span>Values come from persisted AWS API responses; click Collect Live AWS Data to request a new snapshot.</span></footer>
      </div>
    </main>
  </div>;
}
