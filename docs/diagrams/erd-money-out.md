# Entity relationships: money out, and the daily check

From the [README](../../README.md#104-each-area-in-full). GitHub draws this diagram from the source below: use its controls to zoom and pan. The README shows the same diagram as an image, [docs/images/diagrams/erd-money-out.png](../images/diagrams/erd-money-out.png).

```mermaid
erDiagram
    releases {
        uuid id PK
        uuid project_id FK
        integer milestone_index
        bigint amount_qapik
        bigint instruction_id UK
    }
    payouts {
        uuid id PK
        bigint instruction_id UK
        uuid project_id FK
        text kind
        bigint amount_qapik
        text status
    }
    claims {
        uuid id PK
        uuid project_id FK
        uuid user_id FK
        text action
        uuid target_project_id FK
        bigint amount_qapik
    }
    reconciliations {
        uuid id PK
        bigint day UK
        bigint chain_supply_qapik
        bigint ledger_qapik
        bigint bank_balance_qapik
        boolean balanced
    }
    projects ||--o{ releases : "releases"
    projects ||--o{ payouts : "pays out"
    projects ||--o{ claims : "after a stop"
    releases ||..o| payouts : "instruction_id"
    claims ||..o{ payouts : "claim_id, for a refund"
```
