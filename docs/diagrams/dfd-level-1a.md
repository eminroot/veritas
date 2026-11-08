# Data flow, level 1a: setting up, and money in

From the [README](../../README.md#83-level-1a-setting-up-and-money-in). GitHub draws this diagram from the source below: use its controls to zoom and pan. The README shows the same diagram as an image, [docs/images/diagrams/dfd-level-1a.png](../images/diagrams/dfd-level-1a.png).

```mermaid
flowchart TB
    classDef ext fill:#FFF4D6,stroke:#B7791F,color:#3D2A00
    classDef proc fill:#E6FFFA,stroke:#2C7A7B,color:#0B3B3B,stroke-width:2px
    classDef store fill:#F1F5F9,stroke:#475569,color:#0F172A

    donor["Donor"]:::ext
    org["Organisation admin"]:::ext
    admin["Veritas admin"]:::ext
    card["Card provider"]:::ext
    bank["Partner bank"]:::ext
    chain["Blockchain"]:::ext

    p1(["1.0 Manage accounts"]):::proc
    p2(["2.0 Verify organisations"]):::proc
    p3(["3.0 Publish the Passport"]):::proc
    p4(["4.0 Take a donation"]):::proc
    p5(["5.0 Batch and anchor, hourly"]):::proc
    p11(["11.0 Relay and index"]):::proc

    d1[("D1 Accounts")]:::store
    d2[("D2 Organisations")]:::store
    d3[("D3 Projects")]:::store
    d4[("D4 Money")]:::store
    d7[("D7 Chain")]:::store
    d8[("D8 Private files")]:::store

    donor -- "email and password,<br/>or Google token" --> p1
    p1 -- "session" --> donor
    p1 <--> d1
    org -- "details, documents" --> p2
    p2 -- "documents" --> d8
    admin -- "verify or reject" --> p2
    p2 <--> d2
    org -- "Passport, signature" --> p3
    d2 -- "verified organisation,<br/>contractor, officer" --> p3
    p3 -- "milestones, budget,<br/>sites" --> d3
    p3 -- "launch call" --> d7
    donor -- "amount, project" --> p4
    p4 -- "payment" --> card
    card -- "signed webhook" --> p4
    d3 -- "split rule" --> p4
    p4 -- "donation, allocations" --> d4
    d4 -- "new allocations" --> p5
    p5 -- "root and totals" --> bank
    bank -- "signature" --> p5
    p5 -- "batch, anchor call" --> d7
    d7 <--> p11
    p11 <--> chain
    p11 -- "in escrow, receipts" --> d4
```
