# Star schema: money

From the [README](../../README.md#113-entity-relationship-diagram). GitHub draws this diagram from the source below: use its controls to zoom and pan. The README shows the same diagram as an image, [docs/images/diagrams/star-money.png](../images/diagrams/star-money.png).

```mermaid
erDiagram
    dim_date {
        integer date_key PK
        date full_date UK
        smallint year
        smallint quarter
        smallint month
        text month_name
        smallint iso_week
        smallint day_of_week
        text day_name
        boolean is_weekend
    }
    dim_donor {
        integer donor_key PK
        uuid donor_id UK
        text sign_in_method
        date joined_date
        boolean is_guest
    }
    dim_project {
        integer project_key PK
        uuid project_id UK
        text title
        text status
        bigint goal_qapik
        smallint milestone_count
        date published_date
        uuid organisation_id
        text organisation_name
        text organisation_voen
        text contractor_name
        text contractor_voen
        text cause_code
        text cause_name
        text passport_category
        text region_code
        text region_name
        text country
        boolean is_abroad
        text escrow_address
    }
    dim_milestone {
        integer milestone_key PK
        uuid milestone_id UK
        smallint milestone_number
        text title
        bigint budget_qapik
        date window_opens
        date window_closes
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
    dim_date ||--o{ fact_donation : "date"
    dim_donor ||--o{ fact_donation : "donor"
    dim_project ||--o{ fact_donation : "project"
    dim_milestone ||--o{ fact_donation : "milestone"
    dim_date ||--o{ fact_release : "released on"
    dim_date ||--o{ fact_release : "paid on"
    dim_project ||--o{ fact_release : "project"
    dim_milestone ||--o{ fact_release : "milestone"
    dim_date ||--o{ fact_claim : "date"
    dim_donor ||--o{ fact_claim : "donor"
    dim_project ||--o{ fact_claim : "project"
    dim_project ||--o{ fact_claim : "target project"
```
