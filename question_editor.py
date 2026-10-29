from copy import deepcopy
import hashlib
import re

import pandas as pd
import streamlit as st

from question_order import question_order
from grouping_ui import render_group_assistant
from templyfier.grouping import remember_edit, undo_edit, redo_edit
from templyfier.review import audit_questions, editor_view_key, safe_metric_match
from metric_editor import render_type_metric_editor
from memory_ui import render_memory_assistant
from templyfier.editor_model import (
    QUESTION_TYPES, change_type, export_rows, prepare_rows,
    reorder_rows, set_metric_selection,
)
from templyfier.smart import _metric_key, proposal_to_row


def _clean(value):
    return " ".join(str(value or "").split())


def _group_id(section, label):
    return hashlib.sha1(f"{section}\0{label.casefold()}".encode("utf-8")).hexdigest()[:12]


def _same_cell_value(left, right):
    """Compare data-editor values without treating list identity or NaN as a change."""
    if isinstance(left, (list, tuple)) or isinstance(right, (list, tuple)):
        return list(left or []) == list(right or [])
    if pd.isna(left) and pd.isna(right):
        return True
    return left == right


def _selected_cell_changes(original_records, edited_records, selected_ids):
    """Return explicit edits made inside selected rows, grouped by column."""
    selected = set(selected_ids)
    originals = {row["G-Sight question"]: row for row in original_records}
    ignored = {"Edit together", "G-Sight question", "Status"}
    changes = {}
    for edited in edited_records:
        question_id = edited["G-Sight question"]
        if question_id not in selected or question_id not in originals:
            continue
        original = originals[question_id]
        for column, value in edited.items():
            if column in ignored or _same_cell_value(value, original.get(column)):
                continue
            changes.setdefault(column, []).append((question_id, value))
    return changes


def _apply_table_metric_edit(row, edited_type, edited_metrics, type_sources):
    """Apply one editable table row and honour the preset of a newly selected type."""
    previous_type = row["Type"]
    if edited_type != previous_type:
        change_type(row, edited_type)
        source = type_sources.get(edited_type)
        if source is not None:
            matched, missing = safe_metric_match(source, row, source.get("Selected metrics", []))
            if not missing and matched:
                set_metric_selection(row, matched)
        return
    chosen = list(edited_metrics) if isinstance(edited_metrics, (list, tuple)) else []
    set_metric_selection(row, chosen)


def _apply_group_wide_table_edits(changed, original_rows, original_records, edited_records):
    """Keep a displayed group coherent when its name or section is edited once."""
    originals = {record["G-Sight question"]: record for record in original_records}
    source_rows = {row["Question ID"]: row for row in original_rows}
    updates = {}
    for edited in edited_records:
        question_id = edited.get("G-Sight question")
        original = originals.get(question_id)
        source = source_rows.get(question_id)
        old_group_id = source.get("Group ID") if source else ""
        if not original or not old_group_id:
            continue
        group_changed = not _same_cell_value(edited.get("Group"), original.get("Group"))
        section_changed = not _same_cell_value(edited.get("Section"), original.get("Section"))
        if not group_changed and not section_changed:
            continue
        proposed = (
            _clean(edited.get("Group", original.get("Group", ""))),
            _clean(edited.get("Section", original.get("Section", ""))),
            group_changed,
            section_changed,
        )
        if old_group_id in updates and updates[old_group_id] != proposed:
            raise ValueError("A group received two different names or sections. Keep one value.")
        updates[old_group_id] = proposed

    for old_group_id, (group, section, group_changed, section_changed) in updates.items():
        member_ids = {
            row["Question ID"] for row in original_rows if row.get("Group ID") == old_group_id
        }
        members = [row for row in changed if row["Question ID"] in member_ids]
        for row in members:
            if section_changed:
                row["Section"] = section
            if group_changed and not group:
                row["Display label"] = row.get("Metric label") or row["Display label"]
                row["Metric label"] = ""
                row["Group ID"] = ""
                continue
            if group_changed:
                row["Display label"] = group
            if row.get("Group ID"):
                row["Group ID"] = _group_id(row.get("Section", ""), row["Display label"])
    return changed


