# Data flow, level 1c: when a project stops, and the daily check

From the [README](../../README.md#85-level-1c-when-a-project-stops-and-the-daily-check). GitHub draws this diagram from the source below: use its controls to zoom and pan. The README shows the same diagram as an image, [docs/images/diagrams/dfd-level-1c.png](../images/diagrams/dfd-level-1c.png).

```mermaid
flowchart TB
    classDef ext fill:#FFF4D6,stroke:#B7791F,color:#3D2A00
    classDef proc fill:#E6FFFA,stroke:#2C7A7B,color:#0B3B3B,stroke-width:2px
    classDef store fill:#F1F5F9,stroke:#475569,color:#0F172A

    org["Organisation admin"]:::ext
    officer["Verification Officer"]:::ext
    donor["Donor"]:::ext
    bank["Partner bank"]:::ext

    p9(["9.0 Stop: refund or move"]):::proc
    p10(["10.0 Reconcile, daily"]):::proc

    d4[("D4 Money")]:::store
    d6[("D6 Decisions")]:::store
    d7[("D7 Chain")]:::store

    org -- "withdrawal, signed" --> p9
    officer -- "stop proposal,<br/>then a donor vote" --> p9
    donor -- "refund or move,<br/>signed" --> p9
    d4 -- "the donor's<br/>allocations" --> p9
    p9 -- "claims" --> d6
    p9 -- "refund instruction" --> bank
    p9 -- "claim calls" --> d7
    p9 -- "moved money,<br/>new allocations" --> d4
    bank -- "signed balance" --> p10
    d4 -- "ledger total" --> p10
    d7 -- "supply on-chain" --> p10
    p10 -- "reconciliation" --> d4
    p10 -- "alerts" --> d7
```
