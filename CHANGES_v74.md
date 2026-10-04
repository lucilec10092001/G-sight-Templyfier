# Templyfier v74

## Silent production safeguards

- Exact duplicate CMR catalogue rows are safely deduplicated.
- Conflicting reuse of a CMR code or Fr-Land ID is blocked before matching.
- Equal-confidence matches to several CMR rows are blocked instead of resolved by row order.
- G-Sight product-code and product-name vectors must have identical lengths.
- Duplicate final Excel product name/subtitle pairs are blocked.
- Empty topline readings are blocked before workbook download.
- Null bases block generation; unusually different or unreadable bases are reported in the existing file audit.

## Professional error handling

- Unexpected exceptions are no longer exposed as technical stack traces to CMIs.
- A deterministic support code is shown only when an error occurs.
- The support code contains no study values and allows the owner to identify the failed phase.
- Products that cannot be matched safely to the CMR use their G-Sight names and trigger one concise warning.

No new mandatory screen or decision was added.
