# G-Sight Templyfier v56

Templyfier turns G-Sight DataViz outputs into editable Excel toplines for consumer research studies. The interface is in English and the question detection supports English and French source wording. No consumer files or credentials are included in this repository.

## Everyday workflow

1. Select every G-Sight output for the study and the matching CMR export. The CMR is required. A study may use one G-Sight workbook containing all splits or one workbook per split.
2. Confirm the study format and the few choices that change the workbook: Screeners, KPI Summary, benchmark reading, Mean decimals, and gap/delta columns.
3. Check the proposed split names and their G-Sight source file or worksheet. Templyfier uses `TOTAL` when no split is specified and reads native G-Sight filters such as `Search: S-15-Fabcon brand MO: Lenor` as `LENOR`.
4. Choose the default result rows by question type, review every question in one table, then generate the workbook. The existing safety checks still block incomplete or inconsistent configurations.

The sidebar only shows the four landmarks. Technical details and rare options no longer interrupt the main journey.

## One question review table

The main table contains the decisions that affect Excel:

- Keep or exclude a question;
- G-Sight source question;
- variable/item name and reusable group name;
- section and free-text stage;
- included splits;
- KPI Summary and KPI short label;
- question type and the metrics shown in Excel;
- a visible `Please check` status when recognition needs a CMI decision.

Search and filters change only the view; hidden questions remain in the output. Tick `Select` on adjacent or non-adjacent rows to apply one action to several questions: keep, exclude, rename variables/items or groups, set section, stage, included splits or metrics, and add or remove KPI Summary.

Question ordering sits directly below the table. Multiple questions or groups can be selected and dragged. Moves remain in the browser until `Save order`, avoiding a Streamlit rerun after every movement. Sections and groups follow this saved question order in Excel.

Metric recipes for Standard, Strength, CATA, Bipolar, Listing, Preference and Project-specific questions are always visible before the table. The table supports direct per-question metric editing and safe bulk changes; the detailed question-specific assistant remains under `Advanced metric settings`.

## Benchmark and split handling

Benchmark identification is automatic. Manual benchmark selection is not shown in the standard journey. The two output layouts remain available:

- all benchmarks side by side on one worksheet per split;
- one worksheet per split and benchmark reading.

Any number of detected benchmarks is supported within Excel limits. Each comparison keeps its own scores, bases and significance. Missing benchmark exports are reported rather than invented.

Split names remain editable. Non-empty filters that cannot be parsed are marked for review and never silently become TOTAL. The exact G-Sight value after the filter delimiter is used where available.

## Stages and multilingual projects

All validated result sheets are analysed, so WET, NEAT, DRY and unfamiliar stages can coexist in one source workbook. No question is discarded because its stage is unknown. `Unassigned` questions stay visible and can be mapped directly in the main table to any free-text stage such as Pre-wash, After application or Skin dry-down.

French and English wording is supported for common Standard, Strength/JAR, CATA, Preference, compared-to-current, Bipolar and Listing questions. Original IDs and source metrics remain unchanged. Unknown wording is kept for CMI review.

## Run locally

Run `install_and_launch.bat` for the first installation, then `launch_templyfier.bat` for later sessions. Python must already be installed. Dependencies are pinned in `requirements.txt`.

For an internal server deployment, follow `SERVER_DEPLOYMENT.md`. The current public Streamlit release processes the current session only: drafts, persistent profiles and client memory are not shown.

## Validation

The calculation engine and Excel writer were preserved. Version 56 removes the deferred legacy-template interface, adds source traceability, and makes metric and multi-row editing part of the main review. See `CHANGES_v56.md` and `VALIDATION_v56.md`.
