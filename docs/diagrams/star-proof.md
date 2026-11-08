# Star schema: proof and decisions

From the [README](../../README.md#113-entity-relationship-diagram). GitHub draws this diagram from the source below: use its controls to zoom and pan. The README shows the same diagram as an image, [docs/images/diagrams/star-proof.png](../images/diagrams/star-proof.png).

```mermaid
erDiagram
    fact_evidence_check {
        uuid bundle_id PK
        smallint check_number PK
        integer date_key FK
        integer project_key FK
        integer milestone_key FK
        smallint attempt
        text check_name
        text check_kind
        text result
        boolean is_passed
    }
    fact_ballot {
        text ballot_id PK
        integer end_date_key FK
        integer project_key FK
        integer milestone_key FK
        text ballot_kind
        smallint round
        integer eligible_count
        integer yes_count
        integer no_count
        boolean is_passed
        boolean is_turnout_fallback
    }
    dim_date ||--o{ fact_evidence_check : "date"
    dim_project ||--o{ fact_evidence_check : "project"
    dim_milestone ||--o{ fact_evidence_check : "milestone"
    dim_date ||--o{ fact_ballot : "ends on"
    dim_project ||--o{ fact_ballot : "project"
    dim_milestone ||--o{ fact_ballot : "milestone"
```
