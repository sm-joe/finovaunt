import { useMemo, useState } from "react";
import { ArrowRight, ChartNoAxesCombined, Database, HardDrive, Layers3, PackageSearch, Target, Wallet } from "lucide-react";
import type { FinOpsAssessment } from "./FinopsEvidence";

export type Cost = {service: string; amount: number; currency: string};
export type BillingInfo = {total_cost: number; currency: string; period_start: string; scanned_at: string; services: Cost[]};
export type BillingPoint = {id: string; period_start: string; scanned_at: string; total_cost: number; currency: string};
export type CandidateInfo = {resource_id: string; name: string; region: string; reason: string; risk: string; confidence: string; estimated_monthly_savings: string | null; kubernetes?: {status: string}};
export type InventoryInfo = {asset_count: number; truncated: boolean; observed_total?: number; assets?: Array<{id: string;type: string}>};
type Props = {
  billing: BillingInfo | null; history: BillingPoint[]; inventory: InventoryInfo | null;
  candidates: CandidateInfo[]; finops: FinOpsAssessment | null;
  potentialStorageSavings: string | null; reviewedCount: number;
  collectionSettings?: React.ReactNode;
  onNavigate: (tab: "Cost Breakdown" | "AWS FinOps" | "Assets" | "Review Candidates") => void;
};

const currency = (value?: number | string | null, code = "USD") => {
  if (value == null || value === "") return "Not available";
  const n = Number(value);
  if (!Number.isFinite(n)) return "Not available";
  try { return new Intl.NumberFormat("en-US", {style:"currency",currency:code,maximumFractionDigits:2}).format(n); }
  catch { return n.toLocaleString("en-US", {maximumFractionDigits:2}) + " " + code; }
};
const shortAmount = (n: number, code: string) => {
  if (!Number.isFinite(n)) return "—";
  return new Intl.NumberFormat("en-US",{style:"currency",currency:code,notation:"compact",maximumFractionDigits:1}).format(n);
};
const count = (n: number | undefined) => n == null ? "—" : new Intl.NumberFormat("en-US").format(n);
type CostGroup = {name: string; cost_exact: string};
type AllocationRow = {groups?: CostGroup[]; currency?: string; status?: string};
type AllocEvidence = {allocation?: Record<string, AllocationRow>};
type EksEvidence = {clusters?: Array<{name: string;namespace_usage?:{status:string;namespaces?:Array<{namespace:string;cpu_millicores_sampled:string;memory_mib_sampled:string;pods_sampled:number}>}}>};
type S3Evidence = {buckets?: Array<{name:string;storage_bytes?:number|null}>;observed_buckets?:number};
type BudgetEvidence = {budgets?: Array<{name:string;type?:string;limit_exact?:string;actual_exact?:string;unit?:string}>};
type RightsizingEvidence = {findings?: Array<{resource_id:string;type:string;status:string;current_size?:string;reason?:string;estimated_monthly_savings_usd?:string|null}>};

