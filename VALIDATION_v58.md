# Validation — Templyfier v58

- `py -m unittest discover -s tests -t . -p "test_*.py"`
- Result: **173 tests passed, 1 skipped**.
- Added focused tests for single-question selection, safe CATA multi-selection and incomplete-match preservation.
- Deep AppTest with real G-Sight and CMR files: no exception.
- Confirmed the selection instructions render, the old Advanced metric editor is absent and no manual `Set metrics` action remains.
