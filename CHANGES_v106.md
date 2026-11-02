# Templyfier v106

## Clearer topline reading

- A restrained separator now closes each question block after its final metric.
- Rows belonging to the same item family remain visually together; the separator is applied only at the end of the family.
- No blank rows are inserted, so attribute-heavy toplines stay compact.
- The same shared formatting rule is used for Monadic, Paired, CLT and HUT outputs, including benchmark layouts.

## Quality control

- Added an automated regression test for Monadic and Paired question-block separators.
- The complete unit-test suite passes: 237 tests, with 1 optional real-data test skipped when its fixture is unavailable.

