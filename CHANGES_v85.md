# v85 - Consolidated multi-split DataViz workbooks

- Recognises every valid `2_TAILED` table in one G-Sight workbook as a split when the tabs share one stage and contain distinct Search filters.
- Excludes `1_TAILED`, `2_TAILED_DELTA` and legend companion tabs.
- Removes repeated TOTAL tables with identical source values so they cannot create duplicate output sheets.
- Reads the split name after the final colon in native G-Sight Search syntax.
- Keeps distinct age definitions distinct; for example `18-30, 31-40` and `Under 18, 18-30` no longer collapse into one split.
- Uses the resolved split name consistently for question availability and Excel output.
- Preserves the existing one-file-per-split and named-sheet Paired workflows.

