# The database's five areas

From the [README](../../README.md#103-the-whole-database-at-a-glance). GitHub draws this diagram from the source below: use its controls to zoom and pan. The README shows the same diagram as an image, [docs/images/diagrams/database-areas.png](../images/diagrams/database-areas.png).

```mermaid
flowchart TB
    classDef area fill:#F8FAFC,stroke:#475569,color:#0F172A,stroke-width:1.5px
    ACC["Accounts and organisations<br/>11 tables<br/>users, charities, contractors, officers"]:::area
    PRJ["Projects<br/>5 tables<br/>projects, passports, milestones"]:::area
    MON["Money<br/>11 tables<br/>donations, allocations, batches,<br/>receipts, releases, payouts, claims"]:::area
    EVD["Evidence and decisions<br/>9 tables<br/>capture_sessions, evidence_bundles,<br/>officer_decisions, ballots, votes"]:::area
    CHN["Talking to the blockchain<br/>5 tables<br/>chain_outbox, chain_events"]:::area

    ACC -- "an organisation runs projects<br/>charity_id" --> PRJ
    PRJ -- "a project receives money<br/>project_id" --> MON
    PRJ -- "each milestone needs proof<br/>project_id + milestone_index" --> EVD
    ACC -- "officers sign decisions<br/>officer_id" --> EVD
    EVD -- "an approved milestone<br/>is released" --> MON
    MON -- "on-chain calls<br/>outbox_id" --> CHN
    EVD -- "on-chain calls<br/>outbox_id" --> CHN
```
