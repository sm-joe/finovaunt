import { useMemo, useState } from "react";
import { ArrowRight, BarChart3, ChartNoAxesCombined, CircleHelp, Database, HardDrive, Layers3, PackageSearch, ShieldCheck, Target, Wallet, Zap } from "lucide-react";
import type { FinOpsAssessment } from "./FinopsEvidence";

export type Cost = {service: string; amount: number; currency: string};
export type BillingInfo = {total_cost: number; currency: string; period_start: string; scanned_at: string; services: Cost[]};
export type BillingPoint = {id: string; period_start: string; scanned_at: string; total_cost: number; currency: string};
export type CandidateInfo = {resource_id: string; name: string; region: string; reason: string; risk: string; confidence: string; estimated_monthly_savings: string | null; kubernetes?: {status: string}};
export type InventoryInfo = {asset_count: number; truncated: boolean; observed_total?: number; assets?: Array<{id: string;type: string}>};
type Props = {
  billing: BillingInfo | null; history: BillingPoint[]; inventory: InventoryInfo | null;
  candidates: CandidateInfo[]; finops: FinOpsAssessment | null;
  potentialStorageSavings: string | null; reviewedCount: number; search: string;
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
type Section = {status: string; evidence?: Record<string, unknown>};
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
      {onClick && <button type="button" className="fv-inline-link" onClick={onClick}>View details <ArrowRight size={14}/></button>}
    </div>{children}
  </section>;
}
function KPI({title,value,hint,icon:Icon,tone="blue"}:{title:string;value:string;hint:string;icon:typeof Wallet;tone?:string}) {
  return <article className={"fv-kpi fv-tone-"+tone}>
    <div className="fv-kpi-head"><span>{title}</span><Icon size={19} aria-hidden="true"/></div>
    <strong title={value}>{value}</strong><small>{hint}</small>
  </article>;
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
  if(!points.length || !billing) return <InlineEmpty>Collect billing to see monthly observed spend. A forecast is not available yet.</InlineEmpty>;
  const max=Math.max(...points.map(x=>x.total_cost),1)*1.18;
  const w=640,h=242,left=64,right=22,top=20,bottom=48,plotH=h-top-bottom;
  const gap=(w-left-right)/points.length;
  const barWidth=Math.min(66,gap*.5);
  const cc=billing.currency||"USD";
  return <div className="fv-trend">
    <svg viewBox={`0 0 ${w} ${h}`} role="img" aria-label="Historical month-to-date Cost Explorer snapshots; the latest snapshot per month, not full finalized months" preserveAspectRatio="xMidYMid meet">
      {[0,.25,.5,.75,1].map(t=><g key={t}>
        <line x1={left} y1={top+plotH*(1-t)} x2={w-right} y2={top+plotH*(1-t)} stroke="#e7edf7" strokeWidth="1"/>
        <text x={left-12} y={top+plotH*(1-t)+4} fill="#8795ac" fontSize="11" textAnchor="end">{shortAmount(max*t,cc)}</text>
      </g>)}
      {points.map((point,i)=>{
        const bh=Math.max(0,Math.min(plotH,point.total_cost/max*plotH));
        const x=left+gap*(i+.5);
        const label=new Date(point.period_start+"T00:00:00Z").toLocaleDateString("en-US",{month:"short",year:"2-digit",timeZone:"UTC"});
        return <g key={point.id}>
          <rect x={x-barWidth/2} y={top+plotH-bh} width={barWidth} height={bh} rx="6" fill={i===points.length-1?"#2563eb":"#69b7ff"}/>
          <text x={x} y={Math.max(14,top+plotH-bh-8)} fontSize="11" fill="#243652" fontWeight="650" textAnchor="middle">{shortAmount(point.total_cost,cc)}</text>
          <text x={x} y={h-20} fontSize="12" fill="#72849b" textAnchor="middle">{label}</text>
        </g>;
      })}
    </svg>
    <div className="fv-legend"><span><i className="fv-legend-dot"/>Observed month-to-date</span><span>Forecast unavailable · No extrapolated amounts</span></div>
  </div>;
}
function CostDrivers({billing,search,onNavigate}:{billing:BillingInfo|null;search:string;onNavigate:()=>void}) {
  const costs=(billing?.services||[]).filter(x=>x.service.toLowerCase().includes(search.toLowerCase())).sort((a,b)=>b.amount-a.amount).slice(0,6);
  const max=Math.max(...costs.map(x=>x.amount),1);
  return <Card title="Top Cost Drivers" icon={BarChart3} onClick={onNavigate}>
    {!costs.length?<InlineEmpty>Service-level cost evidence is unavailable for this selection.</InlineEmpty>:
    <div className="fv-driver-list">{costs.map((item,i)=><div className="fv-driver" key={item.service}>
      <span className={"fv-driver-icon fv-driver-icon-"+i}>{i<3?<Layers3 size={16}/>:<Database size={16}/>}</span>
      <div className="fv-driver-name" title={item.service}>{item.service}</div>
      <strong>{currency(item.amount,item.currency)}</strong>
      <div className="fv-driver-meter"><span style={{width:Math.max(0,item.amount/max*100)+"%"}}/></div>
    </div>)}</div>}
    <p className="fv-footnote">By AWS service, not individual resource. Source: Cost Explorer.</p>
  </Card>;
}
const allocationKeys=["team","project","environment","region"] as const;
function Allocation({finops,onNavigate}:{finops:FinOPS;onNavigate:()=>void}) {
  const [dimension,setDimension]=useState<typeof allocationKeys[number]>("team");
  const source=finops?.sections?.cost_allocation;
  const allocations=(source?.evidence as AllocEvidence|undefined)?.allocation;
  const selected=allocations?.[dimension];
  const groups=(selected?.groups||[]).slice().sort((a,b)=>Number(b.cost_exact)-Number(a.cost_exact));
  const total=groups.reduce((sum,x)=>sum+Math.max(0,Number(x.cost_exact)||0),0);
  const colors=["#2563eb","#8362e7","#21c6c5","#88d17c","#aab6c9","#ffad61"];
  const stops=groups.map((g,i)=>({color:colors[i%colors.length],value:Math.max(0,Number(g.cost_exact)||0)}));
  let cursor=0;
  const gradient=stops.map(s=>{const a=cursor;cursor+=total?s.value/total*100:0;return s.color+" "+a+"% "+cursor+"%";}).join(", ");
  return <Card title="Cost Allocation" icon={ChartNoAxesCombined} onClick={onNavigate}>
    <div className="fv-switcher" role="group" aria-label="Cost allocation dimension">{allocationKeys.map(key=>
      <button type="button" key={key} className={dimension===key?"selected":""} aria-pressed={dimension===key} onClick={()=>setDimension(key)}>{key[0].toUpperCase()+key.slice(1)}</button>
    )}</div>
    {source?.status!=="collected" || !selected || !groups.length?<InlineEmpty>{source?.status==="not_assessed"?"Cost allocation not assessed. Check tag activation and permissions.":"Collect AWS FinOps evidence to show attributed and unallocated spend."}</InlineEmpty>:
    <div className="fv-allocation-body">
      <div className="fv-donut" role="img" aria-label={`Cost allocation by ${dimension}`} style={{background:`conic-gradient(${gradient})`}}>
        <div><strong>{currency(total,selected.currency)}</strong><span>Observed spend</span></div>
      </div>
      <div className="fv-allocation-rows">{groups.slice(0,6).map((group,i)=><div key={group.name} className="fv-allocation-row">
        <span className="fv-color-dot" style={{background:colors[i%colors.length]}}/>
        <span title={group.name}>{group.name}</span>
        <strong>{currency(group.cost_exact,selected.currency)}</strong>
        <small>{total?(Number(group.cost_exact)/total*100).toFixed(1)+"%":"—"}</small>
      </div>)}</div>
    </div>}
    <p className="fv-footnote">Tag groups require activated AWS cost allocation tags. Unallocated spend remains visible.</p>
  </Card>;
}
type FinOPS=FinOpsAssessment|null;
function EksMini({finops,onNavigate}:{finops:FinOPS;onNavigate:()=>void}) {
  const source=finops?.sections.eks;
  const eks=source?.evidence as EksEvidence|undefined;
  const clusters=eks?.clusters||[];
  const namespaces=clusters.flatMap(c=>(c.namespace_usage?.namespaces||[]).map(ns=>({...ns,cluster:c.name}))).slice(0,5);
  return <Card title="EKS Namespace Usage" icon={Layers3} onClick={onNavigate} small>
    <p className="fv-subheading">Measured usage, not namespace spend</p>
    {source?.status!=="collected" || namespaces.length===0?<InlineEmpty>{clusters.length?"Kubernetes metrics unavailable; EKS permissions or Metrics Server may be missing.":"No EKS namespace sample collected."}</InlineEmpty>:
      <div className="fv-table-wrap"><table className="fv-data-table"><thead><tr><th>Namespace</th><th>CPU</th><th>Memory</th><th>Pods</th></tr></thead><tbody>
        {namespaces.map(x=><tr key={x.cluster+"/"+x.namespace}><td><strong>{x.namespace}</strong><small>{x.cluster}</small></td><td>{Number(x.cpu_millicores_sampled).toLocaleString()} m</td><td>{Number(x.memory_mib_sampled).toLocaleString()} MiB</td><td>{count(x.pods_sampled)}</td></tr>)}
      </tbody></table></div>}
  </Card>;
}
function S3Mini({finops,onNavigate}:{finops:FinOPS;onNavigate:()=>void}) {
  const source=finops?.sections.s3;
  const payload=source?.evidence as S3Evidence|undefined;
  const buckets=payload?.buckets||[];
  const sampled=buckets.filter(b=>typeof b.storage_bytes==="number");
  const bytes=sampled.reduce((a,b)=>a+(b.storage_bytes||0),0);
  return <Card title="S3 Storage Insights" icon={HardDrive} onClick={onNavigate} small>
    <div className="fv-insight-row"><span>Buckets discovered</span><strong>{source?.status==="collected"?count(payload?.observed_buckets):"—"}</strong></div>
    <div className="fv-insight-row"><span>Sampled standard storage</span><strong>{sampled.length?(bytes/(1024**3)).toFixed(2)+" GiB":"Not available"}</strong></div>
    <div className="fv-insight-row"><span>Bucket billing</span><strong className="fv-unverified">Not attributed</strong></div>
    <div className="fv-insight-row"><span>Coverage</span><strong>{source?.status==="collected"?sampled.length+" of "+buckets.length+" buckets":"Not assessed"}</strong></div>
    <p className="fv-footnote">Does not include other storage classes.</p>
  </Card>;
}
function BudgetMini({finops,onNavigate}:{finops:FinOPS;onNavigate:()=>void}) {
  const source=finops?.sections.budgets;
  const budgets=((source?.evidence as BudgetEvidence|undefined)?.budgets||[]).slice(0,4);
  return <Card title="AWS Budgets" icon={Target} onClick={onNavigate} small>
    {source?.status!=="collected" || !budgets.length?<InlineEmpty>No existing AWS budget data collected.</InlineEmpty>:
      <div className="fv-budget-list">{budgets.map((b,i)=>{
        const limit=Number(b.limit_exact),used=Number(b.actual_exact);
        const ratio=Number.isFinite(limit)&&limit>0&&Number.isFinite(used)?used/limit:null;
        return <div key={b.name+i}>
          <div className="fv-budget-label"><span title={b.name}>{b.name}</span><strong>{ratio==null?"Not available":Math.round(ratio*100)+"%"}</strong></div>
          <div className="fv-meter"><i style={{width:ratio==null?"0%":Math.min(100,ratio*100)+"%",background:ratio!=null&&ratio>1?"#e45b65":"#21ac72"}}/></div>
          <small>{currency(b.actual_exact,b.unit)} / {currency(b.limit_exact,b.unit)}</small>
        </div>;
      })}</div>}
  </Card>;
}
function Recommendations({finops,candidates,search,onNavigate}:{finops:FinOPS;candidates:CandidateInfo[];search:string;onNavigate:()=>void}) {
  const rightsizing=((finops?.sections?.rightsizing?.evidence as RightsizingEvidence|undefined)?.findings||[]).map(f=>({
    id:f.resource_id,type:f.type,summary:f.status==="review_low_cpu"?"Investigate sustained low CPU":"Inspect missing utilization evidence",
    evidence:f.reason||f.status,risk:"High",estimate:f.estimated_monthly_savings_usd,review:"Requires investigation",
  }));
  const volumes=candidates.map(c=>({id:c.resource_id,type:"ebs",summary:"Review unattached EBS volume",evidence:c.reason,
    risk:c.risk,estimate:c.estimated_monthly_savings,review:"Manual review only"}));
  const rows=[...volumes,...rightsizing].filter(x=>(x.id+" "+x.type+" "+x.summary).toLowerCase().includes(search.toLowerCase())).slice(0,7);
  return <Card title="Optimization Recommendations" icon={Zap} onClick={onNavigate}>
    <p className="fv-subheading">Evidence-backed investigation queue. No automatic changes or verified realized savings.</p>
    {rows.length ? <div className="fv-table-wrap"><table className="fv-data-table fv-recommend-table">
      <thead><tr><th>Resource</th><th>Recommendation</th><th>Risk</th><th>Potential / Month</th><th>Approval</th></tr></thead>
      <tbody>{rows.map(row=><tr key={row.type+row.id}>
        <td><strong>{row.id}</strong><small>{row.type.toUpperCase()}</small></td>
        <td><strong>{row.summary}</strong><small>{row.evidence}</small></td>
        <td><span className="fv-pill fv-pill-warn">{row.risk}</span></td>
        <td>{row.estimate==null?"Not estimable":currency(row.estimate)}<small>Unverified scenario</small></td>
        <td><span className="fv-pill fv-pill-blue">{row.review}</span></td>
      </tr>)}</tbody></table></div>:
      <InlineEmpty>No review candidates have been identified in collected evidence.</InlineEmpty>}
  </Card>;
}
export default function FinovauntOverview({billing,history,inventory,candidates,finops,potentialStorageSavings,reviewedCount,search,onNavigate}:Props) {
  const allocationSection=finops?.sections.cost_allocation;
  const tagAllocation=(allocationSection?.evidence as AllocEvidence|undefined)?.allocation?.team;
  const teams=tagAllocation?.groups||[];
  const assigned=teams.filter(x=>x.name!=="Unallocated").reduce((s,x)=>s+(Number(x.cost_exact)||0),0);
  const sum=teams.reduce((s,x)=>s+(Number(x.cost_exact)||0),0);
  const coverage=sum>0?Math.round(assigned/sum*1000)/10:null;
  const rightsizing=((finops?.sections.rightsizing?.evidence as RightsizingEvidence|undefined)?.findings||[]).length;
  return <div className="fv-overview">
    <div className="fv-kpi-grid">
      <KPI title="Month-to-Date Spend" value={currency(billing?.total_cost,billing?.currency)} hint={billing?"Cost Explorer · provisional month-to-date":"Collect AWS billing to populate"} icon={Wallet}/>
      <KPI title="Spend Forecast" value="Not available" hint="Requires validated forecasting evidence" icon={ChartNoAxesCombined} tone="indigo"/>
      <KPI title="Potential Storage Savings" value={currency(potentialStorageSavings)} hint="EBS scenario only · not realized" icon={Zap} tone="violet"/>
      <KPI title="Verified Savings" value="Not verified" hint="Post-change billing evidence required" icon={ShieldCheck} tone="green"/>
      <KPI title="Team Cost Coverage" value={coverage==null?"Not assessed":coverage+"%"} hint="Share of tagged team spend" icon={Target} tone="indigo"/>
      <KPI title="Review Candidates" value={inventory||finops?count(candidates.length+rightsizing):"Not available"} hint={reviewedCount+" recorded EBS reviews"} icon={PackageSearch} tone="violet"/>
    </div>
    <div className="fv-dashboard-row fv-primary-row">
      <Card title="Organization Spend Trend" icon={BarChart3} onClick={()=>onNavigate("Cost Breakdown")}>
        <p className="fv-subheading">Latest observed month-to-date snapshot per month. Months may represent different collection dates.</p>
        <SpendTrend billing={billing} history={history}/>
      </Card>
      <CostDrivers billing={billing} search={search} onNavigate={()=>onNavigate("Cost Breakdown")}/>
    </div>
    <div className="fv-dashboard-row fv-secondary-row">
      <Allocation finops={finops} onNavigate={()=>onNavigate("AWS FinOps")}/>
      <EksMini finops={finops} onNavigate={()=>onNavigate("AWS FinOps")}/>
      <S3Mini finops={finops} onNavigate={()=>onNavigate("AWS FinOps")}/>
      <BudgetMini finops={finops} onNavigate={()=>onNavigate("AWS FinOps")}/>
    </div>
    <Recommendations finops={finops} candidates={candidates} search={search} onNavigate={()=>onNavigate("Review Candidates")}/>
    {inventory?.truncated&&<p role="alert" className="fv-warning">The inventory scan was truncated; {count(inventory.asset_count)} resources were saved. Recommendations and coverage are incomplete.</p>}
    <p className="fv-provenance"><CircleHelp size={14}/> All displayed amounts come from the selected account's persisted AWS evidence. Unavailable values are not estimated. EKS and S3 usage do not represent attributed cost.</p>
  </div>;
}
