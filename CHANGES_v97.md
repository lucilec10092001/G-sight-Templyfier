# Changes v97

- Restored the fail-closed control for a retained question or selected metric missing from an expected worksheet. No partial workbook is offered silently.
- Source worksheet stage is now authoritative over incidental words in question IDs. A usage question such as HOW_DRY no longer becomes a DRY-stage evaluation when it belongs to OVERALL / IN USE.
- Consolidated multi-stage workbooks now receive unique reading names when several stage sheets share one split, preventing duplicate benchmark-panel crashes.
- Interrogative categorical questions such as HOW_DRY, HOW_MANY_WASHES and HOW_MUCH_PRODUCT_USED are proposed as Listing and retain their response options. True ordinal scales remain Standard.
- The qualification runner now skips unavailable historical fixtures cleanly and supports current safe gap formulas and English KPI-detail headers.

