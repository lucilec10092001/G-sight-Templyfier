# Templyfier v62

## Questions with a split name in their wording

- Fixed a false split restriction affecting questions such as `Yellow fit` when the study also contains a `YELLOW` split.
- A simple word overlap no longer pre-fills `Included splits`.
- Automatic restriction remains available for explicit audience or comparison wording such as `with Yumos Orkide`, `among Lenor users`, `chez`, `parmi` or `avec`.
- The main review table remains the final CMI control: included splits can still be adjusted manually.
- Added portable regression tests in English and French.

This prevents a selected question from silently disappearing from TOTAL or other applicable topline worksheets.
