# v79 validation

- Full test suite: 205 tests run, 1 skipped, all passing.
- Reviewed with a 63-question multi-split project to confirm that Question type and Metrics are the first editable decision columns.
- Confirmed that selecting rows for bulk edits does not trigger the unsaved-change warning by itself.
- Confirmed that ordering remains available but is collapsed by default.
- No calculation, Excel-writing, CMR, split, benchmark or saved-profile logic was changed.
