# G-Sight Templyfier v54

English interface, editable CMI proposals, optional score differences and flexible
benchmark layouts. Suitable for local review; internal production deployment
requires IT acceptance. No real credentials or consumer files are included.

## Start locally

Extract into a new folder. Run `install_and_launch.bat` for first installation,
then `launch_templyfier.bat` for later sessions. Python must already be installed.
Dependencies are pinned to the tested direct versions; IT must review them and
approve the package mirror and upgrades. Server installation is described in
`SERVER_DEPLOYMENT.md`; never expose the desktop launcher as a shared server.

## Recommended workflow

1. Upload the G-Sight DataViz exports. Confirm the detected study design and
   editable split names; confidence is shown where a check is useful.
2. Choose the benchmark layout and Mean precision. These two workbook decisions
   are kept short and visible before question review.
3. Confirm the proposed question types and metric recipes. Generate immediately
   with the safe defaults, or open optional ordering and advanced settings.
4. If needed, drag questions or selected groups into order, clean product names,
   adjust gaps or KPI options, then generate.
   Every Generate now shortcut still applies the complete readiness checks.

The sidebar links move between steps without changing choices. Search hides rows
without excluding them from the export. Undo and redo support recent changes.
Help is available on demand rather than blocking the first visit with a dialog.

## Optional gap / delta columns

The visible **Score difference columns — optional** box is outside advanced
layout options. Uncheck **Show gap / delta columns (candidate score minus benchmark
score)** when these columns are not required. Scores and benchmark-specific
significance remain available. The setting also removes the Gap column from
generated KPI Details. Monadic gaps and Paired deltas are supported.

A positive gap means a higher candidate score, not automatically a better result.
Check favourable direction for strength, bipolar and other special scales.

## Multiple benchmark layouts

**Benchmark comparisons as columns on one sheet** creates one topline worksheet
per split, with one clearly headed comparison panel for each available benchmark.
Variable and metric labels appear once on the left. Panels are side by side and
preserve their own scores, bases, significance and optional gap formulas. Product
score columns are repeated where necessary to keep each comparison independent.
This is a consolidated reading, not an exact reproduction of the raw G-Sight file.

**A separate sheet for each benchmark** creates a topline worksheet for every
available split × benchmark comparison. Existing KPI Summary options remain
independent and can create additional summary worksheets.

There is no fixed limit of two or three benchmarks. Excel's column limit still
applies; use separate sheets for very wide projects. With one benchmark both
layouts contain one reading. Automatic detection associates each export with its
G-Sight comparison code and tolerates reordered product columns when stable codes
match. Missing exports are reported, not invented. A missing source metric remains
blank in its individual panel, with an Excel comment; it is never treated as zero.

Use distinct split names in manual mode. For multiple files describing the same
split against different benchmarks, use automatic benchmark detection.

## A clearer metric workflow

The metric editor follows three explicit decisions: choose the question, start from a suggested recipe or customise it, then choose where the change applies. Each question type has a short explanation. Batch choices display the number of affected questions and require a preview before confirmation. Choose **Only this question** when unsure.

## Question types and metric recipes

- Standard: Mean, Top Box, Top 2 Boxes and Bottom 2 Boxes are proposed by default.
  Remove Mean, add Top 3 Boxes or select other available rows for the client.
- Strength: choose the appropriate intensity/JAR metrics and favourable direction.
- CATA: keep the positive response, 1-No, or both when available.
- Bipolar: retain individual scale points, box metrics, or a custom combination.
- Listing: keep response options; listing codes are not interpreted as means.
- Other: review unusual preference, compared-to-current and other question formats.

Only rows available in the exports can be selected. Missing boxes are not
calculated from respondent data. Batch recipes are previewed before confirmation;
an incomplete or ambiguous match preserves the previous recipe.

## Generic grouping and question order

The grouping assistant is not limited to Color. It looks for compatible shared
labels and question batteries across attributes, emotions, benefits and other
themes, keeping section, stage, type and response structure separate. Review the
examples, accept or reject the suggestion, and rename the shared label once.
Source identifiers, response choices, scores and user clean labels are preserved.

