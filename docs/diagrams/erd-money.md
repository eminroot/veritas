# Entity relationships: money

From the [README](../../README.md#104-each-area-in-full). GitHub draws this diagram from the source below: use its controls to zoom and pan. The README shows the same diagram as an image, [docs/images/diagrams/erd-money.png](../images/diagrams/erd-money.png).

```mermaid
erDiagram
    donations {
        uuid id PK
        uuid project_id FK
        uuid user_id FK "empty for a guest"
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
        text holder "donor key"
        bytea leaf_hash UK
        bigint amount_qapik
        bigint batch_id FK
    }
    batches {
        bigint id PK "batch number"
        bytea root
        bigint total_qapik
        text status
        bigint outbox_id FK
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
        integer approval_round
        text status
    }
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
        text kind "payout, refund"
        bigint amount_qapik
        text status
    }
    claims {
        uuid id PK
        uuid project_id FK
        uuid user_id FK
        text action "refund, redirect"
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
    donations ||--|{ allocations : "split into"
    batches |o--o{ allocations : "anchors"
    batches ||--o{ batch_leaves : "holds"
    allocations ||--o| batch_leaves : "placed as"
    pledges ||--o{ pledge_charges : "charged as"
    pledge_charges |o--o{ donations : "becomes"
    receipts ||..o{ allocations : "project_id + holder"
    releases ||..o| payouts : "instruction_id"
    claims ||..o{ payouts : "claim_id, for a refund"
```
