# Use cases: organisations, and the people who check them

From the [README](../../README.md#6-use-case-diagram). GitHub draws this diagram from the source below: use its controls to zoom and pan. The README shows the same diagram as an image, [docs/images/diagrams/use-cases-organisations.png](../images/diagrams/use-cases-organisations.png).

```mermaid
%%{init: {"flowchart": {"rankSpacing": 34, "nodeSpacing": 26}}}%%
flowchart LR
    classDef actor fill:#FFF4D6,stroke:#B7791F,color:#3D2A00,stroke-width:1.5px
    classDef uc fill:#E8F1FF,stroke:#2B6CB0,color:#0B2545
    classDef shared fill:#E6FFFA,stroke:#2C7A7B,color:#0B3B3B
    classDef system fill:#EFE9FF,stroke:#6B46C1,color:#22104A,stroke-width:1.5px

    org["👤 Organisation<br/>admin"]:::actor
    field["👤 Field worker"]:::actor
    officer["👤 Verification<br/>Officer"]:::actor
    admin["👤 Veritas admin"]:::actor
    subgraph veritas["Veritas"]
        u2(["UC2 Sign up and sign in"]):::uc
        u8(["UC8 Register<br/>the organisation"]):::uc
        u9(["UC9 Publish a Passport"]):::uc
        u11(["UC11 Sign the evidence"]):::uc
        u10(["UC10 Capture<br/>evidence on site"]):::uc
        u12(["UC12 Review and decide"]):::uc
        u13(["UC13 Verify<br/>organisations,<br/>contractors, officers"]):::uc
        u14(["UC14 Release and pay"]):::shared
        u15(["UC15 Record<br/>on-chain"]):::shared
    end
    bank["🏦 Partner<br/>bank"]:::system
    chain["⛓️ Blockchain"]:::system

    org --- u2 & u8 & u9 & u11
    field --- u10
    officer --- u12
    admin --- u13
    u9 -. "«include»" .-> u15
    u11 -. "«include»" .-> u15
    u12 -. "«include»" .-> u15
    u14 -. "«include»" .-> u15
    u14 --- bank
    u15 --- chain
```
