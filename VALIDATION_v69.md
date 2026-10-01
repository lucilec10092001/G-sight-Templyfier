# Validation - Templyfier v69

- Full automated suite: 191 tests passed, 1 skipped.
- New regression: composite G-Sight headers are matched to exact CMR codes and explicit benchmark types.
- New regression: a stage-named `2_TAILED` worksheet is selected without treating its `1_TAILED` and `DELTA` companions as extra splits.
- Real-file validation with the supplied Herbal Essences Hair Oil DataViz and CMR:
  - 10/10 products matched;
  - A26 and B35 detected as the two benchmarks;
  - 15 questions detected and generated;
  - side-by-side output generated successfully;
  - separate benchmark worksheets generated successfully;
  - generated XLSX files reopened successfully.
