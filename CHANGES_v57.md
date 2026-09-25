# Templyfier v57

## First-use clarity

- Fixed the step badges so they show 1, 2, 3 and 4 while retaining stable navigation anchors.
- Replaced the outdated tutorial with a short English guide matching the current G-Sight + required CMR journey.
- Removed obsolete tutorial references to optional CMR files, saved profiles and the former screen order.

## Calmer question table

- Added four column views: **Essentials**, **Study mapping**, **KPI Summary** and **All columns**.
- Made **Essentials** the default to reduce horizontal scrolling and visual load.
- Kept every field and bulk action available; changing views affects only presentation, never the Excel configuration.
- Made hidden-column handling defensive so saving a compact view cannot overwrite values that are not visible.

## Visual Excel preview

- Added an always-visible preview before generation.
- Lets the CMI switch between planned topline, Screener and KPI Summary worksheets.
- Shows the first 20 configured result rows with sections, final labels, product headers and delta columns.
- Uses dashes for scores so the preview communicates structure without fabricating results.
- Clearly marks the preview as preliminary while a generation safeguard is unresolved.
