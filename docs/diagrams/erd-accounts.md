# Entity relationships: accounts and organisations

From the [README](../../README.md#104-each-area-in-full). GitHub draws this diagram from the source below: use its controls to zoom and pan. The README shows the same diagram as an image, [docs/images/diagrams/erd-accounts.png](../images/diagrams/erd-accounts.png).

```mermaid
erDiagram
    users {
        uuid id PK
        text email UK "lower case"
        text phone UK "+994..."
        text password_hash "scrypt, or empty"
        text firebase_uid UK "Google"
        boolean is_admin
    }
    sessions {
        uuid id PK
        uuid user_id FK
        bytea token_hash UK
        uuid device_id FK
        timestamptz expires_at
    }
    password_resets {
        uuid id PK
        uuid user_id FK
        bytea token_hash UK
        timestamptz expires_at
    }
    login_codes {
        uuid id PK
        text phone
        bytea code_hmac
        integer attempts
    }
    devices {
        uuid id PK
        uuid user_id FK
        text address UK "phone key"
        text platform
    }
    device_challenges {
        uuid id PK
        uuid user_id FK
        uuid charity_id FK
        text purpose
    }
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
        text role "admin, field_worker"
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
        text address UK "signing key"
        uuid user_id FK, UK
        text status
    }
    kyb_documents {
        uuid id PK
        text owner_type "charity, contractor"
        uuid owner_id
        text kind
        bytea sha256
    }
    users ||--o{ sessions : "signs in with"
    users ||--o{ password_resets : "asks for"
    users ||--o{ devices : "registers"
    devices |o--o{ sessions : "opened from"
    users ||--o{ device_challenges : "answers"
    charities |o--o{ device_challenges : "key for"
    users ||--o{ charity_members : "is"
    charities ||--o{ charity_members : "has"
    charities ||--o{ contractors : "registers"
    users |o--o| officers : "account of"
    users ||--o{ charities : "created"
    charities ||..o{ kyb_documents : "owner_type = charity"
    contractors ||..o{ kyb_documents : "owner_type = contractor"
```
