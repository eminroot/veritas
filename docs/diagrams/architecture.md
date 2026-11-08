# Architecture, high level

From the [README](../../README.md#7-architecture). GitHub draws this diagram from the source below: use its controls to zoom and pan. The README shows the same diagram as an image, [docs/images/diagrams/architecture.png](../images/diagrams/architecture.png).

```mermaid
flowchart TB
    classDef people fill:#FFF4D6,stroke:#B7791F,color:#3D2A00
    classDef app fill:#E8F1FF,stroke:#2B6CB0,color:#0B2545
    classDef worker fill:#E6FFFA,stroke:#2C7A7B,color:#0B3B3B
    classDef store fill:#F1F5F9,stroke:#475569,color:#0F172A
    classDef outside fill:#EFE9FF,stroke:#6B46C1,color:#22104A

    U["👤 Donors, organisations,<br/>officers, admins"]:::people
    W["Web app"]:::app
    FB["Firebase<br/>Google sign-in"]:::outside
    API["Veritas API"]:::app
    AI["🤖 OpenAI<br/>the assistant's model"]:::outside
    DB[("Database<br/>and private files")]:::store
    WK["Workers<br/>checks, batches, votes,<br/>payouts, chain sync"]:::worker
    PAY["💳 Card provider<br/>🏦 partner bank"]:::outside
    PUB[("⛓️ Public record<br/>Polygon contracts, IPFS")]:::outside

    U --> W --> API
    W -.-> FB
    API --> AI
    API <-->|"card payments"| PAY
    API <--> DB
    DB <--> WK
    WK <-->|"bank instructions"| PAY
    WK <--> PUB
```
