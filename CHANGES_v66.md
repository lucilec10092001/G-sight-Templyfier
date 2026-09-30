# Templyfier v66

## Safe gap and delta formulas

- Monadic gaps and Paired deltas are calculated only when both compared cells contain numeric scores.
- If either the candidate or benchmark score is blank, the comparison cell remains blank.
- Missing data can therefore no longer look like a real zero difference in the final Excel file.
- The rule also applies to multi-benchmark layouts and the legacy calculation path.

This protects interpretation when G-Sight contains an unavailable score, an unevaluated product or an incomplete base.
