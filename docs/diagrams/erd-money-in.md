# Entity relationships: money in

From the [README](../../README.md#104-each-area-in-full). GitHub draws this diagram from the source below: use its controls to zoom and pan. The README shows the same diagram as an image, [docs/images/diagrams/erd-money-in.png](../images/diagrams/erd-money-in.png).

```mermaid
erDiagram
    donations {
        uuid id PK
        uuid project_id FK
        uuid user_id FK
        text provider_payment_id UK
        text kind
        bigint amount_qapik
        uuid pledge_charge_id FK
    }
    allocations {
        uuid id PK
        uuid donation_id FK
        uuid project_id FK
        integer milestone_index
        text holder
        bytea leaf_hash UK
        bigint amount_qapik
        bigint batch_id FK
    }
    batches {
        bigint id PK
        bytea root
        bigint total_qapik
        text status
    }
    batch_leaves {
        uuid allocation_id PK, FK
        bigint batch_id FK
        integer tree_index
        jsonb proof
    }
    receipts {
        uuid id PK
        uuid project_id FK
        text holder
        text token_id UK
    }
    pledges {
        uuid id PK
        uuid user_id FK
        uuid project_id FK
        bigint amount_qapik
        text status
    }
    pledge_charges {
        uuid id PK
        uuid pledge_id FK
        integer milestone_index
        text status
    }
    donations ||--|{ allocations : "split into"
    allocations ||--o| batch_leaves : "placed as"
    allocations }o--o| batches : "anchored in"
    batch_leaves }o--|| batches : "held in"
    pledges ||--o{ pledge_charges : "charged as"
    pledge_charges |o--o{ donations : "becomes"
    receipts ||..o{ allocations : "project_id + holder"
```
