import { useCallback, useEffect, useRef, useState } from "react";
import { AlertCircle, ArrowUpRight, Cloud, LogOut, RefreshCw } from "lucide-react";
import FinovauntOverview from "./FinovauntOverview";
import "./finovaunt-enterprise.css";
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
export type Tab = "Overview" | "Assets" | "Cost Breakdown" | "AWS FinOps" | "Review Candidates" | "Scan History";

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
  return <div className="empty-state">{children}</div>;
}
export default function App({ onOpenCloud, onOpenProfile, onSignOut, username, tab, onNavigate, signingOut }: { onOpenCloud: () => void; onOpenProfile: () => void; onSignOut: () => void; username: string; tab: Tab; onNavigate: (tab: Tab) => void; signingOut: boolean }) {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [accountId, setAccountId] = useState("");
  const [data, setData] = useState<Dashboard | null>(null);
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

  const dashboardRequest = useRef(0);
  const finopsRequest = useRef(0);

  function selectAccount(id: string) {
    dashboardRequest.current++;
    finopsRequest.current++;
    setAccountId(id);
    setData(null);
    setFinops(null);
    setLoading(Boolean(id));
    setLastRefresh(null);
    setError("");
    setScanErrors([]);
    setFinopsError("");
    setSourceError("");
    setSourceStatus(null);
    setExternalId("");
    setReviewResource("");
    setReviewNote("");
    setReviewDecision("approved_for_manual_review");
    setReviewMessage("");
  }

  const loadAccounts = useCallback(async () => {
    try {
      const response = await request<{items: Account[]}>("/api/cloud-accounts");
      setAccounts(response.items);
      setAccountId(current => response.items.some(a => a.account_id === current) ? current : (response.items[0]?.account_id || ""));
    } catch (err) { setError(err instanceof Error ? err.message : "Unable to load cloud accounts."); }
  }, []);

  const loadDashboard = useCallback(async (id: string) => {
    const requestId = ++dashboardRequest.current;
    if (!id) { setData(null); setLoading(false); return; }
    setLoading(true); setError("");
    try {
      const response = await request<Dashboard>("/api/live-dashboard?account_id=" + encodeURIComponent(id));
      if (requestId !== dashboardRequest.current) return;
      setData(response); setLastRefresh(new Date().toISOString());
    } catch (err) {
      if (requestId !== dashboardRequest.current) return;
      setData(null);
      setError(err instanceof Error ? err.message : "Unable to load AWS data.");
    } finally { if (requestId === dashboardRequest.current) setLoading(false); }
  }, []);

  const loadFinops = useCallback(async (id: string) => {
    const requestId = ++finopsRequest.current;
    if (!id) { setFinops(null); return; }
    try {
      const response = await request<{latest: FinOpsAssessment | null}>("/api/finops-assessments?account_id=" + encodeURIComponent(id));
      if (requestId === finopsRequest.current) setFinops(response.latest);
    } catch { if (requestId === finopsRequest.current) setFinops(null); }
  }, []);

  async function collectFinops() {
    if (!accountId || finopsBusy) return;
    const requestId = ++finopsRequest.current;
    setFinopsBusy(true); setFinopsError("");
    try {
      const result = await request<FinOpsAssessment>("/api/finops-assessments", {
        method: "POST", body: JSON.stringify({account_id: accountId, external_id: externalId}),
      });
      if (requestId === finopsRequest.current) setFinops(result);
    } catch (err) {
      if (requestId === finopsRequest.current) setFinopsError(err instanceof Error ? err.message : "FinOps assessment unavailable.");
    } finally { setFinopsBusy(false); }
  }

  useEffect(() => { void loadAccounts(); }, [loadAccounts]);
  useEffect(() => {
    void loadDashboard(accountId);
    void loadFinops(accountId);
    return () => {
      dashboardRequest.current++;
      finopsRequest.current++;
    };
  }, [accountId, loadDashboard, loadFinops]);

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
    if (reviewBusy || !data?.inventory || !reviewResource || reviewNote.trim().length < 10) return;
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
  const fixedSettings = tab === "Overview" || tab === "Review Candidates" || tab === "AWS FinOps";
  const CollectionSettings = fixedSettings ? "section" : "details";
  const selectedAccount = accounts.find(account => account.account_id === accountId);
  const titles: Record<Tab, string> = {
    Overview: "Overview", Assets: "AWS resources", "Cost Breakdown": "Cost Explorer",
    "AWS FinOps": "Allocation & EKS", "Review Candidates": "Recommendations", "Scan History": "Scan history",
  };

  const showOverview = tab === "Overview" && Boolean(accountId) && !loading && !error;
  const collectionSettings = selectedAccount && (
    <CollectionSettings className={fixedSettings ? "panel fv-collection-settings" : "fv-disclosure fv-collection-settings"} key={`settings-${accountId}`}>
      {fixedSettings ? <h2>Collection settings and snapshot dates</h2> : <summary>Collection settings and snapshot dates</summary>}
      <dl className="fv-snapshot-dates">
        <div><dt>Region</dt><dd>{selectedAccount.region}</dd></div>
        <div><dt>Billing snapshot</dt><dd>{billing ? formatTime(billing.scanned_at) : "Not collected"}</dd></div>
        <div><dt>Inventory snapshot</dt><dd>{inventory ? formatTime(inventory.scanned_at) : "Not collected"}</dd></div>
        {lastRefresh && <div><dt>Last refresh</dt><dd>{formatTime(lastRefresh)}</dd></div>}
      </dl>
      <div className="fv-collector-controls">
        <label>IAM External ID (if required)<input type="password" autoComplete="off" placeholder="Not saved" value={externalId} onChange={e => setExternalId(e.target.value)}/></label>
        <button className="fv-outline-button" type="button" onClick={() => void checkSource()} disabled={checkingSource}>{checkingSource ? "Checking…" : "Check AWS credentials"}</button>
        <button className="fv-outline-button" type="button" aria-label="Refresh dashboard evidence" disabled={loading || finopsBusy} onClick={() => { void loadDashboard(accountId); void loadFinops(accountId); }}>Refresh saved evidence</button>
        {tab !== "Overview" && <button className="fv-outline-button" type="button" onClick={() => void collectAWS()} disabled={scanning}>{scanning ? "Collecting…" : "Collect AWS data"}</button>}
      </div>
    </CollectionSettings>
  );

  return <main className="main fv-main" id="main-content" tabIndex={-1}>
      <header className="topbar fv-topbar">
        <div className="fv-toolbar-left">
          <label className="fv-toolbar-field fv-account-select"><span>Account Scope</span>
            <select aria-label="AWS account scope" value={accountId} disabled={scanning || finopsBusy || checkingSource || reviewBusy} onChange={e=>selectAccount(e.target.value)}>
              {!accounts.length&&<option value="">No AWS accounts connected</option>}
              {accounts.map(a=><option value={a.account_id} key={a.account_id}>{a.name} · {a.account_id}</option>)}
            </select>
          </label>
        </div>
        <div className="fv-toolbar-right">
          <div className="fv-user-menu"><button type="button" className="fv-avatar-button" onClick={onOpenProfile} title="Open profile" aria-label="Open profile"><span className="fv-avatar">{(username||"A").slice(0,2).toUpperCase()}</span></button>
            <button type="button" className="fv-icon-action fv-signout" onClick={onSignOut} disabled={signingOut} title="Sign out" aria-label="Sign out"><LogOut size={16}/></button></div>
        </div>
      </header>
      <div className="page-content fv-page">
        <section className="page-heading fv-heading">
          <h1>{titles[tab]}</h1>
          {accountId && tab === "Overview" && <button className="fv-primary-button" onClick={() => void collectAWS()} disabled={scanning}><RefreshCw size={16}/>{scanning ? "Collecting…" : "Collect AWS data"}</button>}
          {accountId && tab === "AWS FinOps" && <button className="fv-primary-button" onClick={() => void collectFinops()} disabled={finopsBusy}><RefreshCw size={16}/>{finopsBusy ? "Collecting…" : "Collect FinOps evidence"}</button>}
        </section>
        {!accounts.length && !loading && !error && <section className="panel fv-connect-panel"><Cloud size={22}/><div><h2>Connect an AWS account</h2><p>Add a read-only IAM role to start collecting billing and inventory.</p></div><button className="fv-primary-button" onClick={onOpenCloud}>Connect AWS <ArrowUpRight size={15}/></button></section>}
        {sourceStatus && <section className="panel" style={{marginBottom: 16}} aria-live="polite"><strong>AWS Source Identity</strong><p>{sourceStatus.status === "direct_role_ready" ? "Direct collector role ready" : "Source credentials found; target role assumption still needs verification"} · {sourceStatus.source_account_id}</p><small>{sourceStatus.source_principal_arn}</small><p>{sourceStatus.note}</p></section>}
        {sourceError && <div className="error-banner" role="alert"><AlertCircle size={18}/><div><strong>AWS Credentials Unavailable</strong><span>{sourceError}</span></div></div>}
        {error && <div className="error-banner" role="alert"><AlertCircle size={18}/><div><strong>Unable to Load Account Data</strong><span>{error}</span></div></div>}
        {scanErrors.map(message => <div key={message} className="error-banner" role="alert"><AlertCircle size={18}/><div><strong>AWS Collection Failed</strong><span>{message}</span><small>Verify the source AWS credential chain, sts:AssumeRole trust, External ID, and read-only permissions.</small></div></div>)}
        {loading && <p role="status">Loading persisted AWS evidence…</p>}
        {showOverview && <FinovauntOverview key={accountId}
          billing={billing||null} history={data?.billing_history||[]} inventory={inventory||null}
          candidates={data?.review_candidates||[]} finops={finops}
          potentialStorageSavings={data?.potential_ebs_savings_usd||null}
          reviewedCount={data?.ebs_reviews?.length||0}
          onNavigate={onNavigate}
          collectionSettings={collectionSettings}
        />}
        {accountId && !loading && tab === "AWS FinOps" && <>
          {finopsError && <div className="error-banner" role="alert">{finopsError}</div>}
          <FinopsEvidence report={finops}/>
        </>}
        {accountId && !loading && tab === "Assets" && <section className="panel table-panel"><h2>Observed AWS Resources</h2>{inventory ? inventory.assets.length ? <div className="table-scroll"><table><thead><tr><th>Resource</th><th>Type</th><th>State</th><th>Size</th><th>Region</th><th>Monthly Cost</th></tr></thead><tbody>{inventory.assets.map(a => <tr key={a.type + a.id}><td><strong>{a.name}</strong><small className="subline">{a.id}</small></td><td>{a.type.toUpperCase()}</td><td>{a.state}</td><td>{a.size}</td><td>{a.region}</td><td>Not attributed</td></tr>)}</tbody></table></div> : <Empty>AWS returned zero EC2, RDS, or EBS resources in the selected region.</Empty> : <Empty>Inventory not collected. Run an AWS collection to list actual resources.</Empty>}</section>}
        {accountId && !loading && tab === "Cost Breakdown" && <section className="panel table-panel"><h2>Account-Level Billing · Cost Explorer</h2>{billing ? <><p>Unblended cost from {billing.period_start} through {billing.period_end_exclusive} (exclusive). Current month values are provisional.</p><div className="table-scroll"><table><thead><tr><th>AWS Service</th><th>Observed Spend</th><th>Currency</th></tr></thead><tbody>{[...billing.services].sort((a,b) => b.amount - a.amount).map(s => <tr key={s.service}><td>{s.service}</td><td>{formatMoney(s.amount, s.currency)}</td><td>{s.currency}</td></tr>)}</tbody></table></div></> : <Empty>No Cost Explorer billing collected for this account.</Empty>}</section>}
        {accountId && !loading && tab === "Review Candidates" && <div className="fv-review-layout">
          <section className="panel fv-review-estimates">
            <h2>Storage savings estimates</h2>
            <p>Estimates use AWS on-demand storage rates. EKS ownership, retained data, snapshots, IOPS, and throughput can change the result. Realized savings require separate verification.</p>
            <div className="snapshot-row"><span>Potential monthly EBS storage reduction</span><strong>{data?.potential_ebs_savings_usd == null ? "Not estimable" : formatMoney(Number(data.potential_ebs_savings_usd))}</strong></div>
            <div className="snapshot-row"><span>Pricing coverage</span><strong>{data?.ebs_price_coverage?.priced_candidates ?? 0} of {data?.ebs_price_coverage?.total_candidates ?? 0} candidates</strong></div>
          </section>
          <section className="panel table-panel fv-review-candidates">
          <h2>EBS candidates</h2>
          {inventory ? data?.review_candidates.length ? <div className="table-scroll"><table><thead><tr><th>Resource / Volume ID</th><th>Region</th><th>Potential Storage / Month</th><th>EKS PV Correlation</th><th>Risk / Confidence</th><th>Evidence</th></tr></thead><tbody>{data.review_candidates.map(c => <tr key={c.resource_id}>
            <td><strong>{c.name}</strong><small className="subline">{c.resource_id}</small></td>
            <td>{c.region}</td>
            <td>{c.estimated_monthly_savings == null ? "Not estimable" : formatMoney(Number(c.estimated_monthly_savings))}<small className="subline">Storage-only scenario, not verified</small></td>
            <td>{c.kubernetes?.status || "not_verified"}<small className="subline">{c.kubernetes?.discovery_status || "No EKS evidence"}</small>{c.kubernetes?.pv_references?.map((pv, i) => <small className="subline" key={i}>{pv.cluster} / PV {pv.pv} / PVC {pv.namespace || "?"}/{pv.pvc || "?"}</small>)}</td>
            <td>{c.risk} risk<small className="subline">{c.confidence} confidence</small></td>
            <td className="fv-candidate-evidence"><p>{c.reason}</p><ul>{(c.evidence || []).map((e,i) => <li key={i}>{e}</li>)}</ul><small>Pricing: {c.pricing ? `${c.pricing.source}; ${c.pricing.usd_per_gb_month} USD/${c.pricing.unit}` : "Unavailable"}</small><ul>{(c.assumptions || []).map((a,i) => <li key={i}>{a}</li>)}</ul></td>
          </tr>)}</tbody></table></div> : <Empty>No unattached EBS candidates identified in this inventory.</Empty> : <Empty>Collect real AWS inventory to review EBS volumes.</Empty>}
          </section>
          {data?.review_candidates.length ? <section className="panel fv-review-form"><h2>Record a review</h2><form onSubmit={e => void submitReview(e)} className="fin-settings-form">
            <label>Unattached EBS volume<select required value={reviewResource} onChange={e => setReviewResource(e.target.value)}>
              <option value="">Select a candidate</option>{data.review_candidates.map(c => <option key={c.resource_id} value={c.resource_id}>{c.name} · {c.resource_id}</option>)}
            </select></label>
            <label>Decision<select value={reviewDecision} onChange={e => setReviewDecision(e.target.value as "approved_for_manual_review" | "rejected")}>
              <option value="approved_for_manual_review">Approve for External Manual Investigation (No Deletion)</option><option value="rejected">Reject Candidate</option>
            </select></label>
            <label>Evidence-Based Review Note<textarea required minLength={10} maxLength={2000} rows={3} value={reviewNote} onChange={e => setReviewNote(e.target.value)} placeholder="Document ownership, Kubernetes PV/PVC references, backup/retention verification, and risk." /></label>
            <button className="primary-button" disabled={reviewBusy || reviewNote.trim().length < 10 || !reviewResource}>{reviewBusy ? "Recording…" : "Save Review (No AWS Changes)"}</button>
            {reviewMessage && <p role="status">{reviewMessage}</p>}
          </form></section> : null}
          <section className="panel table-panel"><h2>Historical EBS findings</h2>
          <p>Findings persist after a volume disappears from subsequent inventories. Absence from a complete scan is not proof of deletion or verified financial savings.</p>
          {data?.optimization_history?.length ? <div className="table-scroll"><table><thead><tr><th>Volume</th><th>Region</th><th>Last Observed</th><th>Lifecycle</th><th>Historic Storage Scenario</th><th>Verified Savings</th></tr></thead><tbody>{[...data.optimization_history].reverse().map(h => <tr key={h.region + h.resource_id}><td><strong>{h.name}</strong><small className="subline">{h.resource_id}</small></td><td>{h.region}</td><td>{formatTime(h.last_seen_at)}<small className="subline">{h.observations} observations</small></td><td>{h.lifecycle.replaceAll("_", " ")}</td><td>{h.latest_evidence?.potential_storage_reduction_usd == null ? "Not estimable" : formatMoney(Number(h.latest_evidence.potential_storage_reduction_usd))}<small className="subline">Historic estimate, not accrued savings</small></td><td>Not verified</td></tr>)}</tbody></table></div> : <Empty>No historical EBS candidates recorded yet. Legacy scans are not retroactively inferred.</Empty>}
          </section>
          <section className="panel table-panel"><h2>Review audit history</h2>
          {data?.ebs_reviews?.length ? <div className="table-scroll"><table><thead><tr><th>Volume</th><th>Decision</th><th>Reviewer / Date</th><th>Note</th><th>AWS Changes</th></tr></thead><tbody>{[...data.ebs_reviews].reverse().map(r => <tr key={r.id}><td>{r.resource_id}</td><td>{r.decision}</td><td>{r.reviewed_by}<small className="subline">{formatTime(r.reviewed_at)}</small></td><td>{r.note}</td><td>None</td></tr>)}</tbody></table></div> : <Empty>No review decisions recorded.</Empty>}
          </section>
        </div>}
        {accountId && !loading && tab === "Scan History" && <section className="panel table-panel"><h2>Persisted AWS Collection History</h2>{data?.billing_history.length ? <div className="table-scroll"><table><thead><tr><th>Collected At</th><th>Month</th><th>Month-to-Date Spend</th><th>Status</th></tr></thead><tbody>{[...data.billing_history].reverse().map(s => <tr key={s.id}><td>{formatTime(s.scanned_at)}</td><td>{s.period_start}</td><td>{formatMoney(s.total_cost,s.currency)}</td><td>{s.status}</td></tr>)}</tbody></table></div> : <Empty>No Cost Explorer collection history exists for this account.</Empty>}{inventory && <p>Latest inventory collection: {formatTime(inventory.scanned_at)} · {inventory.asset_count} regional resources · {inventory.status}</p>}</section>}
        {!showOverview && collectionSettings}
      </div>
  </main>;
}
