# Validation — Templyfier v55

## Automated calculation and regression suite

`py -m unittest -v`

- 170 tests run
- 170 passed
- 1 historical real-fixture module skipped because its complete fixture set is not present in this workspace

The new regression verifies `Search: S-15-Fabcon brand MO: Lenor` → `LENOR`. Existing multi-stage, three-benchmark, four-benchmark, split consolidation, metric, grouping, memory, draft, server-storage and Excel-generation tests remain green.

## Streamlit journey check

A Streamlit AppTest loaded a real DataViz example and a real CMR example with the journey gates bypassed only for automated navigation.

- no uncaught Streamlit exception;
- required upload labels displayed;
- setup controls displayed;
- question summary and filters displayed;
- Generate now reached with the full readiness logic still active.

The known Windows AppTest temporary-directory cleanup warning occurs after successful execution and does not affect the application.

## Manual visual check

The local v55 start screen was loaded in the in-app browser. The main content begins with `Select your study files`; the old route overview and file-selection explanation are absent. The legacy strict-template option is isolated in the sidebar.
