# Entity relationships: talking to the blockchain

From the [README](../../README.md#104-each-area-in-full). GitHub draws this diagram from the source below: use its controls to zoom and pan. The README shows the same diagram as an image, [docs/images/diagrams/erd-chain.png](../images/diagrams/erd-chain.png).

```mermaid
erDiagram
    chain_outbox {
        bigint id PK
        text kind
        text dedupe_key UK
        text function
        jsonb args
        text status
        bigint depends_on FK
        bytea tx_hash
    }
    chain_events {
        bigint id PK
        bigint block_number
        integer log_index
        text event
        jsonb args
        uuid project_id FK
    }
    chain_contracts {
        text address PK
        text contract
        uuid project_id FK
        bigint from_block
    }
    chain_cursor {
        text name PK
        bigint block_number
    }
    alerts {
        uuid id PK
        text severity
        text kind
        text dedupe_key UK
    }
    chain_outbox |o--o{ chain_outbox : "waits for"
    projects |o--o{ chain_outbox : "about"
    projects |o--o{ chain_events : "emitted by its escrow"
    projects |o--o{ chain_contracts : "its escrow"
```
