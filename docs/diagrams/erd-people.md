# Entity relationships: people, and how they sign in

From the [README](../../README.md#104-each-area-in-full). GitHub draws this diagram from the source below: use its controls to zoom and pan. The README shows the same diagram as an image, [docs/images/diagrams/erd-people.png](../images/diagrams/erd-people.png).

```mermaid
erDiagram
    users {
        uuid id PK
        text email UK
        text phone UK
        text password_hash
        text firebase_uid UK
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
        text address UK
        text platform
    }
    device_challenges {
        uuid id PK
        uuid user_id FK
        uuid charity_id FK
        text purpose
    }
    users ||--o{ sessions : "signs in with"
    users ||--o{ password_resets : "asks for"
    users ||--o{ devices : "registers"
    devices |o--o{ sessions : "opened from"
    users ||--o{ device_challenges : "answers"
```
