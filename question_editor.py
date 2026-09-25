from copy import deepcopy
import hashlib
import re

import pandas as pd
import streamlit as st

from question_order import question_order
from grouping_ui import render_group_assistant
from templyfier.grouping import remember_edit, undo_edit, redo_edit
from templyfier.review import editor_view_key, audit_questions
from metric_editor import render_metric_editor, render_type_metric_editor
from memory_ui import render_memory_assistant
from templyfier.editor_model import (
    QUESTION_TYPES, change_type, export_rows, matching_selection, prepare_rows,
    reorder_rows, set_metric_selection,
)
from templyfier.smart import _metric_key, proposal_to_row


def _clean(value):
    return " ".join(str(value or "").split())


def _group_id(section, label):
    return hashlib.sha1(f"{section}\0{label.casefold()}".encode("utf-8")).hexdigest()[:12]


def _metric_text(metrics):
    return "; ".join(str(metric) for metric in metrics)


def _parse_metric_text(value):
    return [_clean(item) for item in re.split(r"[;\n·|]+", str(value or "")) if _clean(item)]


def _exact_metric_selection(value, available):
    requested = _parse_metric_text(value)
    by_key = {_metric_key(metric): metric for metric in available}
    missing = [metric for metric in requested if _metric_key(metric) not in by_key]
    if missing:
        raise ValueError(
            "Unknown metric(s): " + ", ".join(missing)
            + ". Use the exact G-Sight metric names, separated with semicolons."
        )
    return [by_key[_metric_key(metric)] for metric in requested]


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
        else:
            st.info("No change to apply.")

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
        "hidden rows stay in the output. Select rows when one change should apply to several questions."
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
            "Select": False,
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
            "Metrics shown in Excel": _metric_text(row.get("Selected metrics", [])),
            "Status": "Please check" if question_id in attention_ids else "Ready",
        })

    st.caption(f"{len(visible)} of {len(rows)} questions shown.")
    view_key = editor_view_key(
        [{"Question ID": row["G-Sight question"]} for row in visible],
        search, f"{scope}|{type_filter}|{stage_filter}|{table_view}",
    )
    column_sets = {
        "Essentials (recommended)": [
            "Select", "Keep", "G-Sight question", "Variable / item", "Group", "Stage",
            "Question type", "Metrics shown in Excel", "Status",
        ],
        "Study mapping": [
            "Select", "Keep", "G-Sight question", "Section", "Stage", "Included splits", "Status",
        ],
        "KPI Summary": [
            "Select", "Keep", "G-Sight question", "Variable / item",
            "KPI Summary", "KPI short label", "Status",
        ],
        "All columns": [
            "Select", "Keep", "G-Sight question", "Variable / item", "Group", "Section",
            "Stage", "Included splits", "KPI Summary", "KPI short label", "Question type",
            "Metrics shown in Excel", "Status",
        ],
    }
    with st.form(f"questions_form_{key}_{revision}_{view_key}"):
        edited = st.data_editor(
            pd.DataFrame(visible), hide_index=True, width="stretch", height=560,
            key=f"questions_table_{key}_{revision}_{view_key}",
            disabled=["G-Sight question", "Status"],
            column_order=column_sets[table_view],
            column_config={
                "Select": st.column_config.CheckboxColumn("Select", pinned=True, help="Select rows for the bulk action below."),
                "Keep": st.column_config.CheckboxColumn("Keep", pinned=True, help="Untick to exclude this question from Excel."),
                "G-Sight question": st.column_config.TextColumn(width="large"),
                "Variable / item": st.column_config.TextColumn("Variable / item shown in Excel", required=True, width="large"),
                "Group": st.column_config.TextColumn("Group shown in Excel", width="medium",
                                                     help="Use the same group name on several rows to group them together."),
                "Section": st.column_config.TextColumn("Section shown in Excel", width="medium"),
                "Stage": st.column_config.TextColumn(width="small",
                                                     help="Type any study-specific stage. Use a semicolon for several stages."),
                "Included splits": st.column_config.TextColumn(width="medium",
                                                               help="All, or split names separated with semicolons."),
                "KPI Summary": st.column_config.CheckboxColumn(width="small"),
                "KPI short label": st.column_config.TextColumn(width="medium"),
                "Question type": st.column_config.SelectboxColumn(options=list(QUESTION_TYPES), required=True, width="medium"),
                "Metrics shown in Excel": st.column_config.TextColumn(
                    width="large",
                    help="Edit one question directly. Use exact G-Sight metric names separated with semicolons.",
                ),
                "Status": st.column_config.TextColumn(width="small"),
            },
        )
        st.caption(
            "Tick Select on any adjacent or non-adjacent rows when the same change should apply to all of them. "
            "For example: rename Color, assign a stage or split, or apply one metric selection."
        )
        bulk_cols = st.columns([1.4, 2.2])
        bulk_action = bulk_cols[0].selectbox(
            "Apply to selected rows",
            ["No bulk action", "Keep", "Exclude", "Set variable / item name", "Set group",
             "Set section", "Set stage", "Set included splits", "Set metrics",
             "Add to KPI Summary", "Remove from KPI Summary"],
        )
        bulk_value = bulk_cols[1].text_input(
            "New value", placeholder="For metrics, separate exact G-Sight names with semicolons",
            disabled=bulk_action not in {
                "Set variable / item name", "Set group", "Set section", "Set stage",
                "Set included splits", "Set metrics",
            },
        )
        submitted = st.form_submit_button("Save table changes", type="primary", icon=":material/save:")

    if submitted:
        changed = deepcopy(rows)
        by_id = {row["Question ID"]: row for row in changed}
        selected_ids = set(edited.loc[edited["Select"].astype(bool), "G-Sight question"].tolist())
        try:
            for edit in edited.to_dict("records"):
                row = by_id[edit["G-Sight question"]]
                prior_type = row["Type"]
                prior_metrics = list(row["Selected metrics"])
                edited_type = edit.get("Question type", prior_type)
                change_type(row, edited_type)
                edited_metrics = _exact_metric_selection(
                    edit.get("Metrics shown in Excel", _metric_text(prior_metrics)),
                    row["Available metric list"],
                )
                if edited_type == prior_type or {
                    _metric_key(metric) for metric in edited_metrics
                } != {_metric_key(metric) for metric in prior_metrics}:
                    set_metric_selection(row, edited_metrics)
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
                    "Keep": bool(edit.get("Keep", row["Keep"])), "Section": section,
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

            if bulk_action != "No bulk action" and not selected_ids:
                raise ValueError("Select at least one row before applying a bulk action.")
            if bulk_action in {
                "Set variable / item name", "Set group", "Set section", "Set stage",
                "Set included splits", "Set metrics",
            } and not _clean(bulk_value):
                raise ValueError("Enter the new value for the selected rows.")
            for question_id in selected_ids:
                row = by_id[question_id]
                if bulk_action == "Keep":
                    row["Keep"] = True
                elif bulk_action == "Exclude":
                    row["Keep"] = False
                elif bulk_action == "Set variable / item name":
                    if row.get("Group ID"):
                        row["Metric label"] = _clean(bulk_value)
                    else:
                        row["Display label"] = _clean(bulk_value)
                elif bulk_action == "Set group":
                    label = _clean(bulk_value)
                    variable = row.get("Metric label") or row["Display label"]
                    row["Group ID"] = _group_id(row.get("Section", ""), label)
                    row["Display label"] = label
                    row["Metric label"] = variable
                elif bulk_action == "Set section":
                    row["Section"] = _clean(bulk_value)
                    if row.get("Group ID"):
                        row["Group ID"] = _group_id(row["Section"], row["Display label"])
                elif bulk_action == "Set stage":
                    row["Stage"] = _clean(bulk_value)
                elif bulk_action == "Set included splits":
                    row["Included splits"] = _clean(bulk_value)
                elif bulk_action == "Set metrics":
                    requested = _parse_metric_text(bulk_value)
                    matched = matching_selection(requested, row["Available metric list"])
                    if len(matched) != len(requested):
                        raise ValueError(
                            f"{row['Question ID']}: the requested metrics do not all have a safe match. "
                            "Use question-type recipes or edit this question separately."
                        )
                    set_metric_selection(row, matched)
                elif bulk_action == "Add to KPI Summary":
                    row["KPI Summary"] = True
                elif bulk_action == "Remove from KPI Summary":
                    row["KPI Summary"] = False
            commit(changed, "Question table updated.")
        except ValueError as exc:
            st.error(str(exc))

    st.markdown("### Change the question order")
    st.caption("Select one or several questions, including non-adjacent rows, and drag a handle. "
               "Moves stay local until **Save order**, so the page does not reload after every move.")
    order_result = question_order(rows, revision, f"order_{key}")
    event = order_result.reordered
    if event and event.get("revision") == revision:
        try:
            if event["ids"] != [row["Question ID"] for row in rows]:
                commit(reorder_rows(rows, event["ids"]), "Question order updated.", request_rerun=False)
        except (ValueError, KeyError, TypeError) as exc:
            st.error(f"Move not applied: {exc}")

    with st.expander("Advanced metric settings", expanded=bool(st.session_state.get(f"metric_batch_{key}")),
                     icon=":material/tune:"):
        st.caption("Use these controls only when a question type or one question needs different result rows.")
        render_metric_editor(model["rows"], key, model["revision"], commit)

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
