# Templyfier v107

## Clearer Paired toplines

- Every comparison is now presented as an independent horizontal pair block.
- A dark `PAIR 1`, `PAIR 2`, etc. band makes the pairing immediately visible.
- The comparison name is shown directly below as `Candidate vs Benchmark`.
- Product names and source codes remain visible in the corresponding columns.
- Column roles are explicit: `Benchmark`, `Candidate` and `Gap`.
- Respondent bases are simplified to `Base: n=...` when a base can be read safely.
- Benchmark, candidate and gap headers use restrained, distinct fills.
- A narrow blank spacer remains between pairs and headers stay frozen while scrolling.
- The layout adapts to any pair count and to projects generated with or without gap columns.

## Quality control

- Added regression coverage for Paired headers with and without gaps.
- Added a multi-pair regression test for independent pair blocks and spacers.
- The complete suite passes: 239 tests, with 1 optional real-data test skipped when its fixture is unavailable.

