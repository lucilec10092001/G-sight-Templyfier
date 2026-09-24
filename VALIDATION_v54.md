# Validation - Templyfier v54

## Multi-stage regression

The new synthetic fixture contains one consolidated G-Sight workbook with two
validated result sheets: NEAT and WET. Each stage contains a distinct question.
Inspection detects both stages and both questions. Generation creates both stage
worksheets and writes all eight requested metric rows.

Additional fixtures verify that an unfamiliar PRE-WASH header is preserved and
that a question with no recognisable stage remains in the generated workbook as
Unassigned. Manual free-text stage mappings are used by grouping and ordering.

## Automated suite

`py -m unittest`

- 169 tests run
- 169 passed
- 1 historical real-fixture module skipped because its complete fixture set is
  not present in this workspace
