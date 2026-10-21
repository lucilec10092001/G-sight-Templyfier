# Templyfier v87

- Recognises additional G-Sight metric aliases such as Average, AVG, T1B, T2B, T3B, B1B and B2B.
- Treats classical scales containing a Mean as Standard even when the export does not provide box rows.
- Project-specific questions with valid source results can no longer receive an empty default recipe: source metrics are preserved for review.
- Extends explicit CMR benchmark recognition to Control, Reference, Market product and Competitor labels at safe matching confidence.
- When neither G-Sight nor the CMR exposes a reliable benchmark marker, the interface proposes the first product and asks for one editable confirmation instead of blocking the study.
- The metric recipe editor opens on the most common detected question type and uses a quiet caption for types absent from the study.

