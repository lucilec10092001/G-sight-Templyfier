# v84 - Compact and full DataViz compatibility

- Reads metric rows whose question identifier is intentionally blank because G-Sight displays it only on the first row of a block.
- Intensity blocks containing Too Strong, Just about right and Too Weak are now detected as Strength questions.
- Supports pair-suffixed product codes such as `K1M1` when the CMR contains the base code `K1M`.
- Allows one CMR product to represent several Paired positions when each position has independent reliable matching evidence.
- Copies screener styles through workbook-safe public style components, preventing Excel-generation failures caused by workbook-local style indexes.
- Keeps compatibility with both the compact 9-question intensity export and the full 88-question DataViz export.

