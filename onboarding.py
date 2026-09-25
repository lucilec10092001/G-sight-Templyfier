from __future__ import annotations

import streamlit as st

from templyfier.preferences import has_seen_onboarding, mark_onboarding_seen


TUTORIAL_STEPS = (
    {
        "eyebrow": "1 · Add the study files",
        "title": "Start with G-Sight and the matching CMR export",
        "body": (
            "Select all G-Sight DataViz outputs together. You can use one workbook "
            "containing every split or one workbook per split."
        ),
        "points": (
            "G-Sight output(s): required",
            "Matching CMR export: required",
            "Templyfier proposes splits, benchmarks, stages and question types automatically",
        ),
        "callout": "Your files stay in the current processing session.",
    },
    {
        "eyebrow": "2 · Confirm the important choices",
        "title": "Check only what can materially change the Excel output",
        "body": (
            "Confirm the study format, output layout and proposed split names. "
            "Then choose the default results shown in Excel for each question type."
        ),
        "points": (
            "Rows marked Please check need a CMI decision",
            "Use Select when one change should apply to several questions",
            "Use the table views to show only the columns needed for the current task",
        ),
        "callout": "Safe defaults are already selected. Advanced settings are optional.",
    },
    {
        "eyebrow": "3 · Generate",
        "title": "Create the toplines when the review is ready",
        "body": (
            "You can generate immediately after the question review or open optional "
            "settings for product names, ordering and detailed metric exceptions."
        ),
        "points": (
            "The Generate button stays disabled if a required check is unresolved",
            "No missing score, gap or significance is invented",
            "Download the finished Excel file when generation completes",
        ),
        "callout": "If something blocks generation, Templyfier tells you exactly what to correct.",
    },
)


@st.dialog("Welcome to G-Sight Templyfier", width="large")
def _tutorial_dialog() -> None:
    step = max(0, min(int(st.session_state.get("tutorial_step", 0)), len(TUTORIAL_STEPS) - 1))
    content = TUTORIAL_STEPS[step]
    st.caption(content["eyebrow"])
    st.subheader(content["title"])
    st.write(content["body"])
    for point in content["points"]:
        st.markdown(f"- {point}")
    st.info(content["callout"], icon="💡")
    st.progress((step + 1) / len(TUTORIAL_STEPS), text=f"Step {step + 1} of {len(TUTORIAL_STEPS)}")

    previous_col, _, next_col = st.columns([1, 2.2, 1])
    if previous_col.button("Previous", disabled=step == 0, width="stretch"):
        st.session_state.tutorial_step = step - 1
        st.session_state.tutorial_reopen = True
        st.rerun()
    if step < len(TUTORIAL_STEPS) - 1:
        if next_col.button("Next", type="primary", width="stretch"):
            st.session_state.tutorial_step = step + 1
            st.session_state.tutorial_reopen = True
            st.rerun()
    elif next_col.button("Start", type="primary", width="stretch"):
        st.session_state.tutorial_step = 0
        st.rerun()


def render_onboarding() -> None:
    """Keep a short optional guide available without interrupting the main journey."""
    _, help_col = st.columns([7, 1.35])
    help_clicked = help_col.button(
        "Help",
        key="open_tutorial",
        width="stretch",
        help="Open the three-step quick guide.",
    )

    first_visit = "onboarding_checked" not in st.session_state
    show_tutorial = help_clicked or bool(st.session_state.pop("tutorial_reopen", False))
    if first_visit:
        st.session_state.onboarding_checked = True
        if not has_seen_onboarding():
            mark_onboarding_seen()
            st.session_state.tutorial_step = 0
            st.info(
                "Start by adding the G-Sight outputs and CMR export. Safe defaults are "
                "already selected; Help remains available at the top of the page."
            )
    if help_clicked:
        st.session_state.tutorial_step = 0
    if show_tutorial:
        _tutorial_dialog()
