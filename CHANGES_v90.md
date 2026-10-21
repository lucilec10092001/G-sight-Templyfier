# Templyfier v90

- Fixes support code `TMP-3D93EBB1E6`: an invisible U+001F control character could make openpyxl reject the entire workbook while writing the KPI Summary.
- Restores the intended Unicode KPI arrows in the deployed engine.
- Cleans Excel-forbidden control characters from copied source values, product headers, topline values, screeners and summary labels before writing them.
- Preserves tabs and line breaks that are valid in Excel.

