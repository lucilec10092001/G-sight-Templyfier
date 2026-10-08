# v77 - Unicode transport hardening

- Repaired the remaining corrupted French dictionary keys used by the metric editor.
- Repaired the legacy unassigned-stage marker.
- Kept compatibility with replacement-character separators without embedding a visible corrupted glyph in the source.
- Added a regression test that rejects Unicode replacement characters in every production Python file.
