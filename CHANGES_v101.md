# Templyfier v101 - isolated table edits

- Editing one `Variable / item`, `Item family`, `Section header`, stage or other table cell now changes only that row.
- Removed the legacy implicit propagation that copied a renamed family or section to every row sharing an old group identifier.
- Multi-row propagation now occurs only when the CMI explicitly ticks the rows in **Edit together**.
- Item-family identity now follows the internal family identifier, not merely a matching display label and stage.
- Two different item families can therefore use the same visible label without being merged or renamed together.
- Section and family contiguity remains enforced for genuine members of the same family.

