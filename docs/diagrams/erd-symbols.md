# Crow's foot symbols

From the [README](../../README.md#102-reading-the-diagrams). GitHub draws this diagram from the source below: use its controls to zoom and pan. The README shows the same diagram as an image, [docs/images/diagrams/erd-symbols.png](../images/diagrams/erd-symbols.png).

```mermaid
erDiagram
    A ||--o{ B : "zero or many"
    C ||--|{ D : "one or many"
    E |o--o{ F : "optional parent"
    G ||--o| H : "zero or one"
    I ||..o{ J : "logical link"
```
