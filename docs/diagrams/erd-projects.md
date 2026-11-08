# Entity relationships: projects and their promises

From the [README](../../README.md#104-each-area-in-full). GitHub draws this diagram from the source below: use its controls to zoom and pan. The README shows the same diagram as an image, [docs/images/diagrams/erd-projects.png](../images/diagrams/erd-projects.png).

```mermaid
erDiagram
    projects {
        uuid id PK
        uuid charity_id FK
        text status
        text category
        bigint total_qapik
        text escrow_address
    }
    passports {
        uuid id PK
        uuid project_id FK
        integer version
        text status
        bytea sha256
        text cid
    }
    milestones {
        uuid id PK
        uuid project_id FK
        integer index
        bigint amount_qapik
        text status
        bigint funded_qapik
    }
    budget_lines {
        uuid id PK
        uuid milestone_id FK
        text item
        bigint amount_qapik
    }
    sites {
        uuid id PK
        uuid milestone_id FK
        geography geom
    }
    charities ||--o{ projects : "runs"
    projects ||--o{ passports : "versions"
    projects ||--o{ milestones : "split into"
    milestones ||--o{ budget_lines : "costed by"
    milestones ||--o{ sites : "happens at"
```
