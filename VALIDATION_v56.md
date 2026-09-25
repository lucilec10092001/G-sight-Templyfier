# Validation — Templyfier v56

## Automated checks

- `py -m unittest discover -s tests -t . -p "test_*.py"`
- Result: **173 tests passed, 1 skipped**.
- Added coverage for source-sheet traceability and direct metric-text validation.

## Streamlit checks

- Initial AppTest: no exceptions, exactly two required upload controls, no legacy-template checkbox, v56 header present.
- Deep AppTest with a real G-Sight DataViz workbook and a real CMR export: no exception and the visible **Default results by question type** section rendered.

## Regression scope

- The Excel calculation engine and writer were not rewritten.
- Existing generation readiness checks remain active.
- Existing saved row/profile structures remain compatible; the new source field has a default value.
