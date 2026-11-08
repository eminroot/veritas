# Star schema: one star, high level

From the [README](../../README.md#113-entity-relationship-diagram). GitHub draws this diagram from the source below: use its controls to zoom and pan. The README shows the same diagram as an image, [docs/images/diagrams/star-schema.png](../images/diagrams/star-schema.png).

```mermaid
erDiagram
    dim_date {
        integer date_key PK
    }
    dim_donor {
        integer donor_key PK
    }
    dim_project {
        integer project_key PK
    }
    dim_milestone {
        integer milestone_key PK
    }
    fact_donation {
        uuid allocation_id PK
        integer date_key FK
        integer donor_key FK
        integer project_key FK
        integer milestone_key FK
        bigint amount_qapik
    }
    dim_date ||--o{ fact_donation : "day received"
    dim_donor ||--o{ fact_donation : "who gave"
    dim_project ||--o{ fact_donation : "which project"
    dim_milestone ||--o{ fact_donation : "which milestone"
```
