# Star schema: money in

From the [README](../../README.md#113-entity-relationship-diagram). GitHub draws this diagram from the source below: use its controls to zoom and pan. The README shows the same diagram as an image, [docs/images/diagrams/star-donation.png](../images/diagrams/star-donation.png).

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
    dim_milestone {
        integer milestone_key PK
        uuid milestone_id UK
        smallint milestone_number
        text status
    }
    fact_donation {
        uuid allocation_id PK
        uuid donation_id
        integer date_key FK
        integer donor_key FK
        integer project_key FK
        integer milestone_key FK
        text donation_kind
        text status
        boolean is_anchored
        bigint amount_qapik
    }
    dim_date ||--o{ fact_donation : "date"
    dim_donor ||--o{ fact_donation : "donor"
    dim_project ||--o{ fact_donation : "project"
    dim_milestone ||--o{ fact_donation : "milestone"
```
