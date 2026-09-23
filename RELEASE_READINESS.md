# Templyfier v53 - sharing readiness

## Decision

**Recommended status: controlled internal pilot.** The tool has enough automated
evidence and blocking safeguards to be shared with a small CMI group on approved
projects. It should not yet be presented as universally certified for every future
G-Sight structure.

## Why this recommendation is reasonable

- 165 automated tests passed; one unavailable historical fixture suite is disclosed.
- Nine current-journey Streamlit release checks passed.
- The release archive compiles all Python sources, contains no spreadsheets or
  secrets and is byte-checked against the source folder.
- Tests cover Monadic, Paired, CLT stages, multiple splits, up to four benchmarks,
  both benchmark layouts, gaps on/off, metric recipes, formulas and significance.
- Adaptive importer tests cover moved tables, renamed sheets, header aliases,
  distant or absent base rows, invalid preferred sheets and fail-closed diagnostics.
- Blockers stop generation when the input plan or retained question configuration
  is objectively incomplete. Missing values are not replaced with invented scores.

## Conditions for confident wider sharing

Use dual CMI review for the first three real projects. For each project, open the
workbook in desktop Excel, recalculate and compare representative scores, bases,
significance fills, labels, splits and gaps with G-Sight. Record only metadata and
the pass/fail outcome. Any unexplained difference pauses the pilot until the case is
reproduced and added to the regression suite.

## Known boundaries

- New or structurally changed G-Sight exports may still require review.
- Real production-server security, concurrency and restart behaviour require IT.
- The current interface keeps no draft or persistent project memory.
- Usability has automated coverage but still needs observation with real CMIs.

This status gives colleagues a safe, reviewable starting point without making a
claim that the evidence does not support.
