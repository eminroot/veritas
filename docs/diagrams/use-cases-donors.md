# Use cases: donors

From the [README](../../README.md#6-use-case-diagram). GitHub draws this diagram from the source below: use its controls to zoom and pan. The README shows the same diagram as an image, [docs/images/diagrams/use-cases-donors.png](../images/diagrams/use-cases-donors.png).

```mermaid
%%{init: {"flowchart": {"rankSpacing": 40, "nodeSpacing": 28}}}%%
flowchart LR
    classDef actor fill:#FFF4D6,stroke:#B7791F,color:#3D2A00,stroke-width:1.5px
    classDef uc fill:#E8F1FF,stroke:#2B6CB0,color:#0B2545
    classDef shared fill:#E6FFFA,stroke:#2C7A7B,color:#0B3B3B
    classDef system fill:#EFE9FF,stroke:#6B46C1,color:#22104A,stroke-width:1.5px

    donor["👤 Donor"]:::actor
    subgraph veritas["Veritas"]
        u1(["UC1 Browse projects,<br/>ask the assistant"]):::uc
        u2(["UC2 Give: by card<br/>or pay on proof"]):::uc
        u3(["UC3 Track the money<br/>and vote"]):::uc
        u4(["UC4 Refund or move<br/>if a project stops"]):::uc
    end
    ai["🤖 OpenAI"]:::system
    pay["💳 Card provider<br/>and bank"]:::system
    chain["⛓️ Blockchain"]:::system

    donor --- u1 & u2 & u3 & u4
    u1 --- ai
    u2 --- pay
    u4 --- pay
    u2 --- chain
    u3 --- chain
```
