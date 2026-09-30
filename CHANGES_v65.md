# Templyfier v65

## Stage mapping cannot hide source data

- A question with real source rows is always written, even when its manually assigned stage name differs from the source stage label.
- Stage settings are now used to decide whether an absent question is expected, never to discard a question that is demonstrably present.
- `WET` and `DAMP WET` are treated as safe aliases by the completeness check.
- Custom stages remain supported without weakening the question- and metric-level generation gates.

This prevents spelling, category vocabulary or manual stage mapping from creating a false omission.
