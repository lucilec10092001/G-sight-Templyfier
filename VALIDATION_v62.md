# Validation - Templyfier v62

- Reproduced the issue on the six real Comfort Yellow result exports.
- Before the correction, `Q-09-Yellow fit` was automatically restricted to the `YELLOW` split.
- After the correction, `Included splits` defaults to all splits and Yellow Fit is written to COMFORT, LENOR, TOTAL, 18-40 YO, 41+ YO and YELLOW.
- Generated all six topline worksheets in memory with zero skipped questions.
- Added three regression tests covering the accidental overlap, an explicit English comparison and explicit French audience wording.
- Full automated suite with the supplied real fixtures: **180 tests run — 179 passed, 1 skipped**.
