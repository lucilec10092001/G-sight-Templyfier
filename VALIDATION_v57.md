# Validation — Templyfier v57

- `py -m unittest discover -s tests -t . -p "test_*.py"`
- Result: **173 tests passed, 1 skipped**.
- Python compilation passed for `smart_ui.py`, `question_editor.py` and `onboarding.py`.
- Initial Streamlit AppTest: no exception.
- Help dialog AppTest: no exception, current guide rendered, CMR correctly described as required, no obsolete tutorial copy detected.
- Deep AppTest with real G-Sight and CMR files: no exception; table views and **Preview the final Excel** rendered.
- The calculation engine and Excel writer were unchanged.
