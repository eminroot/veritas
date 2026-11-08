# Entity relationships: evidence

From the [README](../../README.md#104-each-area-in-full). GitHub draws this diagram from the source below: use its controls to zoom and pan. The README shows the same diagram as an image, [docs/images/diagrams/erd-evidence.png](../images/diagrams/erd-evidence.png).

```mermaid
erDiagram
    capture_sessions {
        uuid id PK
        uuid project_id FK
        integer milestone_index
        integer attempt
        text challenge_code
        text device_address FK
        text status
    }
    evidence_items {
        uuid id PK
        uuid session_id FK
        text kind
        bytea sha256
        double latitude
        double longitude
        timestamptz captured_at
    }
    photo_hashes {
        uuid id PK
        uuid item_id FK, UK
        bytea phash
        bytea dhash
    }
    evidence_bundles {
        uuid id PK
        uuid session_id FK, UK
        uuid project_id FK
        bytea bundle_hash
        text status
        text public_cid
    }
    evidence_checks {
        uuid id PK
        uuid bundle_id FK
        integer number
        text kind
        text status
    }
    check_reports {
        uuid id PK
        uuid bundle_id FK, UK
        bytea sha256
        boolean passed
    }
    milestones ||..o{ capture_sessions : "project_id + milestone_index"
    capture_sessions ||--o{ evidence_items : "collects"
    evidence_items ||--o| photo_hashes : "fingerprinted as"
    capture_sessions ||--o| evidence_bundles : "sealed as"
    evidence_bundles ||--o{ evidence_checks : "checked by"
    evidence_bundles ||--o| check_reports : "summed up in"
```
