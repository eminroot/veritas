# Entity relationships: organisations, and who checks them

From the [README](../../README.md#104-each-area-in-full). GitHub draws this diagram from the source below: use its controls to zoom and pan. The README shows the same diagram as an image, [docs/images/diagrams/erd-organisations.png](../images/diagrams/erd-organisations.png).

```mermaid
erDiagram
    charities {
        uuid id PK
        text voen UK
        text legal_name
        text status
        text signer_address UK
        uuid created_by FK
        uuid verified_by FK
    }
    charity_members {
        uuid id PK
        uuid charity_id FK
        uuid user_id FK
        text role
    }
    contractors {
        uuid id PK
        uuid charity_id FK
        text voen
        text iban
        text status
        text registry_status
    }
    officers {
        uuid id PK
        text address UK
        uuid user_id FK, UK
        text status
    }
    kyb_documents {
        uuid id PK
        text owner_type
        uuid owner_id
        text kind
        bytea sha256
    }
    users ||--o{ charities : "created"
    users ||--o{ charity_members : "is"
    charities ||--o{ charity_members : "has"
    charities ||--o{ contractors : "registers"
    users |o--o| officers : "account of"
    charities ||..o{ kyb_documents : "owner_type = charity"
    contractors ||..o{ kyb_documents : "owner_type = contractor"
```
