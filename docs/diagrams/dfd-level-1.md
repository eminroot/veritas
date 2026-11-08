# Data flow, level 1: inside Veritas

From the [README](../../README.md#83-level-1-inside-veritas). GitHub draws this diagram from the source below: use its controls to zoom and pan. The README shows the same diagram as an image, [docs/images/diagrams/dfd-level-1.png](../images/diagrams/dfd-level-1.png).

```mermaid
flowchart LR
    classDef ext fill:#FFF4D6,stroke:#B7791F,color:#3D2A00
    classDef proc fill:#E6FFFA,stroke:#2C7A7B,color:#0B3B3B,stroke-width:2px
    classDef store fill:#F1F5F9,stroke:#475569,color:#0F172A

    org["Organisations"]:::ext
    donor["Donors"]:::ext
    check["Officers<br/>and admins"]:::ext

    p1(["1.0 Accounts<br/>and checks"]):::proc
    p2(["2.0 Projects"]):::proc
    p3(["3.0 Money in"]):::proc
    p4(["4.0 Proof and<br/>decisions"]):::proc
    p5(["5.0 Money out"]):::proc

    d1[("D1 People and<br/>organisations")]:::store
    d2[("D2 Projects")]:::store
    d3[("D3 Money")]:::store
    d4[("D4 Evidence<br/>and decisions")]:::store
    pay["Card provider<br/>and bank"]:::ext

    org -- "application" --> p1
    check -- "verify" --> p1
    org -- "Passport" --> p2
    donor -- "payment" --> p3
    org -- "evidence" --> p4
    donor -- "vote" --> p4
    check -- "decision" --> p4
    p4 -- "approved" --> p5
    p1 <--> d1
    p2 <--> d2
    p3 <--> d3
    p4 <--> d4
    p5 <--> d3
    p3 <-->|"payments"| pay
    p5 <-->|"payouts, refunds"| pay
```
