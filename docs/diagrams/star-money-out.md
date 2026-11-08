# Star schema: money out

From the [README](../../README.md#113-entity-relationship-diagram). GitHub draws this diagram from the source below: use its controls to zoom and pan. The README shows the same diagram as an image, [docs/images/diagrams/star-money-out.png](../images/diagrams/star-money-out.png).

```mermaid
erDiagram
    dim_date {
        integer date_key PK
        date full_date UK
        text month_name
    }
    dim_project {
        integer project_key PK
        uuid project_id UK
        text title
        text cause_name
        text region_name
    }
    dim_milestone {
        integer milestone_key PK
        uuid milestone_id UK
        smallint milestone_number
        text status
    }
    fact_release {
        uuid release_id PK
        integer released_date_key FK
        integer paid_date_key FK
        integer project_key FK
        integer milestone_key FK
        smallint attempt
        text approved_by
        bigint released_qapik
        numeric days_evidence_to_paid
    }
    dim_date ||--o{ fact_release : "released on"
    dim_date ||--o{ fact_release : "paid on"
    dim_project ||--o{ fact_release : "project"
    dim_milestone ||--o{ fact_release : "milestone"
```
