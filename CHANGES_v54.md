# Changes - Templyfier v54

- Fixed consolidated multi-stage G-Sight exports: every validated result sheet is
  now included in question detection instead of analysing only the primary sheet.
- Questions exclusive to NEAT, WET, DRY or another stage remain available in the
  question review and are written to their corresponding Excel stage output.
- Added a regression test covering one workbook with separate NEAT and WET sheets,
  distinct questions and successful Excel generation for both stages.
- Preserves unfamiliar source stages such as PRE-WASH and exposes an optional
  per-question stage-mapping table. CMIs can type any custom stage or use
  semicolon-separated mappings.
- Questions with no reliable stage are shown as Unassigned and remain included;
  stage recognition is never used as a reason to discard a question.
