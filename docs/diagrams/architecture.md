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
    subgraph SERVERS["Veritas servers"]
        W["Web app<br/>React + TypeScript"]:::app
        API["Veritas API<br/>FastAPI, 94 endpoints"]:::app
        DB[("PostgreSQL 17 + PostGIS<br/>41 tables")]:::store
        S3[("Private file storage")]:::store
        EV["Evidence worker<br/>11 checks, redaction"]:::worker
        JOBS["Jobs<br/>hourly batch, votes,<br/>payouts, reconciliation"]:::worker
        RL["Relayer<br/>sends transactions"]:::worker
        IX["Indexer<br/>reads final blocks"]:::worker
    end
    CARD["💳 Card provider"]:::outside
    BANK["🏦 Partner bank"]:::outside
    CH["⛓️ Contracts on Polygon<br/>escrow, ledger, receipts,<br/>voting, payout vault"]:::outside
    IPFS[("IPFS<br/>public copies")]:::outside
    FB["Firebase Auth<br/>Google sign-in only"]:::outside

    U --> W --> API
    F --> API
    W -.-> FB
    CARD -- "signed webhooks" --> API
    API <--> DB
    API --> S3
    EV <--> DB
    EV --> IPFS
    JOBS <--> DB
    JOBS <-->|"signed instructions<br/>and confirmations"| BANK
    DB --> RL --> CH
    CH --> IX --> DB
```
