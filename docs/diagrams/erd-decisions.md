# Entity relationships: decisions

From the [README](../../README.md#104-each-area-in-full). GitHub draws this diagram from the source below: use its controls to zoom and pan. The README shows the same diagram as an image, [docs/images/diagrams/erd-decisions.png](../images/diagrams/erd-decisions.png).

```mermaid
erDiagram
    officer_decisions {
        uuid id PK
        uuid project_id FK
        uuid officer_id FK
        integer milestone_index
        boolean approve
        boolean override_checks
    }
    ballots {
        bytea id PK
        uuid project_id FK
        text kind
        integer eligible
        integer yes
        integer no
    }
    votes {
        uuid id PK
        bytea ballot_id FK
        text holder
        boolean approve
    }
    officers ||--o{ officer_decisions : "signs"
    milestones ||..o{ officer_decisions : "project_id + milestone_index"
    milestones ||..o{ ballots : "project_id + milestone_index"
    ballots ||--o{ votes : "collects"
```
