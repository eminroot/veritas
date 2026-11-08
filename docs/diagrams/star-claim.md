# Star schema: money back after a stop

From the [README](../../README.md#113-entity-relationship-diagram). GitHub draws this diagram from the source below: use its controls to zoom and pan. The README shows the same diagram as an image, [docs/images/diagrams/star-claim.png](../images/diagrams/star-claim.png).

```mermaid
erDiagram
    dim_date {
        integer date_key PK
        date full_date UK
        text month_name
    }
    dim_donor {
        integer donor_key PK
        uuid donor_id UK
        text sign_in_method
    }
    dim_project {
        integer project_key PK
        uuid project_id UK
        text title
        text cause_name
        text region_name
    }
    fact_claim {
        uuid claim_id PK
        integer date_key FK
        integer donor_key FK
        integer project_key FK
        integer target_project_key FK
        text action
        boolean is_default
        text status
        bigint amount_qapik
    }
    dim_date ||--o{ fact_claim : "date"
    dim_donor ||--o{ fact_claim : "donor"
    dim_project ||--o{ fact_claim : "project"
    dim_project ||--o{ fact_claim : "target project"
```
