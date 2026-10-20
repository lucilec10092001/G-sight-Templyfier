# v81 validation

- Full test suite: 207 tests run, 1 skipped, all passing.
- Regression tests confirm that a Stage edit inside selected rows is detected for propagation.
- Regression tests confirm that an edit outside the selected rows remains question-specific.
- Shared metric edits use safe response-code matching and stop without partial application when a match is unavailable.
- No calculation, Excel-writing, CMR, split or benchmark logic was changed.
