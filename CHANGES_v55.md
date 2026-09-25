# Changes — Templyfier v55

## A shorter CMI journey

- The main screen now starts directly with the two required inputs: all G-Sight DataViz outputs and the matching CMR export.
- Removed the route overview, file-selection explanation, study summary cards, CLT block-design question, source-detail panel, recommendation explanation and large review-priority panel.
- The study screen keeps only high-impact choices: study format, Screeners, KPI Summary, benchmark reading, Mean decimals, gaps/deltas and editable split names.
- Benchmark identification is automatic in the standard journey. The unreliable manual selector is no longer displayed.

## One question control table

- Replaced the layered type/stage/guided reviews with one always-visible master table.
- The table edits Keep, G-Sight question, variable/item, group, section, stage, included splits, KPI Summary, KPI short label and question type while showing selected metrics and recognition status.
- Added search plus Show, Question type and Stage filters.
- Added multi-selection and bulk actions for non-adjacent questions.
- Creating a group is now as simple as giving several rows the same group name.
- Free-text stages remain editable in the same table, including category-specific stages.
- Metric recipes and question-level metric exceptions remain available under one advanced expander.

## Reliable question ordering

- Multi-select drag-and-drop remains directly below the table.
- Moves stay in the browser until Save order, preventing a full Streamlit rerun after every movement.
- Saving the order no longer triggers the previous extra rerun that sent users back through earlier screens.

## Split detection

- Native G-Sight filters use the value after the final delimiter as the proposed split name. `Search: S-15-Fabcon brand MO: Lenor` now proposes `LENOR`.
- TOTAL remains the default when no split is specified.
- Unparseable non-empty filters remain visible for manual correction and never silently become TOTAL.

The calculation engine, Excel writer, SQLite storage, SSO and saved-profile formats were not rewritten.
