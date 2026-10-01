# Templyfier v71

- Adds `Preview generated Excel - optional` after successful generation and before download.
- Reads the actual generated workbook rather than simulating its future structure.
- Lets the CMI switch between every generated worksheet.
- Shows real values and formulas from the first 24 rows and 18 columns.
- Shows the full worksheet dimensions when the preview is truncated.
- Keeps the preview collapsed by default and leaves Download Excel immediately accessible.
- Caches the preview so switching worksheets does not regenerate or repeatedly parse the workbook.
