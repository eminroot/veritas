# Architecture

From the [README](../../README.md#7-architecture). GitHub draws this diagram from the source below: use its controls to zoom and pan. The README shows the same diagram as an image, [docs/images/diagrams/architecture.png](../images/diagrams/architecture.png).

```mermaid
flowchart TB
    classDef people fill:#FFF4D6,stroke:#B7791F,color:#3D2A00
    classDef app fill:#E8F1FF,stroke:#2B6CB0,color:#0B2545
    classDef worker fill:#E6FFFA,stroke:#2C7A7B,color:#0B3B3B
    classDef store fill:#F1F5F9,stroke:#475569,color:#0F172A
    classDef outside fill:#EFE9FF,stroke:#6B46C1,color:#22104A

    U["👤 Donors, organisations,<br/>officers, admins"]:::people
    F["👤 Field worker's phone"]:::people
    W["Web app<br/>React + TypeScript"]:::app
    FB["Firebase Auth<br/>Google sign-in only"]:::outside
    API["Veritas API<br/>FastAPI, 94 endpoints"]:::app
    CARD["💳 Card provider"]:::outside
    DB[("PostgreSQL 17 + PostGIS<br/>41 tables")]:::store
    S3[("Private files")]:::store
    WK["Workers<br/>11 evidence checks,<br/>hourly batch, votes,<br/>payouts, daily check"]:::worker
    RI["Relayer and indexer<br/>send transactions,<br/>read final blocks"]:::worker
    BANK["🏦 Partner bank"]:::outside
    IPFS[("IPFS<br/>public copies")]:::outside
    CH["⛓️ Contracts on Polygon<br/>escrow, ledger, receipts,<br/>voting, payout vault"]:::outside

    U --> W
    W -. "Google button" .-> FB
    W --> API
    F --> API
    CARD -- "signed webhooks" --> API
    API <--> DB
    API --> S3
    DB <--> WK
    DB <--> RI
    WK <-- "signed instructions<br/>and confirmations" --> BANK
    WK --> IPFS
    RI <--> CH
```