def _apply_selected_metrics(rows, selected_ids, chosen, labels=None):
    if not selected_ids:
        raise ValueError("Select at least one question.")
    if not chosen:
        raise ValueError("Keep at least one result for the selected questions.")
    changed = deepcopy(rows)
    by_id = {row["Question ID"]: row for row in changed}
    source = by_id.get(selected_ids[0])
    if source is None or not set(chosen).issubset(set(source["Available metric list"])):
        raise ValueError("The selected results are not available for the source question.")
    skipped = []
    for question_id in selected_ids:
        target = by_id.get(question_id)
        if target is None:
            raise ValueError(f"Question not found: {question_id}")
        if question_id == source["Question ID"]:
            matched, missing = list(chosen), []
        else:
            matched, missing = safe_metric_match(source, target, chosen)
        if missing:
            skipped.append(question_id)
            continue
        set_metric_selection(
            target,
            matched,
            labels if len(selected_ids) == 1 and question_id == source["Question ID"] else None,
        )
    return changed, skipped


def render_question_editor(frame, proposals, key, memory=None, protected_ids=(), project_key=None,
                           show_optional=True, stage_order=()):
    """Render one calm review surface for all question-level decisions."""
    model_key = f"question_model_{key}"
    if model_key not in st.session_state:
        initial_rows = prepare_rows(frame.to_dict("records"), proposals, stage_order)
        if len(stage_order) > 1:
            normalized = [(index, re.sub(r"[\W_]+", " ", str(stage).casefold()).strip())
                          for index, stage in enumerate(stage_order)]

            def stage_rank(item):
                text = re.sub(
                    r"[\W_]+", " ",
                    " ".join(str(item.get(field, "")) for field in
                             ("Stage", "Question ID", "Display label", "Section")).casefold(),
                ).strip()
                matched = next((index for index, stage in normalized
                                if stage and re.search(rf"\b{re.escape(stage)}\b", text)), len(normalized))
                return matched, int(item.get("Order", 999999))

            initial_rows = sorted(initial_rows, key=stage_rank)
            for index, row in enumerate(initial_rows, 1):
                row["Order"] = index
        st.session_state[model_key] = {
            "rows": initial_rows, "revision": 0, "history": [], "stage_order": list(stage_order)
        }

    model = st.session_state[model_key]
    if "learning_baseline" not in model:
        model["learning_baseline"] = prepare_rows(
            [proposal_to_row(proposal) for proposal in proposals], proposals, stage_order
        )
    rows, revision = model["rows"], model["revision"]

    def commit(changed, action="Question settings updated.", *, request_rerun=True):
        if remember_edit(model, changed, action):
            if request_rerun:
                st.session_state[f"editor_refresh_{key}"] = True
            return True
        else:
            st.info("No change to apply.")
            return False

    audit = audit_questions(rows)
    type_attention_ids = {
        item["Question ID"] for item in audit["issues"]
        if item.get("Code") in {"uncertain_type", "unknown_type"}
    }
    summary = st.columns(3)
    summary[0].metric("Questions detected", len(rows))
    summary[1].metric("Question types", len({row["Type"] for row in rows if row.get("Keep")}))
    summary[2].metric("To be checked", len(type_attention_ids))
    st.caption(
        "Rows marked **Please check** need a quick CMI decision. All other suggestions are ready to use."
        if type_attention_ids else
        "All question types have a confident proposal. Keep the defaults or adjust any row."
    )

    with st.container(horizontal=True):
        st.button("Undo", key=f"undo_questions_{key}", disabled=not model.get("history"),
                  icon=":material/undo:", on_click=undo_edit, args=(model,))
        st.button("Redo", key=f"redo_questions_{key}", disabled=not model.get("redo"),
                  icon=":material/redo:", on_click=redo_edit, args=(model,))
    if model.get("notice"):
        st.toast(model["notice"], icon=":material/check_circle:")

    render_type_metric_editor(model["rows"], key, model["revision"], commit)

    st.markdown("### Review questions")
    st.caption(
        "Everything that affects the Excel output is in this table. Filtering only changes the view; "
        "hidden rows stay in the output. Edit a cell to change one question. To make the same change "
        "on several questions, tick **Edit together** on those rows and edit any one of their cells."
    )
    filter_cols = st.columns([2.2, 1.1, 1.1, 1.1, 1.35])
    search = filter_cols[0].text_input(
        "Search", key=f"question_search_{key}", placeholder="Question, item, group, section or stage"
    )
    scope = filter_cols[1].selectbox(
        "Show", ["All", "Please check", "Kept", "Excluded"], key=f"question_scope_{key}"
    )
    present_types = list(dict.fromkeys(row["Type"] for row in rows))
    type_filter = filter_cols[2].selectbox(
        "Question type", ["All", *present_types], key=f"question_type_filter_{key}"
    )
    present_stages = list(dict.fromkeys(_clean(row.get("Stage")) or "Unassigned" for row in rows))
    stage_filter = filter_cols[3].selectbox(
        "Stage", ["All", *present_stages], key=f"question_stage_filter_{key}"
    )
    table_view = filter_cols[4].selectbox(
        "Table view",
        ["Essentials (recommended)", "Study mapping", "KPI Summary", "All columns"],
        key=f"question_table_view_{key}",
        help="This changes only the columns shown. It never removes information from the output.",
    )

    attention_ids = set(audit["attention_ids"])
    visible = []
    for row in rows:
        question_id = row["Question ID"]
        if scope == "Please check" and question_id not in attention_ids:
            continue
        if scope == "Kept" and not row["Keep"]:
            continue
        if scope == "Excluded" and row["Keep"]:
            continue
        if type_filter != "All" and row["Type"] != type_filter:
            continue
        stage = _clean(row.get("Stage")) or "Unassigned"
        if stage_filter != "All" and stage != stage_filter:
            continue
        searchable = " ".join(str(row.get(field, "")) for field in
                              ("Question ID", "Display label", "Metric label", "Section", "Stage", "Type")).casefold()
        if search.strip() and search.strip().casefold() not in searchable:
            continue
        grouped = bool(row.get("Group ID"))
        visible.append({
            "Edit together": False,
            "Keep": bool(row["Keep"]),
            "G-Sight question": question_id,
            "Variable / item": row.get("Metric label") if grouped else row["Display label"],
            "Group": row["Display label"] if grouped else "",
            "Section": row.get("Section", ""),
            "Stage": stage,
            "Included splits": row.get("Included splits", "All"),
            "KPI Summary": bool(row.get("KPI Summary")),
            "KPI short label": row.get("Summary label", ""),
            "Question type": row["Type"],
            "Metrics shown in Excel": list(row.get("Selected metrics", [])),
            "Status": "Please check" if question_id in attention_ids else "Ready",
        })

    st.caption(f"{len(visible)} of {len(rows)} questions shown.")
    view_key = editor_view_key(
        [{"Question ID": row["G-Sight question"]} for row in visible],
        search, f"{scope}|{type_filter}|{stage_filter}|{table_view}",
    )
    column_sets = {
        "Essentials (recommended)": [
            "Keep", "Edit together", "Question type", "Metrics shown in Excel", "G-Sight question",
            "Variable / item", "Group", "Stage", "Status",
        ],
        "Study mapping": [
            "Keep", "Edit together", "G-Sight question", "Section", "Stage", "Included splits", "Status",
        ],
        "KPI Summary": [
            "Keep", "Edit together", "G-Sight question", "Variable / item",
            "KPI Summary", "KPI short label", "Status",
        ],
        "All columns": [
            "Keep", "Edit together", "Question type", "Metrics shown in Excel", "G-Sight question",
            "Variable / item", "Group", "Section",
            "Stage", "Included splits", "KPI Summary", "KPI short label", "Status",
        ],
    }
    edited = st.data_editor(
        pd.DataFrame(visible), hide_index=True, width="stretch", height=560,
        key=f"questions_table_{key}_{revision}_{view_key}",
        disabled=["G-Sight question", "Status"],
        column_order=column_sets[table_view],
        column_config={
            "Edit together": st.column_config.CheckboxColumn(
                "Edit together",
                help="Tick several rows, then edit one selected row. The value is copied to every selected row.",
            ),
            "Keep": st.column_config.CheckboxColumn(
                "Keep", pinned=True, help="Untick to exclude this question from Excel."
            ),
            "G-Sight question": st.column_config.TextColumn(width="large"),
            "Variable / item": st.column_config.TextColumn(
                "Variable / item shown in Excel", required=True, width="large"
            ),
            "Group": st.column_config.TextColumn(
                "Item family (optional)", width="medium",
                help=("Use only for true one-result item batteries such as Color or Olfactive Attributes. "
                      "Leave blank for ordinary questions; it does not replace the Section."),
            ),
            "Section": st.column_config.TextColumn(
                "Section header shown in Excel", width="medium",
                help="This is the purple section header in Excel. Select related rows to rename it consistently.",
            ),
            "Stage": st.column_config.TextColumn(
                width="small", help="Type any study-specific stage. Use a semicolon for several stages."
            ),
            "Included splits": st.column_config.TextColumn(
                width="medium", help="All, or split names separated with semicolons."
            ),
            "KPI Summary": st.column_config.CheckboxColumn(width="small"),
            "KPI short label": st.column_config.TextColumn(width="medium"),
            "Question type": st.column_config.SelectboxColumn(
                options=list(QUESTION_TYPES), required=True, width="medium",
                help="Choose the question family. Its default Metrics recipe is applied when you save.",
            ),
            "Metrics shown in Excel": st.column_config.MultiselectColumn(
                "Metrics",
                width="large",
                options=list(dict.fromkeys(
                    metric
                    for source_row in rows
                    for metric in source_row.get("Available metric list", [])
                )),
                help="Open the list and tick the results to show for this question in Excel.",
            ),
            "Status": st.column_config.TextColumn(width="small"),
        },
    )

    selected_ids = edited.loc[
        edited["Edit together"].astype(bool), "G-Sight question"
    ].astype(str).tolist()
    comparison_columns = [column for column in edited.columns if column != "Edit together"]
    original_visible = pd.DataFrame(visible)
    table_dirty = not edited[comparison_columns].reset_index(drop=True).equals(
        original_visible[comparison_columns].reset_index(drop=True)
    )
    shared_changes = _selected_cell_changes(
        visible, edited.to_dict("records"), selected_ids
    )

    def apply_visible_table_edits(propagated=None):
        changed = deepcopy(rows)
        by_id = {row["Question ID"]: row for row in changed}
        type_sources = {}
        for source_row in rows:
            if source_row.get("Keep") and source_row["Type"] not in type_sources:
                type_sources[source_row["Type"]] = source_row
        edit_records = edited.to_dict("records")
        if propagated:
            edited_by_id = {record["G-Sight question"]: record for record in edit_records}
            source_rows = {row["Question ID"]: row for row in rows}
            for column, entries in propagated.items():
                values = []
                for source_id, value in entries:
                    if not any(_same_cell_value(value, existing) for existing in values):
                        values.append(value)
                if len(values) != 1:
                    raise ValueError(
                        f"Two different values were entered for {column}. Keep one value before editing together."
                    )
                source_id, value = entries[-1]
                for question_id in selected_ids:
                    if column == "Metrics shown in Excel" and question_id != source_id:
                        matched, missing = safe_metric_match(
                            source_rows[source_id], source_rows[question_id], list(value or [])
                        )
                        if missing:
                            raise ValueError(
                                f"The selected Metrics are not available for {question_id}. "
                                "No shared change was applied."
                            )
                        edited_by_id[question_id][column] = matched
                    else:
                        edited_by_id[question_id][column] = value
            edit_records = list(edited_by_id.values())
        for edit in edit_records:
            row = by_id[edit["G-Sight question"]]
            _apply_table_metric_edit(
                row,
                edit.get("Question type", row["Type"]),
                edit.get("Metrics shown in Excel", row.get("Selected metrics", [])),
                type_sources,
            )
            grouped_before = bool(row.get("Group ID"))
            variable = _clean(edit.get(
                "Variable / item",
                row.get("Metric label") if grouped_before else row["Display label"],
            ))
            if not variable:
                raise ValueError("A variable or item name is empty.")
            section = _clean(edit.get("Section", row.get("Section", "")))
            group = _clean(edit.get(
                "Group", row["Display label"] if grouped_before else ""
            ))
            row.update({
                "Keep": bool(edit.get("Keep", row["Keep"])),
                "Section": section,
                "Stage": _clean(edit.get("Stage", row.get("Stage", ""))) or "Unassigned",
                "Included splits": _clean(
                    edit.get("Included splits", row.get("Included splits", "All"))
                ) or "All",
                "KPI Summary": bool(edit.get("KPI Summary", row.get("KPI Summary"))),
                "Summary label": _clean(
                    edit.get("KPI short label", row.get("Summary label", ""))
                ),
            })
            if group:
                row["Group ID"] = _group_id(section, group)
                row["Display label"] = group
                row["Metric label"] = variable
            else:
                row["Group ID"] = ""
                row["Display label"] = variable
                row["Metric label"] = ""
        _apply_group_wide_table_edits(changed, rows, visible, edit_records)
        return changed, by_id

    if selected_ids and not shared_changes:
        st.info(
            f"**{len(selected_ids)} question(s) selected.** Now edit one selected cell; "
            "the same value will be copied to every selected question.",
            icon=":material/checklist:",
        )

    if selected_ids and shared_changes:
        try:
            changed, _ = apply_visible_table_edits(shared_changes)
            columns = ", ".join(shared_changes)
            if remember_edit(
                model, changed,
                f"{columns} applied to {len(selected_ids)} selected question(s).",
            ):
                st.rerun()
        except ValueError as exc:
            st.error(str(exc))

    if table_dirty and not shared_changes:
        try:
            changed, _ = apply_visible_table_edits()
            if commit(changed, "Question table updated."):
                st.rerun()
        except ValueError as exc:
            st.error(str(exc))

    st.caption("Question-table edits are saved automatically.")

    with st.expander("Change question order - optional", expanded=False):
        st.caption("Select one or several questions, including non-adjacent rows, and drag a handle. "
                   "Moves stay local until **Save order**, so the page does not reload after every move.")
        order_result = question_order(rows, revision, f"order_{key}")
        event = order_result.reordered
        if event and event.get("revision") == revision:
            try:
                if event["ids"] != [row["Question ID"] for row in rows]:
                    if commit(reorder_rows(rows, event["ids"]), "Question order updated."):
                        st.rerun()
            except (ValueError, KeyError, TypeError) as exc:
                st.error(f"Move not applied: {exc}")

    empty = [row for row in model["rows"] if row["Keep"] and not row["Selected metrics"]]
    if empty:
        st.warning(f"{len(empty)} kept question(s) have no metric. Select at least one result or untick Keep.")
    return pd.DataFrame(export_rows(model["rows"]))


def render_optional_question_tools(key, memory=None, protected_ids=(), project_key=None, *,
                                   include_reorder=True, include_grouping=True, stage_order=()):
    """Backward-compatible advanced tools for saved configurations."""
    model = st.session_state[f"question_model_{key}"]
    rows, revision = model["rows"], model["revision"]

    def commit(changed, action="Question settings updated."):
        if remember_edit(model, changed, action):
            st.session_state[f"editor_refresh_{key}"] = True

    ignored_by_memory = ()
    if include_grouping:
        if memory is not None:
            ignored_by_memory = render_memory_assistant(
                rows, model["learning_baseline"], memory, key, revision, commit,
                protected_ids=protected_ids,
                pending_metrics=bool(st.session_state.get(f"metric_batch_{key}")), project_key=project_key,
            )
        render_group_assistant(rows, key, revision, commit, ignored_by_memory=ignored_by_memory,
                               stage_names=stage_order)
    if include_reorder:
        result = question_order(rows, revision, f"order_optional_{key}")
        event = result.reordered
        if event and event.get("revision") == revision and event["ids"] != [row["Question ID"] for row in rows]:
            commit(reorder_rows(rows, event["ids"]), "Question order updated.")
    return pd.DataFrame(export_rows(model["rows"]))

