# Validation - Templyfier v64

- Added a regression test where a WET question exists but its selected Bottom 2 Boxes metric has no numeric source row.
- Confirmed generation is blocked with the question, worksheet and missing metric in the message.
- Confirmed valid NEAT/WET exports continue to generate.
- Confirmed multi-benchmark side-by-side alignment still permits its intentional annotated blanks.
- Full automated suite with supplied real fixtures: **182 tests run — 181 passed, 1 skipped**.
