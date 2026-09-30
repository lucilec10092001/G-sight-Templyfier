# Templyfier v67

## Clear section blocks

- Questions sharing a section are now written as one contiguous block in Excel.
- The first appearance of each section defines section order.
- Question order inside each section is preserved.
- `FRAGRANCE BENEFITS` and `PRODUCT BENEFITS` can therefore no longer alternate through the worksheet with repeated headers.
- Exact row order remains available when section headers are disabled.

## Excel package integrity

- Before download, Templyfier tests the XLSX ZIP package, parses every XML relationship/document and reopens the workbook.
- A structurally invalid workbook is blocked with a clear message instead of being offered to the CMI.
