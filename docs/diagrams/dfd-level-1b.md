# Data flow, level 1b: proof, decisions and money out

From the [README](../../README.md#84-level-1b-proof-decisions-and-money-out). GitHub draws this diagram from the source below: use its controls to zoom and pan. The README shows the same diagram as an image, [docs/images/diagrams/dfd-level-1b.png](../images/diagrams/dfd-level-1b.png).

```mermaid
flowchart TB
    classDef ext fill:#FFF4D6,stroke:#B7791F,color:#3D2A00
    classDef proc fill:#E6FFFA,stroke:#2C7A7B,color:#0B3B3B,stroke-width:2px
    classDef store fill:#F1F5F9,stroke:#475569,color:#0F172A

    field["Field worker"]:::ext
    org["Organisation admin"]:::ext
    officer["Verification Officer"]:::ext
    donor["Donor"]:::ext
    ipfs["IPFS"]:::ext
    bank["Partner bank"]:::ext

    p6(["6.0 Capture and check evidence"]):::proc
    p7(["7.0 Decide: officer, then donors"]):::proc
    p8(["8.0 Release and pay"]):::proc

    d3[("D3 Projects")]:::store
    d5[("D5 Evidence")]:::store
    d6[("D6 Decisions")]:::store
    d7[("D7 Chain")]:::store
    d8[("D8 Private files")]:::store

    field -- "photos, GPS,<br/>signed manifest" --> p6
    p6 -- "one-time code" --> field
    d3 -- "site, window,<br/>proof list" --> p6
    org -- "signature" --> p6
    p6 -- "originals" --> d8
    p6 <--> d5
    p6 -- "redacted copy" --> ipfs
    p6 -- "evidence and<br/>checks calls" --> d7
    d5 -- "bundle, report" --> p7
    officer -- "signed decision" --> p7
    donor -- "signed vote" --> p7
    p7 <--> d6
    p7 -- "decision and<br/>vote calls" --> d7
    d6 -- "approved milestone" --> p8
    p8 -- "instruction" --> bank
    bank -- "confirmation" --> p8
    p8 -- "release, payout" --> d6
    p8 -- "release call" --> d7
```
