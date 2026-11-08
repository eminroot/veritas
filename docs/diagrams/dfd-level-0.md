# Data flow, level 0: the context

From the [README](../../README.md#82-level-0-the-context). GitHub draws this diagram from the source below: use its controls to zoom and pan. The README shows the same diagram as an image, [docs/images/diagrams/dfd-level-0.png](../images/diagrams/dfd-level-0.png).

```mermaid
flowchart LR
    classDef ext fill:#FFF4D6,stroke:#B7791F,color:#3D2A00
    classDef proc fill:#E6FFFA,stroke:#2C7A7B,color:#0B3B3B,stroke-width:2px

    donor["Donor"]:::ext
    org["Organisation"]:::ext
    field["Field worker"]:::ext
    officer["Verification Officer"]:::ext
    admin["Veritas admin"]:::ext
    V(["0<br/>Veritas"]):::proc
    card["Card provider"]:::ext
    bank["Partner bank"]:::ext
    chain["Blockchain"]:::ext
    ipfs["IPFS"]:::ext

    donor -- "card payment, votes,<br/>refund or move" --> V
    V -- "receipts, gift status,<br/>proof timeline" --> donor
    org -- "application, documents,<br/>Passport, signatures" --> V
    V -- "verification, money raised,<br/>decisions" --> org
    field -- "photos, GPS,<br/>signed manifest" --> V
    V -- "one-time code" --> field
    officer -- "signed decision" --> V
    V -- "evidence, check report" --> officer
    admin -- "verify or reject" --> V
    V -- "applications, alerts" --> admin
    V -- "charges" --> card
    card -- "signed webhooks" --> V
    V -- "payout and refund<br/>instructions" --> bank
    bank -- "signatures, balance,<br/>confirmations" --> V
    V -- "transactions" --> chain
    chain -- "events" --> V
    V -- "public copies" --> ipfs
```
