# Use cases: donors

From the [README](../../README.md#6-use-case-diagram). GitHub draws this diagram from the source below: use its controls to zoom and pan. The README shows the same diagram as an image, [docs/images/diagrams/use-cases-donors.png](../images/diagrams/use-cases-donors.png).

```mermaid
flowchart LR
    classDef actor fill:#FFF4D6,stroke:#B7791F,color:#3D2A00,stroke-width:1.5px
    classDef uc fill:#E8F1FF,stroke:#2B6CB0,color:#0B2545
    classDef shared fill:#E6FFFA,stroke:#2C7A7B,color:#0B3B3B
    classDef system fill:#EFE9FF,stroke:#6B46C1,color:#22104A,stroke-width:1.5px

    donor["👤 Donor"]:::actor
    subgraph veritas["Veritas"]
        u1(["UC1 Browse causes,<br/>projects and the map"]):::uc
        u2(["UC2 Sign up and sign in"]):::uc
        u3(["UC3 Give by card"]):::uc
        u4(["UC4 Pledge: pay on proof"]):::uc
        u5(["UC5 Track every gift"]):::uc
        u6(["UC6 Vote on a milestone"]):::uc
        u7(["UC7 Refund or move<br/>after a stop"]):::uc
        u15(["UC15 Record on-chain"]):::shared
    end
    card["💳 Card provider"]:::system
    chain["⛓️ Blockchain"]:::system

    donor --- u1 & u2 & u3 & u5 & u6
    u4 -. "«extend»" .-> u3
    u7 -. "«extend»" .-> u5
    u3 -. "«include»" .-> u15
    u6 -. "«include»" .-> u15
    u3 --- card
    u4 --- card
    u15 --- chain
```
