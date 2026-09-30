# Validation - Templyfier v61

- Full automated suite with the supplied real fixtures: **177 tests run — 176 passed, 1 skipped**.
- Added a regression with an odd number of products and one benchmark shared by two candidates.
- Confirmed that the same file is blocked without a mapping and generates two correct pair blocks after the mapping is supplied.
- Re-tested `ALL SPLITS CLEANED UP.xlsx` read-only: detected HUT Paired, 17 splits and 105 questions.
- Generated all 17 topline worksheets in memory, with 4,777 data rows, zero skipped questions and 3 to 9 pairs per split.
- Confirmed 35,406 generated Candidate-minus-Benchmark delta formulas.
- No source workbook was modified or exported.
