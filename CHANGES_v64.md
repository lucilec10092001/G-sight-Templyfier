# Templyfier v64

## Metric-level completeness protection

- The generation safety gate now checks every explicitly selected metric for every expected question and worksheet.
- Generation stops before download when a question is present but one of its selected metrics cannot be written.
- The message identifies the question, worksheet and missing metric so the CMI can correct the source or selection.
- The existing question-level, Split and Stage checks remain active for Monadic and Paired studies.
- Side-by-side benchmark panels keep their intentional documented blanks when a metric exists in one reading only; these remain listed in the generation report rather than being mistaken for silent data loss.

The protection stays out of the interface when the project is complete and only appears when it prevents an unsafe output.
