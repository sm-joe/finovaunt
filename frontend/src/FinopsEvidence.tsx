import React from "react";

export type FinOpsSection = {status: string; reason?: string; evidence?: Record<string, unknown>};
export type FinOpsAssessment = {
  id: string; scanned_at: string; status: string;
  sections: Record<string, FinOpsSection>; read_only: boolean;
};

type TagCost = {name: string; cost_exact: string};
type TagGroup = {status: string; currency: string; groups: TagCost[]; unallocated_cost_exact: string};
type AllocationEvidence = {period_start?: string; period_end_exclusive?: string; allocation?: Record<string, TagGroup>};
type RightsizingEvidence = {findings?: Array<{
  type: string; resource_id: string; current_size?: string; status: string;
  samples?: number; cpu_average_percent?: number | null; estimated_monthly_savings_usd?: number | null;
}>; observed?: {ec2_observed?: number; rds_observed?: number}; capped?: boolean};
type S3Evidence = {buckets?: Array<{
  name: string; region: string; tags?: Record<string,string>; storage_bytes?: number | null;
  storage_metrics_status?: string; cost_usd?: number | null;
}>; observed_buckets?: number; status?: string};
type EksEvidence = {clusters?: Array<{
  name: string; version?: string; status?: string; region?: string;
  namespace_costs?: null; allocation_status: string;
  namespace_usage?: {status: string; reason?: string; namespaces?: Array<{
    namespace: string; pods_sampled: number;
    cpu_millicores_sampled: string; memory_mib_sampled: string; cost_usd: null;
  }>};
}>; status?: string};
type BudgetEvidence = {budgets?: Array<{
  name: string; type?: string; unit?: string; limit_exact?: string;
  actual_exact?: string; status?: string;
}>};

