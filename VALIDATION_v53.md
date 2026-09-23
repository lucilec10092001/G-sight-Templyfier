# Validation - Templyfier v53

Qualification performed on 23 September 2026 on Windows with Python 3.13,
Streamlit 1.62.0, openpyxl 3.1.5 and pandas 2.3.3.

## Evidence rerun for this release

- `py -m unittest`: 165 tests passed and one historical real-fixture suite was
  skipped because its complete 45/48-file reference set is not in this workspace.
- A fresh nine-check Streamlit release journey passed: progressive gates,
  type-level metrics, no persistence controls, enabled Generate now after Step 2,
  collapsed optional tools, compatibility status, Excel summary and no app exception.
- Separate journey-gating checks also passed, including the rule that question
  reordering does not send the user back to metric review.
- Packaging compiled all 42 Python files, compared every archived byte with its
  source, checked required launch/configuration files and excluded spreadsheets,
  databases, logs, secrets and temporary data.

## Output behaviours covered by automated tests

- Monadic and Paired calculations, selected metrics, renamed labels and source IDs.
- Two, three and four benchmarks; combined and separate worksheet layouts.
- Multiple splits, split/benchmark reconciliation and duplicate-reading rejection.
- Optional gap/delta columns, formula references, number formats and significance fills.
- Missing metrics remain blank rather than becoming invented zeroes.
- Standard, Strength, CATA, Listing, Bipolar, Preference and project-specific recipes.
- French aggregate aliases and controlled French/English numeric, formula and fill parity.
- WET/NEAT/DRY plus category-specific stages, ordering and grouping separation.
- Grouping, undo/redo, multi-question ordering and preservation of unedited questions.
- Adaptive result-table discovery across renamed worksheets, headers moved as far
  as row 100 or column 60, extended base-row spacing and exports without a base row.
- Metric, Metrics, Measure, Statistics and Indicateur header variants.

## Safety behaviour

Generation remains blocked for missing comparisons, invalid product plans, duplicate
manual split names, empty retained metric selections, invalid question filters,
missing product labels or unresolved input-audit blockers. Ambiguous split filters
are marked for review and are never silently treated as TOTAL. Missing scores and
gaps are never fabricated.

## Honest limits

This is ready for a controlled internal pilot, not a guarantee for every future
G-Sight export. The full historical 45/48-file regression set was unavailable in
this workspace. Desktop Excel recalculation, production server load/security and
real CMI usability have not been certified here. French wording is supported by
reviewed rules and controlled fixtures, but a new client scale may still require
CMI review. The initial shared-server UI has no drafts or persistent memory.

Streamlit AppTest emits a Windows temporary-directory cleanup warning after its
successful assertions in this sandbox; the release assertions completed and the
process exit status was checked.
