# Validation - Templyfier v63

- Added a regression test that inserts a selected question absent from its expected WET source table.
- Confirmed generation is blocked with the question ID, label and affected worksheet in the message.
- Confirmed valid multi-stage NEAT/WET questions still generate normally.
- Confirmed explicit Split and Stage exclusions are not treated as omissions.
- Full automated suite with supplied real fixtures: **181 tests run — 180 passed, 1 skipped**.
