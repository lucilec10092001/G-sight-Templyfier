# Interface design decisions — Templyfier v53

The goal is confidence and clarity for people with different levels of computer
experience. Age is not used as a proxy for ability. This is a reviewed design,
not a claim of perfect usability or guaranteed company recognition.

| Decision | Intended benefit | Safeguard |
| --- | --- | --- |
| Same four steps in overview, sidebar and content | Predictable path and orientation | Navigation does not commit or discard edits |
| Questions and metrics before optional refinements | Everyday tasks are easier to find | All existing options remain available |
| Editable names before technical IDs | Less scanning to rename labels | Source IDs and model rows are unchanged |
| Collapsed memory, grouping, ordering and KPI settings | Lower initial visual density | Widgets remain mounted; applied choices persist |
| Detailed advice collapsed, blockers visible | Advice feels distinct from errors | Actual configuration blockers still prevent export |
| Benchmark layout and gaps remain visible | Client requirements are easy to adjust | Benchmark-specific significance is preserved |
| Next-action guidance beside generation | Explains why the action is unavailable | Uses current readiness conditions; never auto-confirms |
| Native controls, readable text and larger action targets | Familiar interaction and easier clicking | Keyboard controls and existing table editing retained |

The tool still needs CMI judgement. Applied settings, unapplied table cells,
profiles, client habits and drafts are distinct concepts; guidance explains their
purpose rather than pretending they are interchangeable. No option is hidden
through permissions changes or conditional widget removal.

## Pending usability acceptance

Use the included CMI protocol with people of varied computer experience. Observe
whether they can upload, find review points, edit and Apply, find an optional
setting, choose benchmark/gap layout, resume a draft and generate without help.
Record wrong turns and confusion, not just satisfaction. Check real desktop
screens and keyboard use. Fix repeated failures and repeat the tasks.
