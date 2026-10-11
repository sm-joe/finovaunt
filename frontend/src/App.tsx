//CI Integration Test
import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import {
  Activity, AlertCircle, ArrowUpRight, Boxes, CheckCircle2,
  CircleDollarSign, Clock3, Cloud, Database, Gauge, Layers3, RefreshCw,
  ShieldCheck, Sparkles, TrendingDown, Wallet,
} from "lucide-react";

type Overview = {
  generated_at?: string | null;
  run_id?: string | null;
  data_source?: string;
  currency?: string;
  cloud_spend?: {
    status?: string; amount?: number | null; currency?: string;
    period_start?: string | null; period_end_exclusive?: string | null;
    scope?: string; resource_attribution?: string;
  };
  potential_monthly_savings_usd?: number;
  simulated_monthly_savings_usd?: number;
  realized_savings?: { status?: string; amount_usd?: number | null };
  resources_scanned?: number;
  opportunities?: number;
  resources_without_estimable_savings?: number;
  action_counts?: Record<string, number>;
  risk_counts?: Record<string, number>;
  scan_count?: number;
};
type Resource = {
  resource_id: string; name: string; provider: string; resource_type: string;
  region: string; environment: string; production_critical: boolean;
  utilization?: { avg_cpu_percent?: number | null; peak_cpu_percent?: number | null; avg_memory_percent?: number | null };
  cost?: { status?: string; amount?: number | null; currency?: string; monthly_cost_usd?: number | null; source?: string };
  recommendation?: { action?: string; rationale?: string | null; risk?: string; requires_human_approval?: boolean; proposed_instance_type?: string | null; optimization_confidence?: string; missing_evidence?: string[] };
  savings?: { estimated_monthly_usd?: number | null; basis?: string; classification?: string; realized_status?: string; realized_monthly_usd?: number | null; assumptions?: string[] };
  data_quality_warnings?: string[];
};
type Collection<T> = { count: number; items: T[] };
type Scan = { run_id: string; generated_at?: string | null; resource_count?: number; action_counts?: Record<string, number>; realized_savings?: { status?: string; amount_usd?: number | null } };

const money = (value?: number | null, currency = "USD") =>
  value == null || !Number.isFinite(value)
    ? "—"
    : new Intl.NumberFormat("en-US", { style: "currency", currency, maximumFractionDigits: 2 }).format(value);
const date = (value?: string | null) => {
  if (!value) return "Timestamp unavailable";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
};
const titleCase = (value?: string) =>
  (value || "unknown").replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());

async function getJSON<T>(path: string): Promise<T> {
  const response = await fetch(path, { headers: { Accept: "application/json" } });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = body && typeof body.message === "string" ? body.message : `Request failed (${response.status})`;
    throw new Error(message);
  }
  return body as T;
}

type Tab = "Overview" | "Opportunities" | "Assets" | "Scan History";
const tabs: { label: Tab; icon: typeof Gauge }[] = [
  { label: "Overview", icon: Gauge },
  { label: "Opportunities", icon: Sparkles },
  { label: "Assets", icon: Boxes },
  { label: "Scan History", icon: Activity },
];

