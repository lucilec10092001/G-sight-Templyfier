# v78 validation

- Full test suite: 205 tests run, 1 skipped, all passing.
- Real IZOARD Paired HUT CMR reviewed: 12 product rows parse successfully, including four pair-specific codes sharing Fr-Land ID `325430` and four sharing `360387`.
- Regression coverage added for shared secondary CMR identifiers, repeated G-Sight positions reusing an exact CMR match, duplicate Excel product headers and repeated Paired product codes in distinct positions.
- The supplied IZOARD raw-data workbook was used only to validate the pair structure. It is not a G-Sight DataViz result table and remains correctly rejected as an application input.