Select multiple questions or groups and drag a handle to the desired position.
Shift + click selects a range. Move up / Move down also move the selection while
preserving its relative order. Grouping is reversible and never merges source IDs.

## Review before delivery to a client

Check types, selected metrics, names, grouping proposals, product codes, benchmarks,
bases, missing comparisons and favourable direction. KPI review points are advice,
not statistical validation. Mixed significant directions are reported transparently.
Open the workbook in Excel to recalculate stored gap formulas and review the final
presentation. The advanced strict-template mode intentionally follows the previous
clean file's layout; the new flexible benchmark options belong to the recommended
smart workflow.

See `CHANGES_v54.md`, `VALIDATION_v54.md` and `SERVER_DEPLOYMENT.md`.

## Review shortcuts and layout previews

Use **Review only questions needing attention** to hide questions without a review
point. This never drops hidden questions from the output. **Next review question**
and **Previous review question** open the relevant question and metrics together.
**Why this question needs review** explains the proposed type and rule-based
recognition level. Confidence is not a calibrated statistical probability.
Apply edited table cells before changing filters.

The **Preview benchmark layouts** expander shows both worksheet organisations
schematically, without inventing scores. Score repetition in comparison panels
preserves the independent benchmark reading.

## French and English question wording

Reviewed French wording helps recognise standard, intensity/JAR, CATA, preference,
compared-to-current, bipolar and listing questions and some sections/order/KPIs.
French explicit aggregate labels such as Moyenne and 2 cases supérieures are
recognised separately from numbered answer choices. Original labels and IDs remain
unchanged; the application interface stays English. Unknown wording still needs
CMI review. The export's structural layout must be supported.
Controlled bilingual fixtures pass numeric/formula/fill comparisons for Monadic
and Paired processing. Equal reliability across all real French exports is not
certified: qualify representative approved exports before client delivery.
See CMI_USER_TEST_PROTOCOL.md for practical user acceptance tasks.

## A simpler everyday workflow in v54

Follow the same four steps shown in the overview and sidebar. Start with the
exports; review the questions and metrics, check comparisons, then create Excel.
Editable names lead visually before technical source identifiers. The metric
editor stays directly visible, as do benchmark layout and optional gap/delta choices.

Detailed review lists, grouping, reordering and KPI settings are collapsed by
default. Open only what you need. Closing an optional section does not reset your
choices. Configuration errors remain visible and stop export; CMI review points
are advice to consider.

The final step tells you exactly what still needs attention. If the only missing
step is your confirmation, it asks only for that. It never confirms on your behalf.
After confirmation and successful checks, a readiness message appears. Optional
sections are not bypassed checks and this is not automatic business/statistical
approval. Click Apply to commit edited table cells before changing questions.

See UX_DECISIONS.md for the design rationale and ADOPTION_GUIDE.md for a practical
internal demo and adoption plan. Real user ease has not been measured here.


## Adaptive G-Sight structure detection

Templyfier first uses the established G-Sight layouts, then automatically broadens
the search when a workbook differs. Result sheets may be renamed, the Metric table
may move within the first 100 rows and 60 columns, and the base row may sit farther
above the table. Metric/Measure/Statistics/Indicateur header variants and safe
numeric layouts without an explicit base row are supported. If no complete table
can be identified, generation stops and reports the checked sheets; it never guesses
values or produces a partial workbook silently.

## Add a category-specific CLT stage

In Step 0, keep the detected stages and use **Add another stage** when the study
uses different moments or conditions. Enter the wording found in the questions,
for example `After application`, `Rinse` or `Skin dry-down`, then click **Add
stage**. Templyfier recognises that wording in question IDs, labels and sections
and shows the number of matching questions next to each stage.
Place the stage in the desired block order before confirming the study setup.

All validated result sheets are read before the question review. A stage found in
a G-Sight sheet header is preserved even when its name is unfamiliar. Questions
without a reliable stage remain visible as **Unassigned**. In Step 2, open
**Optional - review or change stage mapping** to assign or rename any question
with a free-text category-specific stage. A missing stage never removes a question.

## Initial shared-server scope

This release processes the current project only. Drafts, saved profiles, portable
settings and persistent client memory are not shown in the CMI interface. Upload
the current source files, review the detected structure and download the generated
Excel workbook.
