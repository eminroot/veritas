# Entity relationships: the main entities

From the [README](../../README.md#103-the-main-entities). GitHub draws this diagram from the source below: use its controls to zoom and pan. The README shows the same diagram as an image, [docs/images/diagrams/erd-overview.png](../images/diagrams/erd-overview.png).

```mermaid
erDiagram
    users }o--o{ charities : "work in"
    charities ||--o{ contractors : "registers"
    charities ||--o{ projects : "runs"
    projects ||--|{ milestones : "split into"
    projects ||--o{ donations : "receives"
    users |o--o{ donations : "gives"
    milestones ||..o{ evidence_bundles : "proven by"
    officers ||--o{ officer_decisions : "signs"
    milestones ||..o{ officer_decisions : "decided by"
    milestones ||..o{ ballots : "voted on"
    milestones ||..o{ releases : "paid by"
```
