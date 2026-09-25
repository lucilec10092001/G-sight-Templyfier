# Templyfier v56

## Simpler public journey

- Removed the old-template mimic mode from the interface. The current workflow now always starts with G-Sight outputs and the required CMR export.
- Kept the calculation engine and existing Excel safeguards unchanged.

## Split traceability

- Added a visible **G-Sight source** column beside each proposed split name.
- The source shows the uploaded filename and, for a workbook containing several result sheets, the detected worksheet.
- Added a session-state migration so a browser session opened on v55 can continue safely on v56.

## Metrics before detailed review

- Moved the question-type metric recipe into the main journey, before the question table.
- The recipe applies to every compatible question of the selected type and leaves questions without a complete safe match unchanged.
- Kept the detailed question-specific metric assistant under **Advanced metric settings**.
- Made **Metrics shown in Excel** editable per question with exact source-metric validation.

## Useful multi-selection

- Clarified what the **Select** column does.
- Added bulk changes for variable/item name, group, section, stage, included splits and metrics, as well as Keep, Exclude and KPI Summary.
- Bulk metrics use the existing safe code-aware matching and fail clearly rather than applying a partial recipe.
- All question-table and recipe changes remain available to Undo/Redo.
