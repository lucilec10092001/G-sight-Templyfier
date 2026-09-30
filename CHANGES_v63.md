# Templyfier v63

## No silent question omissions

- Added an independent completeness check inside Excel generation for Monadic and Paired studies.
- Every selected question is checked against every worksheet where its Split and Stage settings say it should appear.
- If no matching source rows can be written, generation stops before download and identifies the question and affected worksheet.
- Intentional exclusions configured through `Included splits` or `Stage` remain valid.
- The protection also covers consolidated multi-stage exports without confusing legitimate NEAT/WET exclusions with missing questions.

This turns a silent data-loss risk into an explicit, actionable CMI review.
