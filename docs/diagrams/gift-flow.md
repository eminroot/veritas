# One gift, start to finish

From the [README](../../README.md#53-behind-the-screens-one-gift-start-to-finish). GitHub draws this diagram from the source below: use its controls to zoom and pan. The README shows the same diagram as an image, [docs/images/diagrams/gift-flow.png](../images/diagrams/gift-flow.png).

```mermaid
flowchart LR
    classDef person fill:#FFF4D6,stroke:#B7791F,color:#3D2A00
    classDef step fill:#E6FFFA,stroke:#2C7A7B,color:#0B3B3B
    classDef money fill:#E8F1FF,stroke:#2B6CB0,color:#0B2545

    subgraph IN["Money in"]
        direction TB
        A["👤 Aysel gives ₼50"]:::person --> B["1 · Card payment<br/>signed webhook"]:::step
        B --> C["2 · Split by milestone<br/>one Merkle leaf each"]:::step
        C --> D["3 · Hourly batch<br/>bank signs,<br/>chain anchors"]:::money
        D --> E["4 · In escrow<br/>receipt token"]:::money
    end
    subgraph PROOF["Proof and decision"]
        direction TB
        F["5 · Evidence on site<br/>GPS, time,<br/>one-time code"]:::step --> G["6 · 11 checks<br/>report hash on-chain"]:::step
        G --> H["7 · Officer signs<br/>approve or reject"]:::step
        H --> I["8 · Donors vote<br/>72 hours"]:::step
    end
    subgraph OUT["Money out"]
        direction TB
        J["9 · Release<br/>to the payout vault"]:::money --> K["10 · Bank pays<br/>the contractor"]:::money
        K --> L["11 · Daily check<br/>bank = chain<br/>= ledger"]:::step
    end
    IN --> PROOF --> OUT
```
