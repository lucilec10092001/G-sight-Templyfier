# Changes - Templyfier v53

## Release confidence and sharing scope

- Replaced contradictory legacy validation claims with evidence rerun for v53.
- Added a concise sharing-readiness decision and current CMI pilot protocol.
- The release is recommended for a controlled internal pilot with dual review of
  the first three real projects.
- The package states the unavailable historical fixture suite and production IT
  boundaries instead of implying universal certification.

## Reliability and journey improvements

- 165 unit tests pass; one disclosed historical real-fixture suite is unavailable.
- Nine current Streamlit journey checks pass without application exceptions.
- Generate now is enabled directly after a valid Step 2 confirmation.
- Later advanced edits still invalidate readiness and require review.
- Readiness instructions point to the correct step or advanced section.
- Custom CLT stages show matching-question counts and warn on unmatched wording.
- Stage recognition tolerates spaces, hyphens and underscores and keeps distinct
  category-specific stages separate during grouping and ordering.

## Adaptive G-Sight import

- Result sheets are selected from validated table structure, not exact names alone.
- Known layouts keep a fast path; unfamiliar layouts trigger the broader scan only
  when needed.
- Metric tables may move within the first 100 rows and 60 columns.
- Base/sample rows may be up to 12 rows above the table header.
- Exports without an explicit base row can be read when repeated numeric result
  columns provide a safe structural match.
- Invalid preferred sheets no longer hide another valid results sheet.
- Unsupported workbooks fail closed with per-sheet diagnostics and explicitly state
  that no output was generated.

## Shared-server scope

- The CMI interface processes one current project per session.
- Draft, profile and persistent-memory controls remain hidden.
- Existing calculation, Excel-writing and compatibility modules remain packaged.
- No project spreadsheets, secrets, databases or logs are included in the archive.
