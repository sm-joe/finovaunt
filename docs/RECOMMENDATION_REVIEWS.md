# Human Recommendation Review Workflow

Finovaunt records human decisions separately from cloud scanning and Terraform proposal execution. A reviewer signed into the dashboard can open **Opportunities**, select a resource from the latest evidence-backed run, choose **Approve for Human-Managed Proposal** or **Reject**, and enter a review note.

Each review records the run ID, resource ID, decision, note, reviewer, timestamp, and `infrastructure_applied=false`. The backend validates that the resource is an opportunity in the current scan before recording a decision. Stale-run submissions return HTTP 409.

Approval means **review approval only**. The API does not apply Terraform, create an AWS resource, or grant AWS write permissions. Operational changes must be proposed, reviewed, and deployed separately. Do not report realized savings until independent post-change evidence supports them.

The current local-first control plane retains the most recent 1,000 review records. For enterprise deployments, use durable transactional storage, independent audit-log retention, and role-based permissions before allowing multiple reviewers to share an instance.
