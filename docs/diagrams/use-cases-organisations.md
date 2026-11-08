# Use cases: organisations, and the people who check them

From the [README](../../README.md#6-use-case-diagram). GitHub draws this diagram from the source below: use its controls to zoom and pan. The README shows the same diagram as an image, [docs/images/diagrams/use-cases-organisations.png](../images/diagrams/use-cases-organisations.png).

```mermaid
%%{init: {"flowchart": {"rankSpacing": 40, "nodeSpacing": 28}}}%%
flowchart LR
    classDef actor fill:#FFF4D6,stroke:#B7791F,color:#3D2A00,stroke-width:1.5px
    classDef uc fill:#E8F1FF,stroke:#2B6CB0,color:#0B2545
    classDef shared fill:#E6FFFA,stroke:#2C7A7B,color:#0B3B3B
    classDef system fill:#EFE9FF,stroke:#6B46C1,color:#22104A,stroke-width:1.5px

    org["👤 Organisation<br/>admins, field workers"]:::actor
    admin["👤 Veritas admin"]:::actor
    officer["👤 Verification<br/>Officer"]:::actor
    subgraph veritas["Veritas"]
        u5(["UC5 Register and<br/>get verified"]):::uc
        u6(["UC6 Publish<br/>a Passport"]):::uc
        u7(["UC7 Prove the work<br/>on site"]):::uc
        u8(["UC8 Review<br/>and decide"]):::uc
        u9(["UC9 Release<br/>and pay"]):::shared
    end
    bank["🏦 Partner bank"]:::system
    chain["⛓️ Blockchain"]:::system

    org --- u5 & u6 & u7
    admin --- u5
    officer --- u8
    u8 -. "approved" .-> u9
    u9 --- bank
    u6 --- chain
    u9 --- chain
```
