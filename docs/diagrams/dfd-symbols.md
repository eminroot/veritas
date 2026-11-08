# Data flow diagram symbols

From the [README](../../README.md#81-reading-the-symbols). GitHub draws this diagram from the source below: use its controls to zoom and pan. The README shows the same diagram as an image, [docs/images/diagrams/dfd-symbols.png](../images/diagrams/dfd-symbols.png).

```mermaid
flowchart LR
    classDef ext fill:#FFF4D6,stroke:#B7791F,color:#3D2A00
    classDef proc fill:#E6FFFA,stroke:#2C7A7B,color:#0B3B3B,stroke-width:2px
    classDef store fill:#F1F5F9,stroke:#475569,color:#0F172A
    E["External entity"]:::ext -- "data flow: what moves" --> P(["1.0 Process"]):::proc
    P -- "data flow" --> D[("D1 Data store")]:::store
```