export default function App() {
  const [tab, setTab] = useState<Tab>("Overview");
  const [overview, setOverview] = useState<Overview | null>(null);
  const [opportunities, setOpportunities] = useState<Resource[]>([]);
  const [assets, setAssets] = useState<Resource[]>([]);
  const [scans, setScans] = useState<Scan[]>([]);
  const [apiOnline, setApiOnline] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [health, summary, opportunityData, assetData, scanData] = await Promise.all([
        getJSON<{ status: string }>("/api/health"),
        getJSON<Overview>("/api/overview"),
        getJSON<Collection<Resource>>("/api/opportunities"),
        getJSON<Collection<Resource>>("/api/assets"),
        getJSON<Collection<Scan>>("/api/scans"),
      ]);
      setApiOnline(health.status === "ok");
      setOverview(summary);
      setOpportunities(opportunityData.items ?? []);
      setAssets(assetData.items ?? []);
      setScans([...(scanData.items ?? [])].reverse());
      setLastRefresh(new Date());
    } catch (err) {
      setApiOnline(false);
      setError(err instanceof Error ? err.message : "Could not load dashboard data.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  const filteredAssets = useMemo(() => assets.filter((item) =>
    [item.name, item.resource_id, item.resource_type, item.region, item.environment]
      .some((part) => (part || "").toLowerCase().includes(query.toLowerCase()))
  ), [assets, query]);
  const filteredOpportunities = useMemo(() => opportunities.filter((item) =>
    [item.name, item.resource_id, item.resource_type, item.region, item.recommendation?.action]
      .some((part) => (part || "").toLowerCase().includes(query.toLowerCase()))
  ), [opportunities, query]);

  const simulated = (overview?.simulated_monthly_savings_usd ?? 0) > 0 ||
    overview?.data_source === "mock";

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-symbol"><TrendingDown size={21} /></div>
          <div><strong>finovaunt</strong><span>Autonomous FinOps</span></div>
        </div>
        <div className="workspace-label">WORKSPACE</div>
        <nav className="nav-list" aria-label="Dashboard sections">
          {tabs.map(({ label, icon: Icon }) => (
            <button key={label} className={`nav-item ${tab === label ? "active" : ""}`} onClick={() => { setTab(label); setQuery(""); }}>
              <Icon size={17} strokeWidth={1.8} /><span>{label}</span>
              {label === "Opportunities" && opportunities.length > 0 && <span className="nav-count">{opportunities.length}</span>}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="security-note"><ShieldCheck size={17} /><div><strong>Guardrails Active</strong><span>Read-only Dashboard</span></div></div>
          <span className="version">FINOVAUNT · MVP</span>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div className="breadcrumb"><span>Finovaunt</span><span className="slash">/</span><strong>{tab}</strong></div>
          <div className="topbar-actions">
            <span className={`api-state ${apiOnline ? "online" : "offline"}`}><i />{apiOnline ? "API Connected" : "API Unavailable"}</span>
            <button className="icon-button" onClick={() => void refresh()} disabled={loading} aria-label="Refresh dashboard" title="Refresh data"><RefreshCw size={16} className={loading ? "spin" : ""} /></button>
            <div className="avatar">F</div>
          </div>
        </header>

        <div className="page-content">
          <section className="page-heading">
            <div><div className="eyebrow">COST INTELLIGENCE</div><h1>{tab === "Overview" ? "Cloud Cost Overview" : tab}</h1>
              <p>{tab === "Overview" ? "Understand spend, surface optimization opportunities, and track scan evidence." :
                tab === "Opportunities" ? "Prioritized recommendations with transparent evidence and risk." :
                tab === "Assets" ? "Discovered cloud resources and their cost and utilization evidence." :
                "Review scan snapshots and their available evidence."}</p>
            </div>
            <button className="primary-button" onClick={() => void refresh()} disabled={loading}><RefreshCw size={15} /> Refresh data</button>
          </section>

          {error && <div className="error-banner"><AlertCircle size={18} /><div><strong>Dashboard data unavailable</strong><span>{error}</span><small>Confirm the Python API is running and FINOPS_OUTPUT_DIR points to a directory containing cost_evidence.json.</small></div><button onClick={() => void refresh()}>Retry</button></div>}
          {simulated && overview && <div className="simulation-banner"><Sparkles size={16} /><span><strong>Simulation data</strong> — mock-mode estimates are illustrative, not live recommendations or verified savings.</span></div>}

          {tab === "Overview" && <>
            <div className="metric-grid">
              <Metric icon={Wallet} label="Account Cloud Spend" value={money(overview?.cloud_spend?.amount, overview?.cloud_spend?.currency)} note={overview?.cloud_spend?.status ? titleCase(overview.cloud_spend.status) : "Billing context unavailable"} tone="blue" />
              <Metric icon={CircleDollarSign} label="Potential Monthly Savings" value={money(overview?.potential_monthly_savings_usd)} note="Resource-cost evidence only" tone="green" />
              <Metric icon={Sparkles} label="Simulated Savings" value={money(overview?.simulated_monthly_savings_usd)} note="Excluded from potential savings" tone="purple" />
              <Metric icon={Boxes} label="Resources Scanned" value={overview?.resources_scanned?.toLocaleString() ?? "—"} note={`${overview?.opportunities ?? 0} optimization opportunities`} tone="amber" />
            </div>

            <div className="content-grid">
              <section className="panel spend-panel">
                <PanelHeading eyebrow="SCAN SNAPSHOT" title="Latest Cost Intelligence" icon={Activity} />
                <div className="snapshot-row"><span>Data Source</span><strong>{titleCase(overview?.data_source)}</strong></div>
                <div className="snapshot-row"><span>Last Generated</span><strong>{date(overview?.generated_at)}</strong></div>
                <div className="snapshot-row"><span>Run ID</span><code>{overview?.run_id || "—"}</code></div>
                <div className="snapshot-row"><span>Scans in History</span><strong>{overview?.scan_count ?? scans.length}</strong></div>
                <div className="snapshot-row"><span>Resources without Estimable Savings</span><strong>{overview?.resources_without_estimable_savings ?? 0}</strong></div>
                <div className="context-note"><Database size={16} /><span>Account-level billing is contextual only and is not attributed to individual resources.</span></div>
              </section>
              <section className="panel">
                <PanelHeading eyebrow="OPTIMIZATION PIPELINE" title="Recommendation Mix" icon={Layers3} />
                {Object.entries(overview?.action_counts ?? {}).length === 0
                  ? <EmptyState text="No recommendation counts are available in this snapshot." />
                  : <div className="mix-list">{Object.entries(overview?.action_counts ?? {}).sort((a,b) => b[1]-a[1]).map(([action,count]) => {
                    const total = Math.max(1, overview?.resources_scanned ?? 1);
                    return <div className="mix-row" key={action}><div className="mix-label"><span>{titleCase(action)}</span><strong>{count}</strong></div><div className="bar-track"><div className="bar-fill" style={{width: `${Math.min(100, count / total * 100)}%`}} /></div></div>;
                  })}</div>}
                <div className="realized-box"><div className="realized-icon"><CheckCircle2 size={17} /></div><div><strong>Realized Savings</strong><span>Not verified — requires post-change measurement</span></div><b>—</b></div>
              </section>
            </div>

            <section className="panel table-panel">
              <PanelHeading eyebrow="TOP OPPORTUNITIES" title="Evidence-Led Recommendations" icon={Sparkles} action={<button className="text-button" onClick={() => setTab("Opportunities")}>View all <ArrowUpRight size={14} /></button>} />
              <OpportunityTable rows={opportunities.slice(0,5)} />
            </section>
          </>}

          {tab === "Opportunities" && <section className="panel table-panel">
            <PanelHeading eyebrow="OPTIMIZATION QUEUE" title={`${opportunities.length} opportunities`} icon={Sparkles} />
            <Search value={query} onChange={setQuery} placeholder="Search resources or actions…" />
            <OpportunityTable rows={filteredOpportunities} />
          </section>}

          {tab === "Assets" && <section className="panel table-panel">
            <PanelHeading eyebrow="RESOURCE INVENTORY" title={`${assets.length} resources`} icon={Boxes} />
            <Search value={query} onChange={setQuery} placeholder="Search name, type, region, environment…" />
            {filteredAssets.length === 0 ? <EmptyState text="No matching resources in the current snapshot." /> :
              <div className="table-scroll"><table><thead><tr><th>Resource</th><th>Type / Region</th><th>Environment</th><th>Monthly cost</th><th>Avg CPU</th><th>Action</th></tr></thead><tbody>
                {filteredAssets.map((item) => <tr key={`${item.provider}:${item.resource_id}`}><td><strong>{item.name}</strong><small className="subline">{item.resource_id}</small></td><td>{titleCase(item.resource_type)}<small className="subline">{item.region}</small></td><td><span className="pill neutral">{titleCase(item.environment)}</span>{item.production_critical && <small className="subline danger-text">Production critical</small>}</td><td>{money(item.cost?.monthly_cost_usd)}</td><td>{item.utilization?.avg_cpu_percent == null ? "—" : `${item.utilization.avg_cpu_percent.toFixed(1)}%`}</td><td><span className={`pill ${riskTone(item.recommendation?.risk)}`}>{titleCase(item.recommendation?.action)}</span></td></tr>)}
              </tbody></table></div>}
          </section>}

          {tab === "Scan History" && <section className="panel table-panel">
            <PanelHeading eyebrow="AUDITABLE RUNS" title="Scan History" icon={Clock3} />
            {scans.length === 0 ? <EmptyState text="No scan history is available in this artifact snapshot." /> :
              <div className="table-scroll"><table><thead><tr><th>Run</th><th>Generated</th><th>Resources</th><th>Recommendations</th><th>Realized Savings</th></tr></thead><tbody>
                {scans.map((scan) => <tr key={scan.run_id}><td><code>{scan.run_id}</code></td><td>{date(scan.generated_at)}</td><td>{scan.resource_count ?? 0}</td><td>{Object.entries(scan.action_counts ?? {}).filter(([key]) => !["no_change","not_proposed"].includes(key)).reduce((sum,[,n])=>sum+n,0)}</td><td><span className="pill neutral">{titleCase(scan.realized_savings?.status || "not_verified")}</span></td></tr>)}
              </tbody></table></div>}
          </section>}

          <footer className="footer"><span>Finovaunt · Autonomous FinOps</span><span>{lastRefresh ? `Updated ${lastRefresh.toLocaleTimeString()}` : "Waiting for data"} · Refresh is read-only</span></footer>
        </div>
      </main>
    </div>
  );
}

function Metric({icon: Icon, label, value, note, tone}: {icon: typeof Gauge; label:string; value:string; note:string; tone:string}) {
  return <article className="metric-card"><div className={`metric-icon ${tone}`}><Icon size={18} /></div><span className="metric-label">{label}</span><strong className="metric-value">{value}</strong><span className="metric-note">{note}</span></article>;
}
function PanelHeading({eyebrow,title,icon:Icon,action}: {eyebrow:string; title:string; icon:typeof Gauge; action?:ReactNode}) {
  return <div className="panel-heading"><div className="panel-heading-icon"><Icon size={17}/></div><div className="panel-title"><span className="eyebrow">{eyebrow}</span><h2>{title}</h2></div>{action && <div className="panel-action">{action}</div>}</div>;
}
function OpportunityTable({rows}: {rows:Resource[]}) {
  if (!rows.length) return <EmptyState text="No optimization opportunities are present in this snapshot." />;
  return <div className="table-scroll"><table><thead><tr><th>Resource</th><th>Recommendation</th><th>Risk / confidence</th><th>Potential / month</th><th>Evidence</th></tr></thead><tbody>
    {rows.map((item) => <tr key={`${item.provider}:${item.resource_id}`}><td><strong>{item.name}</strong><small className="subline">{item.resource_type} · {item.region}</small></td><td><span className="pill blue">{titleCase(item.recommendation?.action)}</span><small className="subline rationale">{item.recommendation?.rationale || "No rationale supplied."}</small></td><td><span className={`pill ${riskTone(item.recommendation?.risk)}`}>{titleCase(item.recommendation?.risk)} risk</span><small className="subline">Confidence: {titleCase(item.recommendation?.optimization_confidence)}</small></td><td><strong>{money(item.savings?.estimated_monthly_usd)}</strong><small className="subline">{item.savings?.classification === "simulated_estimate" ? "Simulated estimate" : item.savings?.classification === "estimated_from_monthly_resource_cost" ? "Resource cost evidence" : "Not estimable"}</small></td><td>{(item.recommendation?.missing_evidence?.length ?? 0) > 0 ? <span className="pill amber">{item.recommendation?.missing_evidence?.length} gaps</span> : <span className="pill green">Evidence reviewed</span>}{item.recommendation?.requires_human_approval && <small className="subline">Human approval required</small>}</td></tr>)}
  </tbody></table></div>;
}
function Search({value,onChange,placeholder}: {value:string; onChange:(value:string)=>void; placeholder:string}) {
  return <div className="search-row"><input value={value} onChange={(event)=>onChange(event.target.value)} placeholder={placeholder} aria-label={placeholder}/><span>{value ? "Filtered results" : "All current results"}</span></div>;
}
function EmptyState({text}: {text:string}) {
  return <div className="empty-state"><div className="empty-symbol"><Cloud size={20}/></div><p>{text}</p></div>;
}
function riskTone(risk?:string) {
  const normalized = (risk || "").toLowerCase();
  if (normalized.includes("high") || normalized.includes("critical")) return "red";
  if (normalized.includes("medium") || normalized.includes("moderate")) return "amber";
  if (normalized.includes("low")) return "green";
  return "neutral";
}
