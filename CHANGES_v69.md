# Templyfier v69

- Recognises stage-named selected G-Sight views such as `NEAT 2_TAILED`, `WET 2_TAILED`, or custom-stage equivalents.
- Excludes companion `1_TAILED` and `DELTA` worksheets from the split plan and generation pass.
- Matches composite G-Sight product headers such as `A26 356897` to the exact CMR code as a bounded token.
- Preserves `Formula type` and `Fr-Land ID` in the CMR match result.
- Uses high-confidence CMR matches explicitly marked as benchmarks when G-Sight comparison metadata is absent.
- Keeps G-Sight comparison metadata as the first-priority benchmark source when it exists.
- Supports both side-by-side and separate-sheet benchmark layouts with this CMR fallback.

No uploaded study file is stored in the repository.
