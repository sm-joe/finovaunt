import { useCallback, useEffect, useState } from "react";
import { Activity, AlertCircle, ArrowUpRight, Boxes, Cloud, CircleDollarSign, Database, RefreshCw, ShieldCheck, Wallet } from "lucide-react";

type Account = { id: string; account_id: string; name: string; provider: string; role_arn: string; region: string; status: string };
type ServiceCost = { service: string; amount: number; amount_exact?: string; currency: string };
type Billing = { id: string; scanned_at: string; status: string; total_cost: number; total_cost_exact?: string; currency: string; period_start: string; period_end_exclusive: string; services: ServiceCost[]; is_final: boolean };
type Asset = { id: string; type: string; name: string; state: string; size: string; region: string; recommendation: string; cost_status: string };
type Inventory = { id: string; scanned_at: string; status: string; region: string; asset_count: number; truncated: boolean; assets: Asset[] };
type History = { id: string; scanned_at: string; period_start: string; total_cost: number; currency: string; status: string };
type Candidate = { resource_id: string; name: string; type: string; region: string; reason: string; estimated_monthly_savings: null; action: string };
type Dashboard = { source: "aws_collected"; account: Account; billing: Billing | null; inventory: Inventory | null; billing_history: History[]; review_candidates: Candidate[]; estimated_savings: null; realized_savings: null; billing_status: string; inventory_status: string };
type Tab = "Overview" | "Assets" | "Cost Breakdown" | "Review Candidates" | "Scan History";
const tabs: Tab[] = ["Overview", "Assets", "Cost Breakdown", "Review Candidates", "Scan History"];

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

