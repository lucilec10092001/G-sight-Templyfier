# Templyfier v76

## Streamlit Cloud symbol hotfix

- Replaced the invalid success icon that could become `?` during publication with a Streamlit Material icon.
- Replaced visible Unicode separators with transport-safe ASCII separators.
- Replaced other alert emojis with Material icons.
- Replaced the HTML privacy icon with an ASCII HTML entity.
- Added a regression test covering alert icons and visible separators.

No detection, calculation, CMR matching or Excel-writing logic changed.
