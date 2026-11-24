# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Working assumption: cloud and platform engineers investigating AWS spending and resource usage are the primary audience. FinOps practitioners also use the workspace to understand cost allocation and review optimization evidence. The relative priority of these audiences is open.

Workspace administrators sign in, rotate the bootstrap password on first use, and configure AWS account connections and collector roles.

## Product Purpose

Finovaunt is a self-hosted AWS FinOps workspace for understanding cloud spend, investigating optimization opportunities, and recording review decisions. A successful investigation lets an operator identify the account and collection scope, follow a cost or resource finding to its source evidence, and see what remains unknown before taking action.

## Positioning

Finovaunt brings AWS billing, inventory, allocation, and utilization evidence into one account-scoped workspace. Saved AWS snapshots and recorded human decisions give findings a traceable history.

## Operating Context

- An administrator connects an AWS account using its account ID, region, and existing read-only IAM role. The role's trust policy may require an External ID.
- Operators collect billing, inventory, and FinOps evidence, then inspect it in the overview, Cost Explorer, resources, recommendations, allocation and EKS, or scan history. Working assumption: investigating a cost driver and inspecting the supporting evidence is the priority workflow.
- Changing a collector role or region requires a documented reason. Earlier snapshots remain historical evidence, and the revised configuration needs a fresh collection.

## Capabilities and Constraints

- Dashboard collection uses read-only AWS access. Review decisions record human judgment. Any privileged non-production execution belongs to the separate opt-in CLI.
- Cost Explorer shows provisional month-to-date AWS charges. EBS scenario estimates describe potential storage savings. Realized savings require post-change evidence.
- Inventory covers EC2, RDS, and EBS. FinOps evidence can include allocation tags, utilization findings, S3 storage, EKS usage, and existing AWS Budgets. EKS usage and S3 storage observations alone do not establish attributed cost.
- Label evidence gaps explicitly, including unavailable billing, uncollected inventory, incomplete or truncated scans, and estimates that have insufficient evidence.

## Brand Commitments

Use the product name Finovaunt. Keep the workspace minimalist, easy to scan, and consistent from sign-in through the dashboard and admin settings.

## Evidence on Hand

The [README](README.md) documents supported workflows and collection limits. [AWS FinOps Scope](docs/AWS_FINOPS_SCOPE.md) details coverage and milestone gaps. In the workspace, financial and resource claims come from the selected account's saved AWS evidence.

## Product Principles

- Keep account, region, and collection date visible where they affect interpretation.
- Make it easy to move from an overview to the evidence behind a finding.
- Distinguish observed charges, modeled savings, verified outcomes, and unavailable values.
- Make manual review decisions and collection history easy to trace.
