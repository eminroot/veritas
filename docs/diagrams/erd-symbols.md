# Crow's foot symbols

From the [README](../../README.md#102-reading-the-diagrams). GitHub draws this diagram from the source below: use its controls to zoom and pan. The README shows the same diagram as an image, [docs/images/diagrams/erd-symbols.png](../images/diagrams/erd-symbols.png).

```mermaid
erDiagram
    A ||--o{ B : "one A has zero or many B"
    C ||--|{ D : "one C has one or many D"
    E |o--o{ F : "an F has zero or one E"
    G ||--o| H : "one G has zero or one H"
    I ||..o{ J : "logical link, no foreign key"
```
