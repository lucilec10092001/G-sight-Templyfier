# Templyfier v103 - batch table editing

- The question table no longer reruns the Streamlit page after every cell edit.
- CMIs can paste or modify many `Item family`, `Section header`, item-name, stage, metric or other cells in one editing session.
- Changes are committed once through **Apply table changes**.
- Item-family and section consolidation occurs only after that button is selected, so it cannot interrupt a large paste operation.
- After applying, equal Item family names are still gathered automatically and the order view and Excel remain structured.
- Explicit **Edit together** propagation remains available inside the same apply action.

