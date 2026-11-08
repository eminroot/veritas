# Data flow, level 0: the context

From the [README](../../README.md#82-level-0-the-context). GitHub draws this diagram from the source below: use its controls to zoom and pan. The README shows the same diagram as an image, [docs/images/diagrams/dfd-level-0.png](../images/diagrams/dfd-level-0.png).

```mermaid
flowchart LR
    classDef ext fill:#FFF4D6,stroke:#B7791F,color:#3D2A00
    classDef proc fill:#E6FFFA,stroke:#2C7A7B,color:#0B3B3B,stroke-width:2px
    classDef store fill:#F1F5F9,stroke:#475569,color:#0F172A

    donor["Donors"]:::ext
    org["Organisations<br/>and field workers"]:::ext
    check["Officers<br/>and admins"]:::ext
    V(["0<br/>Veritas"]):::proc
    pay["Card provider<br/>and bank"]:::ext
    pub["Blockchain<br/>and IPFS"]:::ext
    ai["OpenAI"]:::ext

    donor -- "payments, votes,<br/>questions" --> V
    V -- "receipts, status,<br/>answers" --> donor
    org -- "applications, Passports,<br/>evidence" --> V
    V -- "verification,<br/>money raised" --> org
    check -- "verifications,<br/>decisions" --> V
    V -- "evidence to review" --> check
    V <-->|"charges, payouts,<br/>confirmations"| pay
    V <-->|"records, events"| pub
    V <-->|"question, answer"| ai
```