function Card({title,icon:Icon,onClick,children,small=false}: {title:string;icon?: typeof Wallet;onClick?:()=>void;children:React.ReactNode;small?:boolean}) {
  return <section className={"fv-card" + (small ? " fv-card-small" : "")}>
    <div className="fv-card-head"><h2>{Icon && <Icon size={17} aria-hidden="true"/>}{title}</h2>
      {onClick && <button type="button" className="fv-inline-link" onClick={onClick} aria-label={`View details for ${title}`}>View details <ArrowRight size={14}/></button>}
    </div>{children}
  </section>;
}
function InlineEmpty({children}:{children:React.ReactNode}) {
  return <p className="fv-empty"><PackageSearch size={19} aria-hidden="true"/>{children}</p>;
}
function SpendTrend({billing,history}:{billing:BillingInfo|null;history:BillingPoint[]}) {
  const points = useMemo(()=>{
    const latest = new Map<string,BillingPoint>();
    for(const h of history) {
      if (!h.period_start || !Number.isFinite(h.total_cost)) continue;
      const current=latest.get(h.period_start);
      if (!current || h.scanned_at > current.scanned_at) latest.set(h.period_start,h);
    }
    return [...latest.values()].sort((a,b)=>a.period_start.localeCompare(b.period_start)).slice(-6);
  },[history]);
  if(!points.length || !billing) return <InlineEmpty>Collect billing to see monthly spend.</InlineEmpty>;
  const max=Math.max(...points.map(x=>x.total_cost),1)*1.18;
  const w=640,h=242,left=64,right=22,top=20,bottom=48,plotH=h-top-bottom;
  const gap=(w-left-right)/points.length;
  const barWidth=Math.min(66,gap*.5);
  const cc=billing.currency||"USD";
  return <div className="fv-trend">
    {points.length > 1 && <svg viewBox={`0 0 ${w} ${h}`} role="img" aria-label="Latest month-to-date Cost Explorer snapshot for each month" preserveAspectRatio="xMidYMid meet">
      {[0,.25,.5,.75,1].map(t=><g key={t}>
        <line x1={left} y1={top+plotH*(1-t)} x2={w-right} y2={top+plotH*(1-t)} stroke="var(--line)" strokeWidth="1"/>
        <text x={left-12} y={top+plotH*(1-t)+4} fill="var(--muted)" fontSize="11" textAnchor="end">{shortAmount(max*t,cc)}</text>
      </g>)}
      {points.map((point,i)=>{
        const bh=Math.max(0,Math.min(plotH,point.total_cost/max*plotH));
        const x=left+gap*(i+.5);
        const label=new Date(point.period_start+"T00:00:00Z").toLocaleDateString("en-US",{month:"short",year:"2-digit",timeZone:"UTC"});
        return <g key={point.id}>
          <rect x={x-barWidth/2} y={top+plotH-bh} width={barWidth} height={bh} rx="6" fill={i===points.length-1?"var(--accent)":"var(--chart-muted)"}/>
          <text x={x} y={Math.max(14,top+plotH-bh-8)} fontSize="11" fill="var(--ink)" fontWeight="650" textAnchor="middle">{shortAmount(point.total_cost,cc)}</text>
          <text x={x} y={h-20} fontSize="12" fill="var(--muted)" textAnchor="middle">{label}</text>
        </g>;
      })}
    </svg>}
    <div className="fv-chart-values">
      <p className="fv-footnote">Latest month-to-date snapshot for each month.</p>
      <div className="fv-table-wrap">
        <table aria-label="Observed month-to-date spend by month">
          <caption>Monthly spend values</caption>
          <thead><tr><th scope="col">Month</th><th scope="col">Observed spend</th></tr></thead>
          <tbody>{points.map(point => <tr key={point.id}>
            <td>{new Date(point.period_start + "T00:00:00Z").toLocaleDateString("en-US", { month: "short", year: "numeric", timeZone: "UTC" })}</td>
            <td>{currency(point.total_cost, point.currency || cc)}</td>
          </tr>)}</tbody>
        </table>
      </div>
    </div>
  </div>;
}
function CostDrivers({billing,onNavigate}:{billing:BillingInfo|null;onNavigate:()=>void}) {
  const [search, setSearch] = useState("");
  const costs=(billing?.services||[]).filter(x=>x.service.toLowerCase().includes(search.toLowerCase())).sort((a,b)=>b.amount-a.amount).slice(0,6);
  const max=Math.max(...costs.map(x=>x.amount),1);
  return <Card title="Top cost drivers">
    {(billing?.services.length ?? 0) > 4 && <label className="fv-evidence-filter">Filter AWS services
      <input type="search" value={search} onChange={event => setSearch(event.target.value)}/>
    </label>}
    {!costs.length?<InlineEmpty>{search ? "No services match this filter." : "No service-level costs collected."}</InlineEmpty>:
    <div className="fv-driver-list">{costs.map((item,i)=><div className="fv-driver" key={item.service}>
      <span className={"fv-driver-icon fv-driver-icon-"+i}>{i<3?<Layers3 size={16}/>:<Database size={16}/>}</span>
      <div className="fv-driver-name" title={item.service}>{item.service}</div>
      <strong>{currency(item.amount,item.currency)}</strong>
      <div className="fv-driver-meter"><span style={{width:Math.max(0,item.amount/max*100)+"%"}}/></div>
    </div>)}</div>}
    {billing && <button type="button" className="fv-inline-link" onClick={onNavigate}>All service costs <ArrowRight size={14}/></button>}
  </Card>;
}
const allocationKeys=["team","project","environment","region"] as const;
function Allocation({finops}:{finops:FinOPS}) {
  const [dimension,setDimension]=useState<typeof allocationKeys[number]>("team");
  const source=finops?.sections?.cost_allocation;
  const allocations=(source?.evidence as AllocEvidence|undefined)?.allocation;
  const selected=allocations?.[dimension];
  const groups=(selected?.groups||[]).slice().sort((a,b)=>Number(b.cost_exact)-Number(a.cost_exact));
  const total=groups.reduce((sum,x)=>sum+Math.max(0,Number(x.cost_exact)||0),0);
  const colors=["var(--accent)","#8d632c","#326873","#8474a2","#a2a4b2","#a85256"];
  return <Card title="Cost Allocation" icon={ChartNoAxesCombined}>
    {source?.status === "collected" && <div className="fv-switcher" role="group" aria-label="Cost allocation dimension">{allocationKeys.map(key=>
      <button type="button" key={key} className={dimension===key?"selected":""} aria-pressed={dimension===key} onClick={()=>setDimension(key)}>{key[0].toUpperCase()+key.slice(1)}</button>
    )}</div>}
    {source?.status!=="collected" || !selected || !groups.length?<InlineEmpty>{source?.status==="not_assessed"?"Cost allocation not assessed. Check tag activation and permissions.":"Collect AWS FinOps evidence to show attributed and unallocated spend."}</InlineEmpty>:
    <div className="fv-allocation-rows">{groups.slice(0,6).map((group,i)=><div key={group.name} className="fv-allocation-row">
        <span className="fv-color-dot" style={{background:colors[i%colors.length]}}/>
        <span title={group.name}>{group.name}</span>
        <strong>{currency(group.cost_exact,selected.currency)}</strong>
        <small>{total?(Number(group.cost_exact)/total*100).toFixed(1)+"%":"—"}</small>
      </div>)}
    </div>}
    <p className="fv-footnote">Tag groups require active cost allocation tags.</p>
  </Card>;
}
type FinOPS=FinOpsAssessment|null;
function EksMini({finops}:{finops:FinOPS}) {
  const source=finops?.sections.eks;
  const eks=source?.evidence as EksEvidence|undefined;
  const clusters=eks?.clusters||[];
  const namespaces=clusters.flatMap(c=>(c.namespace_usage?.namespaces||[]).map(ns=>({...ns,cluster:c.name}))).slice(0,5);
  return <Card title="EKS Namespace Usage" icon={Layers3} small>
    {source?.status!=="collected" || namespaces.length===0?<InlineEmpty>{clusters.length?"Kubernetes metrics unavailable; EKS permissions or Metrics Server may be missing.":"No EKS namespace sample collected."}</InlineEmpty>:
      <div className="fv-table-wrap"><table className="fv-data-table"><thead><tr><th>Namespace</th><th>CPU</th><th>Memory</th><th>Pods</th></tr></thead><tbody>
        {namespaces.map(x=><tr key={x.cluster+"/"+x.namespace}><td><strong>{x.namespace}</strong><small>{x.cluster}</small></td><td>{Number(x.cpu_millicores_sampled).toLocaleString()} m</td><td>{Number(x.memory_mib_sampled).toLocaleString()} MiB</td><td>{count(x.pods_sampled)}</td></tr>)}
      </tbody></table></div>}
  </Card>;
}
function S3Mini({finops}:{finops:FinOPS}) {
  const source=finops?.sections.s3;
  const payload=source?.evidence as S3Evidence|undefined;
  const buckets=payload?.buckets||[];
  const sampled=buckets.filter(b=>typeof b.storage_bytes==="number");
  const bytes=sampled.reduce((a,b)=>a+(b.storage_bytes||0),0);
  return <Card title="S3 Storage Insights" icon={HardDrive} small>
    {source?.status !== "collected" ? <InlineEmpty>No S3 storage evidence collected.</InlineEmpty> : <>
    <div className="fv-insight-row"><span>Buckets discovered</span><strong>{source?.status==="collected"?count(payload?.observed_buckets):"—"}</strong></div>
    <div className="fv-insight-row"><span>Sampled standard storage</span><strong>{sampled.length?(bytes/(1024**3)).toFixed(2)+" GiB":"Not available"}</strong></div>
    <div className="fv-insight-row"><span>Bucket billing</span><strong className="fv-unverified">Not attributed</strong></div>
    <div className="fv-insight-row"><span>Coverage</span><strong>{source?.status==="collected"?sampled.length+" of "+buckets.length+" buckets":"Not assessed"}</strong></div>
    <p className="fv-footnote">Standard storage only.</p>
    </>}
  </Card>;
}
function BudgetMini({finops}:{finops:FinOPS}) {
  const source=finops?.sections.budgets;
  const budgets=((source?.evidence as BudgetEvidence|undefined)?.budgets||[]).slice(0,4);
  return <Card title="AWS Budgets" icon={Target} small>
    {source?.status!=="collected" || !budgets.length?<InlineEmpty>No existing AWS budget data collected.</InlineEmpty>:
      <div className="fv-budget-list">{budgets.map((b,i)=>{
        const limit=Number(b.limit_exact),used=Number(b.actual_exact);
        const ratio=Number.isFinite(limit)&&limit>0&&Number.isFinite(used)?used/limit:null;
        return <div key={b.name+i}>
          <div className="fv-budget-label"><span title={b.name}>{b.name}</span><strong>{ratio==null?"Not available":Math.round(ratio*100)+"%"}</strong></div>
          <div className="fv-meter"><i style={{width:ratio==null?"0%":Math.min(100,ratio*100)+"%",background:ratio!=null&&ratio>1?"#a85256":"var(--accent)"}}/></div>
          <small>{currency(b.actual_exact,b.unit)} / {currency(b.limit_exact,b.unit)}</small>
        </div>;
      })}</div>}
  </Card>;
}
function Recommendations({finops,candidates}:{finops:FinOPS;candidates:CandidateInfo[]}) {
  const [search, setSearch] = useState("");
  const rightsizing=((finops?.sections?.rightsizing?.evidence as RightsizingEvidence|undefined)?.findings||[]).map(f=>({
    id:f.resource_id,type:f.type,summary:f.status==="review_low_cpu"?"Investigate sustained low CPU":"Inspect missing utilization evidence",
    evidence:f.reason||f.status,risk:"High",estimate:f.estimated_monthly_savings_usd,review:"Requires investigation",
  }));
  const volumes=candidates.map(c=>({id:c.resource_id,type:"ebs",summary:"Review unattached EBS volume",evidence:c.reason,
    risk:c.risk,estimate:c.estimated_monthly_savings,review:"Manual review only"}));
  const rows=[...volumes,...rightsizing].filter(x=>(x.id+" "+x.type+" "+x.summary).toLowerCase().includes(search.toLowerCase())).slice(0,7);
  return <>

    {volumes.length + rightsizing.length > 4 && <label className="fv-evidence-filter">Filter recommendations
      <input type="search" value={search} onChange={event => setSearch(event.target.value)}/>
    </label>}
    {rows.length ? <div className="fv-table-wrap"><table className="fv-data-table fv-recommend-table">
      <thead><tr><th>Resource</th><th>Recommendation</th><th>Risk</th><th>Potential / Month</th><th>Approval</th></tr></thead>
      <tbody>{rows.map(row=><tr key={row.type+row.id}>
        <td><strong>{row.id}</strong><small>{row.type.toUpperCase()}</small></td>
        <td><strong>{row.summary}</strong><small>{row.evidence}</small></td>
        <td><span className="fv-pill fv-pill-warn">{row.risk}</span></td>
        <td>{row.estimate==null?"Not estimable":currency(row.estimate)}<small>Unverified scenario</small></td>
        <td><span className="fv-pill fv-pill-blue">{row.review}</span></td>
      </tr>)}</tbody></table></div>:
      <InlineEmpty>{search ? "No recommendations match this filter." : "No review candidates in collected evidence."}</InlineEmpty>}
  </>;
}
export default function FinovauntOverview({billing,history,inventory,candidates,finops,potentialStorageSavings,reviewedCount,onNavigate,collectionSettings}:Props) {
  const recommendations = candidates.length + ((finops?.sections?.rightsizing?.evidence as RightsizingEvidence | undefined)?.findings?.length ?? 0);
  return <div className="fv-overview">
    <div className="fv-overview-column">
      <Card title="Month-to-date spend">
        {billing && <p className="fv-spend-total">{currency(billing.total_cost, billing.currency)}
          <small>Provisional · AWS Cost Explorer</small>
        </p>}
        <SpendTrend billing={billing} history={history}/>
      </Card>
      <Card title="Optimization recommendations" onClick={() => onNavigate("Review Candidates")}>
        <p className="fv-overview-summary">
          {inventory || finops ? `${count(recommendations)} review candidate${recommendations === 1 ? "" : "s"}` : "Collect evidence to find review candidates."}
        </p>
        {potentialStorageSavings != null && <p className="fv-subheading">
          Estimated EBS storage savings: <strong>{currency(potentialStorageSavings)}</strong> per month.
        </p>}
        {reviewedCount > 0 && <p className="fv-subheading">{reviewedCount} EBS review{reviewedCount === 1 ? "" : "s"} recorded.</p>}
        {recommendations > 0 && <Recommendations finops={finops} candidates={candidates}/>}
      </Card>
      {collectionSettings}
    </div>
    <div className="fv-overview-column">
      <CostDrivers billing={billing} onNavigate={() => onNavigate("Cost Breakdown")}/>
      <Card title="Allocation, usage, and budgets" onClick={() => onNavigate("AWS FinOps")}>
        {finops ? <div className="fv-overview-evidence">
          <Allocation finops={finops}/>
          <EksMini finops={finops}/>
          <S3Mini finops={finops}/>
          <BudgetMini finops={finops}/>
        </div> : <p className="fv-overview-summary">Collect FinOps evidence to see this breakdown.</p>}
      </Card>
    </div>
    {inventory?.truncated && <p role="alert" className="fv-warning">The inventory scan was truncated. {count(inventory.asset_count)} resources were saved. Recommendations and coverage are incomplete.</p>}
  </div>;
}