const humanName: Record<string,string> = {
  cost_allocation: "Cost Allocation By Team & Project",
  rightsizing: "EC2 & RDS Optimization Reviews",
  s3: "S3 Bucket Storage",
  eks: "Amazon EKS",
  budgets: "AWS Budgets",
};
function showMoney(amount: string | number | null | undefined, currency = "USD"): string {
  if (amount == null) return "Not available";
  const value = Number(amount);
  return Number.isFinite(value) ? new Intl.NumberFormat("en-US", {
    style: "currency", currency, maximumFractionDigits: 2,
  }).format(value) : "Not available";
}
function formatBytes(value?: number | null): string {
  return value == null || !Number.isFinite(value) ? "Not available" : (value / (1024 ** 3)).toFixed(2) + " GiB";
}
function EvidenceNotice({message}: {message: string}) {
  return <p className="context-note" role="note">{message}</p>;
}
function Section({title, name, section, children}: {
  title: string; name: string; section?: FinOpsSection; children: React.ReactNode;
}) {
  return <section className="panel table-panel" style={{marginTop: 16}} aria-label={name}>
    <h3>{title}</h3>
    {!section ? <EvidenceNotice message="No collection evidence exists for this section."/> :
      section.status !== "collected" ? <p role="status">Not assessed · {section.reason || "AWS data not available."}</p> :
      children}
  </section>;
}
export default function FinopsEvidence({report}: {report: FinOpsAssessment | null}) {
  if (!report) return <div className="empty-state">No AWS FinOps assessment collected for this account configuration.</div>;
  const sections = report.sections || {};
  const allocation = sections.cost_allocation?.evidence as AllocationEvidence | undefined;
  const reviews = sections.rightsizing?.evidence as RightsizingEvidence | undefined;
  const storage = sections.s3?.evidence as S3Evidence | undefined;
  const eks = sections.eks?.evidence as EksEvidence | undefined;
  const budgets = sections.budgets?.evidence as BudgetEvidence | undefined;
  return <div aria-label="Collected AWS FinOps evidence">
    <p role="status">Collected: {new Date(report.scanned_at).toLocaleString()} · {report.status} · Read-only collection</p>
    <Section title={humanName.cost_allocation} name="cost_allocation" section={sections.cost_allocation}>
      <EvidenceNotice message="Month-to-date AWS Cost Explorer amounts. Activated cost allocation tags are required. Unallocated charges remain visible; tag totals are not per-resource costs."/>
      {(["team", "project", "environment"] as const).map(key => {
        const group = allocation?.allocation?.[key];
        return <div key={key} style={{marginTop: 18}}>
          <h4 style={{textTransform: "capitalize"}}>{key}</h4>
          {group?.groups?.length ? <div className="table-scroll"><table>
            <thead><tr><th>{key === "environment" ? "Environment" : key === "team" ? "Team" : "Project"}</th><th>Observed Spend</th></tr></thead>
            <tbody>{group.groups.map((item, i) =>
              <tr key={item.name + i}><td>{item.name}</td><td>{showMoney(item.cost_exact,group.currency)}</td></tr>)}</tbody>
          </table></div> : <EvidenceNotice message="No activated tag allocation data returned."/>}
          {group && <p className="context-note">Unallocated: {showMoney(group.unallocated_cost_exact, group.currency)}</p>}
        </div>;
      })}
    </Section>
    <Section title={humanName.rightsizing} name="rightsizing" section={sections.rightsizing}>
      <EvidenceNotice message="These are manual investigation candidates, not instance-size prescriptions or verified savings. Check memory, IO, peaks and business ownership before changing AWS resources."/>
      {reviews?.observed && <p>Observed: EC2 {reviews.observed.ec2_observed ?? "Unknown"} · RDS {reviews.observed.rds_observed ?? "Unknown"}{reviews.capped ? " · Truncated" : ""}</p>}
      {reviews?.findings?.length ? <div className="table-scroll"><table>
        <thead><tr><th>Resource</th><th>Type</th><th>Current Size</th><th>Evidence</th><th>Action</th></tr></thead>
        <tbody>{reviews.findings.map((item, i) => <tr key={item.resource_id + i}>
          <td>{item.resource_id}</td><td>{item.type.toUpperCase()}</td><td>{item.current_size || "Unknown"}</td>
          <td>{item.status} · {item.samples ?? 0} CPU samples</td><td>Human review only</td>
        </tr>)}</tbody></table></div> : <EvidenceNotice message="No actionable review candidates observed; this does not establish resource optimization."/>}
    </Section>
    <Section title={humanName.s3} name="s3" section={sections.s3}>
      <EvidenceNotice message="Daily CloudWatch StandardStorage capacity is not billed bucket cost. Other storage classes and request/transfer charges require CUR/Data Exports evidence."/>
      {storage?.buckets?.length ? <div className="table-scroll"><table>
        <thead><tr><th>Bucket</th><th>Region</th><th>Team / Project Tags</th><th>Standard Capacity</th><th>Bucket Cost</th></tr></thead>
        <tbody>{storage.buckets.map((bucket) => <tr key={bucket.name}>
          <td>{bucket.name}</td><td>{bucket.region}</td>
          <td>{bucket.tags?.Team || "Unallocated"} / {bucket.tags?.Project || "Unallocated"}</td>
          <td>{formatBytes(bucket.storage_bytes)}</td><td>Not attributed</td>
        </tr>)}</tbody></table></div> :
        <EvidenceNotice message={storage?.status === "partial" ? "Bucket inventory is partial; no complete assessment is available." : "No accessible buckets returned."}/>}
    </Section>
    <Section title={humanName.eks} name="eks" section={sections.eks}>
      <EvidenceNotice message="EKS can sample namespace CPU and memory from Kubernetes Metrics API when RBAC and Metrics Server are available. These usage observations are not attributable dollar costs."/>
      {eks?.clusters?.length ? <div className="table-scroll"><table>
        <thead><tr><th>Cluster</th><th>Region</th><th>Kubernetes Version</th><th>Status</th><th>Namespace Cost</th></tr></thead>
        <tbody>{eks.clusters.map((cluster) => <React.Fragment key={cluster.name}>
          <tr>
            <td>{cluster.name}</td><td>{cluster.region || "Unknown"}</td><td>{cluster.version || "Unknown"}</td>
            <td>{cluster.status || "Unknown"}</td><td>Not attributed</td>
          </tr>
          <tr><td colSpan={5}>
            <details>
              <summary>Namespace CPU / memory sample · {cluster.namespace_usage?.status || "Not assessed"}</summary>
              {cluster.namespace_usage?.status === "collected" && cluster.namespace_usage.namespaces?.length ?
                <div className="table-scroll"><table><thead><tr><th>Namespace</th><th>Sampled Pods</th><th>CPU (mCPU)</th><th>Memory (MiB)</th><th>Allocated Cost</th></tr></thead>
                  <tbody>{cluster.namespace_usage.namespaces.map(ns => <tr key={ns.namespace}>
                    <td>{ns.namespace}</td><td>{ns.pods_sampled}</td><td>{ns.cpu_millicores_sampled}</td>
                    <td>{ns.memory_mib_sampled}</td><td>Not attributed</td>
                  </tr>)}</tbody></table></div> :
                <p>{cluster.namespace_usage?.reason || "No namespace metrics available. Enable Kubernetes Metrics Server and allow read access."}</p>}
            </details>
          </td></tr>
        </React.Fragment>)}</tbody></table></div> : <EvidenceNotice message="No EKS clusters were returned for the selected region."/>}
    </Section>
    <Section title={humanName.budgets} name="budgets" section={sections.budgets}>
      <EvidenceNotice message="Existing AWS Budgets are displayed read-only. Finovaunt does not create budgets or send alerts."/>
      {budgets?.budgets?.length ? <div className="table-scroll"><table>
        <thead><tr><th>Budget</th><th>Type</th><th>Limit</th><th>Actual Spend</th></tr></thead>
        <tbody>{budgets.budgets.map((budget, i) => <tr key={budget.name + i}>
          <td>{budget.name}</td><td>{budget.type || "Unknown"}</td>
          <td>{showMoney(budget.limit_exact,budget.unit)}</td><td>{showMoney(budget.actual_exact,budget.unit)}</td>
        </tr>)}</tbody></table></div> : <EvidenceNotice message="No existing budgets were returned."/>}
    </Section>
  </div>;
}
