# Templyfier v105 - Excel-safe KPI signals

- Fixed `IllegalCharacterError` during generation of the KPI Summary.
- Replaced deployment-sensitive triangle and mixed-result glyphs with transport-safe values: `WIN95`, `WIN90`, `LOSS90`, `LOSS95`, `MIXED`, `NA` and `=`.
- Preserved the existing green, red, amber and neutral KPI formatting.
- Replaced the KPI legend with an English ASCII-only explanation.
- The correction applies to every project using KPI Summary, not only the Nano study.
- Support diagnostic `TMP-D5607A6622` is now covered by a dedicated illegal-character regression check.