export default function App({ onOpenCloud }: { onOpenCloud: () => void }) {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [accountId, setAccountId] = useState("");
  const [data, setData] = useState<Dashboard | null>(null);
  const [tab, setTab] = useState<Tab>("Overview");
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState("");
  const [scanErrors, setScanErrors] = useState<string[]>([]);
  const [externalId, setExternalId] = useState("");
  const [lastRefresh, setLastRefresh] = useState<string | null>(null);

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

  useEffect(() => { void loadAccounts(); }, [loadAccounts]);
  useEffect(() => { void loadDashboard(accountId); }, [accountId, loadDashboard]);

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

  const billing = data?.billing;
  const inventory = data?.inventory;
  const noEvidence = !billing && !inventory;

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-symbol"><Cloud size={21}/></div><div><strong>finovaunt</strong><span>AWS Cost Intelligence</span></div></div>
      <div className="workspace-label">LIVE AWS WORKSPACE</div>
      <nav className="nav-list" aria-label="Dashboard sections">
        {tabs.map(label => <button key={label} className={"nav-item " + (tab === label ? "active" : "")} onClick={() => setTab(label)}><Activity size={17}/><span>{label}</span></button>)}
      </nav>
      <div className="sidebar-bottom"><div className="security-note"><ShieldCheck size={17}/><div><strong>Read-only Access</strong><span>No AWS mutations or synthetic data</span></div></div><span className="version">FINOVAUNT · AWS</span></div>
    </aside>
    <main className="main">
      <header className="topbar"><div className="breadcrumb"><span>Finovaunt</span><span className="slash">/</span><strong>{tab}</strong></div><div className="topbar-actions"><span className="api-state online"><i/>Live AWS Evidence</span><button className="icon-button" onClick={() => void loadDashboard(accountId)} disabled={!accountId || loading} title="Reload collected results"><RefreshCw size={16}/></button></div></header>
      <div className="page-content">
        <section className="page-heading"><div><div className="eyebrow">AWS ACCOUNT INTELLIGENCE</div><h1>{tab === "Overview" ? "Cloud Cost Overview" : tab}</h1><p>Observed Cost Explorer billing and regional EC2, RDS, and EBS resources. No sample or fabricated data.</p></div><button className="primary-button" onClick={onOpenCloud}><Cloud size={16}/> Manage AWS Accounts</button></section>
        <section className="panel" style={{marginBottom: 18}}>
          {accounts.length === 0 ? <><h2>Connect Your First AWS Account</h2><p>Onboard a read-only IAM role, then collect actual billing and inventory evidence. No mock data is loaded.</p><button className="primary-button" onClick={onOpenCloud}><ArrowUpRight size={16}/> Onboard AWS Account</button></> :
          <div style={{display: "flex",gap: 16,alignItems: "end",flexWrap: "wrap"}}>
            <label style={{flex: "1 1 260px"}}>Onboarded AWS Account<select value={accountId} onChange={e => {setAccountId(e.target.value);setScanErrors([]);setExternalId("");}}>{accounts.map(a => <option key={a.account_id} value={a.account_id}>{a.name} · {a.account_id} · {a.region}</option>)}</select></label>
            <label style={{flex: "1 1 220px"}}>IAM External ID (only if role requires it)<input type="password" autoComplete="off" value={externalId} onChange={e => setExternalId(e.target.value)} placeholder="Not saved"/></label>
            <button className="primary-button" onClick={() => void collectAWS()} disabled={scanning || !accountId}><RefreshCw size={16}/>{scanning ? "Collecting from AWS…" : "Collect Live AWS Data"}</button>
          </div>}
        </section>
        {error && <div className="error-banner" role="alert"><AlertCircle size={18}/><div><strong>Unable to Load Account Data</strong><span>{error}</span></div></div>}
        {scanErrors.map(message => <div key={message} className="error-banner" role="alert"><AlertCircle size={18}/><div><strong>AWS Collection Failed</strong><span>{message}</span><small>Verify the source AWS credential chain, sts:AssumeRole trust, External ID, and read-only permissions.</small></div></div>)}
        {loading && <p role="status">Loading persisted AWS evidence…</p>}
        {accountId && !loading && noEvidence && !error && <section className="panel" style={{marginBottom: 20}}><h2>No AWS Data Collected Yet</h2><p>This account has been onboarded, but neither Cost Explorer nor inventory collection has completed. Click <strong>Collect Live AWS Data</strong> after configuring the API container's AWS credentials. No spend or resource count is assumed.</p></section>}
        {data && <div style={{marginBottom: 15,fontSize: 13,opacity: .8}}>Account: {data.account.account_id} · Region: {data.account.region} · Billing: {billing ? formatTime(billing.scanned_at) : "Not collected"} · Inventory: {inventory ? formatTime(inventory.scanned_at) : "Not collected"}{lastRefresh ? " · Dashboard refreshed " + formatTime(lastRefresh) : ""}</div>}
        {tab === "Overview" && <>
          <div className="metric-grid">
            <Metric Icon={Wallet} label="Month-to-Date Cloud Spend" value={formatMoney(billing?.total_cost, billing?.currency)} detail={billing ? billing.period_start + " to " + billing.period_end_exclusive + " (provisional)" : "Cost Explorer not collected"}/>
            <Metric Icon={Boxes} label="Observed Resources" value={inventory ? String(inventory.asset_count) : "Not available"} detail={inventory ? inventory.region + (inventory.truncated ? " · Partial inventory" : " · EC2, RDS, EBS") : "Inventory not collected"}/>
            <Metric Icon={Activity} label="Review Candidates" value={inventory ? String(data?.review_candidates.length ?? 0) : "Not available"} detail="Unattached EBS only; human review required"/>
            <Metric Icon={CircleDollarSign} label="Verified Savings" value="Not available" detail="No verified cost attribution or realized savings"/>
          </div>
          <div className="content-grid">
            <section className="panel"><h2>Cost Explorer Spend by Service</h2>{billing ? billing.services.length ? <div className="fin-service-list">{[...billing.services].sort((a,b) => b.amount - a.amount).slice(0, 12).map(s => <div key={s.service}><span>{s.service}</span><strong>{formatMoney(s.amount, s.currency)}</strong></div>)}</div> : <Empty>Cost Explorer returned no service charges for this period.</Empty> : <Empty>Collect AWS billing to show real spend by service.</Empty>}</section>
            <section className="panel"><h2>Collection Evidence</h2><div className="snapshot-row"><span>Billing Source</span><strong>{billing ? "AWS Cost Explorer" : "Not collected"}</strong></div><div className="snapshot-row"><span>Inventory Source</span><strong>{inventory ? "EC2 / RDS / EBS APIs" : "Not collected"}</strong></div><div className="snapshot-row"><span>Collection Scope</span><strong>{inventory?.region || data?.account.region || "—"}</strong></div><div className="snapshot-row"><span>Inventory Completeness</span><strong>{inventory ? (inventory.truncated ? "Truncated" : "Complete for queried services / region") : "Unknown"}</strong></div><p className="context-note"><Database size={16}/> Service-level spend is not attributable to individual resources without additional AWS billing evidence. No savings are inferred.</p></section>
          </div>
        </>}
        {tab === "Assets" && <section className="panel table-panel"><h2>Observed AWS Resources</h2>{inventory ? inventory.assets.length ? <div className="table-scroll"><table><thead><tr><th>Resource</th><th>Type</th><th>State</th><th>Size</th><th>Region</th><th>Monthly Cost</th></tr></thead><tbody>{inventory.assets.map(a => <tr key={a.type + a.id}><td><strong>{a.name}</strong><small className="subline">{a.id}</small></td><td>{a.type.toUpperCase()}</td><td>{a.state}</td><td>{a.size}</td><td>{a.region}</td><td>Not attributed</td></tr>)}</tbody></table></div> : <Empty>AWS returned zero EC2, RDS, or EBS resources in the selected region.</Empty> : <Empty>Inventory not collected. Run an AWS collection to list actual resources.</Empty>}</section>}
        {tab === "Cost Breakdown" && <section className="panel table-panel"><h2>Account-Level Billing · Cost Explorer</h2>{billing ? <><p>Unblended cost from {billing.period_start} through {billing.period_end_exclusive} (exclusive). Current month values are provisional.</p><div className="table-scroll"><table><thead><tr><th>AWS Service</th><th>Observed Spend</th><th>Currency</th></tr></thead><tbody>{[...billing.services].sort((a,b) => b.amount - a.amount).map(s => <tr key={s.service}><td>{s.service}</td><td>{formatMoney(s.amount, s.currency)}</td><td>{s.currency}</td></tr>)}</tbody></table></div></> : <Empty>No Cost Explorer billing collected for this account.</Empty>}</section>}
        {tab === "Review Candidates" && <section className="panel table-panel"><h2>Review-Only Optimization Candidates</h2><p>Unattached EBS volumes are surfaced for human investigation; no price or savings estimate is claimed.</p>{inventory ? data?.review_candidates.length ? <div className="table-scroll"><table><thead><tr><th>Resource</th><th>Region</th><th>Review Reason</th><th>Estimated Savings</th></tr></thead><tbody>{data.review_candidates.map(c => <tr key={c.resource_id}><td><strong>{c.name}</strong><small className="subline">{c.resource_id}</small></td><td>{c.region}</td><td>{c.reason}</td><td>Not estimable</td></tr>)}</tbody></table></div> : <Empty>No unattached EBS volumes identified in the collected regional inventory.</Empty> : <Empty>Collect regional inventory before assessing resources.</Empty>}</section>}
        {tab === "Scan History" && <section className="panel table-panel"><h2>Persisted AWS Collection History</h2>{data?.billing_history.length ? <div className="table-scroll"><table><thead><tr><th>Collected At</th><th>Month</th><th>Month-to-Date Spend</th><th>Status</th></tr></thead><tbody>{[...data.billing_history].reverse().map(s => <tr key={s.id}><td>{formatTime(s.scanned_at)}</td><td>{s.period_start}</td><td>{formatMoney(s.total_cost,s.currency)}</td><td>{s.status}</td></tr>)}</tbody></table></div> : <Empty>No Cost Explorer collection history exists for this account.</Empty>}{inventory && <p>Latest inventory collection: {formatTime(inventory.scanned_at)} · {inventory.asset_count} regional resources · {inventory.status}</p>}</section>}
        <footer className="footer"><span>Finovaunt · Read-only AWS Evidence</span><span>Values come from persisted AWS API responses; click Collect Live AWS Data to request a new snapshot.</span></footer>
      </div>
    </main>
  </div>;
}
