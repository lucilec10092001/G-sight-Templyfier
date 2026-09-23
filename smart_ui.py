from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import streamlit as st
from templyfier.english_catalog import TEXT

from question_editor import render_question_editor, render_optional_question_tools

from templyfier.core import TemplyfierError
from templyfier.grouping import stages_for
from review_ui import render_structure_preview
from templyfier.review import audit_questions
from templyfier.smart import (
    STANDARD_METRICS,
    audit_input_plan,
    build_smart_toplines,
    cmr_product_label,
    inspect_smart_package,
    match_cmr_products,
    _normal,
    profile_to_json,
    proposal_to_row,
)


def _files_key(files, profile=None, cmr=None, local_profile_name="", local_profile=None):
    digest = hashlib.sha1()
    for item in files:
        digest.update(item.name.encode("utf-8"))
        digest.update(item.getvalue())
    if profile is not None:
        digest.update(profile.getvalue())
    if cmr is not None:
        digest.update(cmr.name.encode("utf-8"))
        digest.update(cmr.getvalue())
    digest.update(str(local_profile_name).encode("utf-8"))
    if local_profile is not None and profile is None:
        digest.update(json.dumps(local_profile, sort_keys=True, ensure_ascii=False).encode('utf-8'))
    return digest.hexdigest()


def _question_content_signature(frame):
    """Track content decisions without treating optional row order as a new review."""
    content = frame.drop(columns=['Order'], errors='ignore')
    return hashlib.sha1(content.to_json(orient='records').encode('utf-8')).hexdigest()


def _step(number, title, hint):
    st.markdown(
        f'<div class="step-title" id="etape-{number}"><span class="step-number">{number}</span>{title}</div>'
        f'<div class="hint">{hint}</div>',
        unsafe_allow_html=True,
    )


def _output_options(settings, key, test_type, mean_decimals):
    with st.container(border=True):
        st.markdown('**Score difference columns — optional**')
        show_difference = st.checkbox('Show gap / delta columns (candidate score minus benchmark score)',
            value=bool(settings.get('show_monadic_gaps' if test_type == 'Monadic' else 'include_deltas', True)),
            key=f"smart_monadic_gaps_{key}" if test_type == 'Monadic' else f"smart_deltas_{key}",
            help='Hide these columns when the client does not need score differences. Scores and benchmark-specific significance remain visible.')
        st.caption('Positive gap = candidate score is higher. This does not automatically mean better: check the favourable direction of the question.')
    include_deltas = show_difference if test_type == 'Paired' else True
    show_gaps = show_difference if test_type == 'Monadic' else True
    with st.expander("Options de mise en page — facultatif"):
        option_cols = st.columns(3)
        include_screeners = option_cols[0].checkbox(
            "Ajouter Screeners",
            value=bool(settings.get("include_screeners", True)),
            key=f"smart_screeners_{key}",
        )
        include_sections = option_cols[1].checkbox(
            "Afficher les sections",
            value=bool(settings.get("include_sections", True)),
            key=f"smart_sections_{key}",
        )
        if test_type == "Monadic":
            saved_order = settings.get("output_sheet_order", "benchmark_first")
            output_order_label = st.radio(
                "Ordre des onglets",
                ["Par benchmark puis par split (recommandé)", "Par split puis par benchmark"],
                horizontal=True,
                index=0 if saved_order == "benchmark_first" else 1,
                key=f"smart_output_order_{key}",
            )
            output_order = "benchmark_first" if output_order_label.startswith("Par benchmark") else "split_first"
            render_cols = st.columns(2)
            highlight_benchmarks = render_cols[1].checkbox(
                "Mettre les benchmarks en évidence",
                value=bool(settings.get("highlight_benchmarks", True)),
                key=f"smart_highlight_benchmarks_{key}",
            )
            if not show_gaps:
                st.caption(
                    "Les colonnes de gap seront masquées. Les significativités resteront visibles "
                    "uniquement sur les valeurs des candidats."
                )
        else:
            output_order, highlight_benchmarks = "split_first", False
    return (
        mean_decimals,
        include_screeners,
        include_sections,
        include_deltas,
        output_order,
        show_gaps,
        highlight_benchmarks,
    )


def render_smart_mode():
    with st.sidebar:
        st.subheader('Your journey')
        st.markdown('[Upload files](#etape-upload)\n\n[0 · Study setup](#etape-0)\n\n[1 · Excel structure](#etape-1)\n\n[2 · Questions and metrics](#etape-2)\n\n[3 · Optional order](#etape-3)\n\n[4 · Advanced options](#etape-4)')
        navigation_status = st.empty()
        sidebar_generate_slot = st.empty()
        navigation_status.progress(.1, text='Commence par les exports G-Sight')
        st.caption('Navigation does not change your choices. Click Save after editing a table.')
    st.caption('Start with your exports. We prepare editable suggestions; you stay in control of the final choices.')
    _step(
        "upload",
        "Ajoute tous les exports G-Sight",
        "Select all exports needed for your study. The CMR file is optional.",
    )
    exports_col, cmr_col = st.columns([1.35, 1], gap="large")
    with exports_col:
        exports = st.file_uploader(
            "Exports G-Sight DataViz",
            type=["xlsx", "xls"],
            accept_multiple_files=True,
            key="smart_exports",
            help="Exemple : 5 splits face à 2 benchmarks = 10 exports G-Sight à sélectionner ensemble.",
        )
        with st.expander('Which files should I select?'):
            st.caption('Select all G-Sight exports needed for your project together. Include each required split and benchmark comparison. For example, five splits compared with two benchmarks may require ten exports.')
    with cmr_col:
        cmr_upload = st.file_uploader(
            "CMR request export — optional",
            type=["xlsx", "xls"],
            key="smart_cmr",
            help="Charge les Fantasy names, Formula descriptions et Formula codes associés aux produits.",
        )
    # Initial shared-server release: keep the path focused on the current
    # project. Drafts, saved profiles and persistent client memory stay hidden.
    local_profile_name = "Aucune"
    profile_upload = None
    resumed_draft = None
    local_profiles = {}
    client_memory = None
    if not exports:
        if st.session_state.pop('memory_refresh_requested', False):
            st.rerun()
        st.stop()

    key = _files_key(exports, profile_upload, cmr_upload, local_profile_name, resumed_draft if resumed_draft and not profile_upload else local_profiles.get(local_profile_name))
    state_key = f"smart_state_{key}"
    if state_key not in st.session_state:
        try:
            with st.spinner("Analyse du questionnaire et des métriques…"):
                info = inspect_smart_package([(item.name, item.getvalue()) for item in exports])
                profile = None
                question_rows = [proposal_to_row(item) for item in info.questions]
                saved_settings = {}
                result_inputs = [item for item in info.inputs if item.role == "Résultats"] or list(info.inputs)
                cmr_matches = (
                    match_cmr_products(result_inputs[0].product_keys, info.product_names, cmr_upload.getvalue())
                    if cmr_upload else ()
                )
        except Exception as exc:
            st.error(f"Analyse impossible : {exc}")
            st.stop()
        st.session_state[state_key] = {
            "info": info,
            "questions": pd.DataFrame(question_rows),
            "splits": pd.DataFrame(
                {
                    "Fichier": [item.filename for item in info.inputs if item.role == "Résultats"],
                    "Nom de l’onglet": [item.split_name for item in info.inputs if item.role == "Résultats"],
                    "Stage": [item.stage for item in info.inputs if item.role == "Résultats"],
                    "Split detection": [item.split_detection for item in info.inputs if item.role == "Résultats"],
                    "Benchmark détecté": [" · ".join(item.comparison_codes) or "—" for item in info.inputs if item.role == "Résultats"],
                    "Bases": [" · ".join("?" if n is None else str(n) for n in item.counts) for item in info.inputs if item.role == "Résultats"],
                }
            ),
            "settings": saved_settings,
            "profile_comparison": None,
            "profile_protected_ids": [],
            "cmr_matches": cmr_matches,
        }

    state = st.session_state[state_key]
    info = state["info"]
    settings = state["settings"]

    result_inputs = [item for item in info.inputs if item.role == "Résultats"] or list(info.inputs)
    suggested_test_type = "Paired" if info.suggested_test_type.startswith("Paired") else "Monadic"
    saved_test_type = settings.get("test_type", suggested_test_type)
    gate_prefix = f"journey_{key}"
    qa_skip_gates = bool(st.session_state.get("_qa_skip_journey_gates", False))

    _step(0, "Confirm the detected study setup", "Correct only a wrong high-impact suggestion, then continue.")
    summary = st.columns(4)
    summary[0].metric("Study", TEXT.get(info.study_format, info.study_format))
    summary[1].metric("G-Sight files", len(result_inputs))
    proposed_split_count = len({_normal(item.split_name) for item in result_inputs})
    summary[2].metric("Consolidated splits", proposed_split_count)
    summary[3].metric("Active products", len(info.product_names))

    detected_format = info.study_format if info.study_format in {"HUT / in-use", "CLT"} else None
    study_format = st.segmented_control(
        "Study format", ["HUT / in-use", "CLT"],
        default=detected_format,
        key=f"detected_study_format_{key}",
        help="This confirmation describes the study. It does not alter source scores.",
    )
    if study_format == "HUT / in-use":
        test_type = st.segmented_control(
            "Analysis design", ["Monadic", "Paired"], default=saved_test_type,
            key=f"smart_test_type_{key}",
        )
    elif study_format == "CLT":
        test_type = "Monadic"
        block_design = st.segmented_control(
            "CLT block design — for the project record", ["Complete block", "Incomplete block"],
            default=settings.get("clt_block_design") if settings.get("clt_block_design") in {"Complete block", "Incomplete block"} else None,
            key=f"smart_clt_block_{key}",
        )
        st.caption("Please confirm if known. DataViz contains aggregated product tables, so this cannot be detected reliably and does not change the topline calculation.")
        detected_stages = [stage for stage in info.stages if str(stage).strip() and _normal(stage) not in {'not specified', 'non precise'}]
        saved_stages = settings.get('clt_stage_order') or settings.get('clt_stages', detected_stages)
        stage_selection_key = f'clt_stages_{key}'
        custom_stage_key = f'clt_custom_stage_{key}'
        stage_notice_key = f'clt_custom_stage_notice_{key}'
        if stage_selection_key not in st.session_state:
            st.session_state[stage_selection_key] = list(saved_stages)
        stage_options = list(dict.fromkeys([
            *detected_stages, *saved_stages, *st.session_state.get(stage_selection_key, []),
            'WET', 'NEAT', 'DRY',
        ]))
        clt_stages = st.multiselect(
            'Evaluated stages', options=stage_options,
            accept_new_options=True, key=stage_selection_key,
            help='Select the stages used in this study. You can also type a category-specific stage and press Enter.',
        )
        def add_custom_stage():
            new_stage = ' '.join(str(st.session_state.get(custom_stage_key, '')).split()).strip(' -_/')
            if not new_stage:
                return
            existing = list(st.session_state.get(stage_selection_key, []))
            if _normal(new_stage) not in {_normal(stage) for stage in existing}:
                st.session_state[stage_selection_key] = [*existing, new_stage]
                st.session_state[stage_notice_key] = f'Added stage: {new_stage}'
            else:
                st.session_state[stage_notice_key] = f'{new_stage} is already selected.'
            st.session_state[custom_stage_key] = ''

        add_stage_columns = st.columns([4, 1])
        add_stage_columns[0].text_input(
            'Add another stage', key=custom_stage_key,
            placeholder='Example: After application, Rinse, Skin dry-down…',
            help='Use the wording that appears in the question IDs, labels or sections.',
        )
        add_stage_columns[1].button(
            'Add stage', key=f'add_custom_stage_{key}', on_click=add_custom_stage,
            icon=':material/add:', use_container_width=True,
        )
        if st.session_state.get(stage_notice_key):
            st.caption(st.session_state.pop(stage_notice_key))
        # Read the widget state again because the Add callback runs before this rerun.
        clt_stages = list(st.session_state.get(stage_selection_key, clt_stages))
        stage_order_token = hashlib.sha1('|'.join(_normal(stage) for stage in clt_stages).encode('utf-8')).hexdigest()[:10]
        stage_question_counts = {stage: 0 for stage in clt_stages}
        for question in info.questions:
            question_stages = stages_for({
                'Question ID': question.question_id,
                'Display label': question.display_label,
                'Metric label': question.metric_label,
                'Section': question.section,
            }, clt_stages)
            matched_stages = {_normal(value) for value in question_stages}
            for stage in clt_stages:
                if _normal(stage) in matched_stages:
                    stage_question_counts[stage] += 1
        stage_order_frame = st.data_editor(
            pd.DataFrame({
                'Stage': clt_stages,
                'Questions found': [stage_question_counts[stage] for stage in clt_stages],
                'Order': list(range(1, len(clt_stages) + 1)),
            }),
            hide_index=True, width='stretch', disabled=['Stage', 'Questions found'], key=f'clt_stage_order_{key}_{stage_order_token}',
            column_config={
                'Stage': st.column_config.TextColumn('Stage block'),
                'Questions found': st.column_config.NumberColumn('Questions recognised', help='Questions whose ID, label or section explicitly contains this stage wording.'),
                'Order': st.column_config.NumberColumn('Block order shown in Excel', min_value=1, max_value=max(1, len(clt_stages)), step=1, required=True),
            },
        )
        clt_stage_order = stage_order_frame.sort_values('Order', kind='stable')['Stage'].astype(str).tolist()
        st.caption('Templyfier looks for these stage names in question IDs, labels and sections, then groups the matching questions into the selected block order. Unmatched questions remain visible for review.')
        custom_stages = [
            stage for stage in clt_stages
            if _normal(stage) not in {_normal(value) for value in [*detected_stages, 'WET', 'NEAT', 'DRY']}
        ]
        unmatched_custom_stages = [stage for stage in custom_stages if not stage_question_counts[stage]]
        if unmatched_custom_stages:
            st.warning(
                'No question wording currently matches: ' + ', '.join(unmatched_custom_stages)
                + '. Check the spelling used in the G-Sight question IDs or labels. The stage remains selected.',
                icon=':material/search_off:',
            )
    else:
        test_type = saved_test_type
        block_design = "unknown"
        clt_stages, clt_stage_order = [], []
        st.warning("Study format was not detected confidently. Choose HUT / in-use or CLT to continue.", icon=":material/warning:")

    detected_codes = list(dict.fromkeys(code for item in result_inputs for code in item.comparison_codes))
    benchmark_count_detected = len(detected_codes) or int(info.suggested_benchmark_count)
    candidate_count = max(0, len(info.product_names) - benchmark_count_detected)
    st.caption(f"Detected plan: {benchmark_count_detected} benchmark(s) · {candidate_count} candidate(s) · {len(result_inputs)} files → {proposed_split_count} splits after consolidation.")

    split_table = st.data_editor(
        state["splits"], hide_index=True, width="stretch",
        disabled=["Fichier", "Stage", "Split detection", "Benchmark détecté", "Bases"],
        column_order=["Nom de l’onglet", "Split detection", "Benchmark détecté", "Fichier", "Stage", "Bases"],
        column_config={
            "Fichier": st.column_config.TextColumn("Source file", width="large"),
            "Nom de l’onglet": st.column_config.TextColumn("Split name shown in Excel", required=True, width="medium"),
            "Stage": st.column_config.TextColumn(width="small"),
            "Split detection": st.column_config.TextColumn("Confidence", width="medium"),
            "Benchmark détecté": st.column_config.TextColumn("Benchmark found", width="medium"),
            "Bases": st.column_config.TextColumn(width="large"),
        }, key=f"smart_splits_{key}",
    )
    uncertain = int(split_table["Split detection"].astype(str).eq("Review recommended").sum())
    if uncertain:
        st.warning(f"{uncertain} split name(s) need checking. Correct the name shown in Excel before continuing.", icon=":material/warning:")
    else:
        st.caption("All split names have high-confidence detection. You can still edit a name.")
    compatibility_issues = []
    if uncertain:
        compatibility_issues.append(f'{uncertain} split name(s)')
    if study_format is None:
        compatibility_issues.append('study format')
    if study_format == 'CLT' and not locals().get('clt_stages'):
        compatibility_issues.append('evaluated stages')
    if compatibility_issues:
        st.warning('File compatibility — please check: ' + ', '.join(compatibility_issues) + '.', icon=':material/rule:')
    else:
        st.success('File compatibility — ready. The study structure, splits and stages needed for this project were recognised.', icon=':material/check_circle:')
    with st.expander("Source details — optional"):
        st.write(f"Stages found: {' · '.join(info.stages) or 'Not specified'}")
        st.dataframe(pd.DataFrame({
            "Source file": [item.filename for item in info.inputs],
            "Stage": [item.stage for item in info.inputs],
            "Tables": [item.embedded_split_count for item in info.inputs],
            "Comparison codes": [" · ".join(item.comparison_codes) or "—" for item in info.inputs],
        }), hide_index=True, width="stretch")
    detection_signature = hashlib.sha1((str(study_format) + str(test_type) +
        split_table["Nom de l’onglet"].astype(str).str.strip().str.casefold().str.cat(sep="|") +
        str(locals().get("block_design", "")) + '|'.join(locals().get('clt_stage_order', []))).encode("utf-8")).hexdigest()
    if st.session_state.get(f"{gate_prefix}_detection_signature") not in {None, detection_signature}:
        st.session_state[f"{gate_prefix}_detection"] = False
        st.session_state[f"{gate_prefix}_structure"] = False
        st.session_state[f"{gate_prefix}_questions"] = False
    st.session_state[f"{gate_prefix}_detection_signature"] = detection_signature
    if st.button("Confirm study setup", type="primary", key=f"confirm_detection_{key}", icon=":material/check_circle:", disabled=study_format is None):
        st.session_state[f"{gate_prefix}_detection"] = True
    detection_confirmed = qa_skip_gates or bool(st.session_state.get(f"{gate_prefix}_detection"))
    if not detection_confirmed:
        st.caption("Confirm this setup to continue. Later settings remain hidden so the screen stays focused.")
        st.stop()

    _step(1, "Choose the Excel structure", "Two choices define the default workbook. Everything else is optional.")
    saved_mode = settings.get("benchmark_sheet_mode", "auto_columns")
    benchmark_layout = st.segmented_control(
        "Benchmark layout",
        ["Benchmarks side by side", "Separate benchmark worksheets"],
        default="Benchmarks side by side" if saved_mode in {"combined", "auto_columns", "benchmark_columns"} else "Separate benchmark worksheets",
        key=f"smart_benchmark_layout_{key}",
        help="Side by side creates one worksheet per split. Separate creates one worksheet per split and benchmark.",
    )
    mean_decimals = st.segmented_control(
        "Mean precision", [0, 1, 2], default=int(settings.get("mean_decimals", 0)),
        format_func=lambda value: "0 decimals" if value == 0 else f"{value} decimal" + ("s" if value > 1 else ""),
        key=f"smart_mean_decimals_{key}",
    )
    st.caption("Recommended defaults: benchmarks side by side and 0 decimals, matching the current Templyfier output convention.")
    structure_signature = f"{benchmark_layout}|{mean_decimals}"
    if st.session_state.get(f"{gate_prefix}_structure_signature") not in {None, structure_signature}:
        st.session_state[f"{gate_prefix}_structure"] = False
        st.session_state[f"{gate_prefix}_questions"] = False
    st.session_state[f"{gate_prefix}_structure_signature"] = structure_signature
    if st.button("Confirm Excel structure", type="primary", key=f"confirm_structure_{key}", icon=":material/check_circle:"):
        st.session_state[f"{gate_prefix}_structure"] = True
    structure_confirmed = qa_skip_gates or bool(st.session_state.get(f"{gate_prefix}_structure"))
    if not structure_confirmed:
        st.caption("Confirm these two choices to review questions and metrics.")
        st.stop()

    _step(2, "Vérifie le contenu proposé", "Vérifie les types, les groupes et les métriques dans l’éditeur ci-dessous.")
    with st.expander("How Templyfier prepared this review"):
        normalized_stages = {str(stage).strip().casefold().replace('-', ' ') for stage in locals().get('clt_stage_order', info.stages)}
        wet_only = bool(normalized_stages) and normalized_stages.issubset({'wet', 'damp wet'})
        if study_format == "CLT" and wet_only:
            st.caption(
                "Suggested order for this WET-only study: Overall Fragrance Opinion first, then Strength, "
                "followed by descriptor batteries from broad perceptions to more specific details. "
                "No NEAT section is proposed because no NEAT export was detected."
            )
        elif study_format == "CLT":
            st.caption(
                "Ordre proposé : résultats sur le produit dilué/WET → bénéfices associés → description du parfum et du type de fraîcheur "
                "→ couleurs et adéquation au produit → parfum pur/NEAT. Les listes d’attributs sont regroupées sous une seule variable."
            )
        else:
            st.caption(
                "Ordre proposé : opinion globale sur le produit → intention d’achat et attentes → performance et bénéfices → "
                "opinion globale sur le parfum → appréciation et intensité aux différents moments d’utilisation → "
                "description du parfum, émotions et couleurs associées."
            )
        st.caption(
            "Les questions d’usage techniques sont proposées décochées. Les numéros Q-… sont retirés des labels, "
            "mais le wording du questionnaire est conservé. Toutes les propositions restent modifiables."
        )
    review_count = int(state["questions"]["CMI note"].fillna("").astype(str).str.contains("À confirmer").sum())
    if review_count:
        st.warning(
            f"{review_count} question(s) dépendent particulièrement de l’objectif du projet, par exemple une comparaison au produit actuel "
            "ou une question de préférence. Elles sont gardées pour le moment afin de ne perdre aucune donnée. "
            "Si elles ne sont pas utiles pour cette étude, décoche Garder dans le tableau ci-dessous.",
            icon="💡",
        )
    comparison = state.get('profile_comparison')
    if comparison:
        st.info(f"Profil repris : {comparison['matched']} question(s) retrouvée(s), {comparison['new']} nouvelle(s), {comparison['absent']} absente(s) de ces exports.")
        if comparison['details']:
            with st.expander('Voir les différences avec le profil chargé', expanded=True):
                st.dataframe(pd.DataFrame(comparison['details']), hide_index=True, width='stretch')
                st.caption('Les questions nouvelles reçoivent des propositions. Les anciennes questions absentes ne sont pas exportées. Les métriques devenues indisponibles doivent être corrigées avant génération.')
    standard_metrics = settings.get("standard_metrics", ["Mean", "Top Box", "Top 2 Boxes", "Bottom 2 Boxes"])
    question_table = render_question_editor(state["questions"], info.questions, key,
        memory=client_memory, protected_ids=state.get('profile_protected_ids', []), project_key=_files_key(exports),
        show_optional=False, stage_order=locals().get('clt_stage_order', []))
    with st.expander("Optional explanation — how Templyfier prepared the recommendations"):
        explanation_frame = question_table.copy()
        summary_reco = explanation_frame[
            explanation_frame["Keep"].astype(bool) & explanation_frame["KPI Summary"].astype(bool)
        ]
        topline_reco = explanation_frame[
            explanation_frame["Keep"].astype(bool) & ~explanation_frame["KPI Summary"].astype(bool)
        ]
        review_reco = explanation_frame[
            explanation_frame["CMI note"].fillna("").astype(str).str.contains("confirmer", case=False)
            | ~explanation_frame["Keep"].astype(bool)
        ]
        reco_tabs = st.tabs(["KPI de synthèse", "Toplines détaillées", "À vérifier ou retirer"])
        for tab, frame in zip(reco_tabs, (summary_reco, topline_reco, review_reco)):
            with tab:
                st.dataframe(
                    frame[["Display label", "CMI role", "CMI note", "Availability"]].rename(columns={
                        "Display label": "Question clean",
                        "CMI role": "Utilité proposée",
                        "CMI note": "Pourquoi / point d’attention",
                        "Availability": "Présence",
                    }),
                    hide_index=True,
                    width="stretch",
                )

    # Ordering is optional and occurs after this gate. Do not send the user back
    # to metric review when a drag-and-drop changes only the Order column.
    question_signature = _question_content_signature(question_table)
    if st.session_state.get(f"{gate_prefix}_question_signature") not in {None, question_signature}:
        st.session_state[f"{gate_prefix}_questions"] = False
        st.session_state[f"smart_verified_{key}"] = False
    st.session_state[f"{gate_prefix}_question_signature"] = question_signature
    if st.button("Confirm questions and metrics", type="primary", key=f"confirm_questions_{key}", icon=":material/check_circle:"):
        st.session_state[f"{gate_prefix}_questions"] = True
        st.session_state[f"smart_verified_{key}"] = True
    questions_confirmed = qa_skip_gates or bool(st.session_state.get(f"{gate_prefix}_questions"))
    if not questions_confirmed:
        st.caption("Confirm the current proposal to generate with these defaults. Detailed edits remain available above.")
        st.stop()

    quick_generate_slot = st.empty()
    _step(3, "Change the question order — optional", "The proposed order is ready. Open this only if the project needs a different story.")
    with st.expander("Drag questions or groups to reorder them", expanded=False):
        question_table = render_optional_question_tools(
            key, client_memory, state.get('profile_protected_ids', []), _files_key(exports),
            include_reorder=True, include_grouping=False,
            stage_order=locals().get('clt_stage_order', []),
        )

    _step(4, "Advanced options — optional", "Open only the settings that solve a specific project need.")
    render_optional_question_tools(
        key, client_memory, state.get('profile_protected_ids', []), _files_key(exports),
        include_reorder=False, include_grouping=True,
        stage_order=locals().get('clt_stage_order', []),
    )
    st.caption("Product naming, benchmark labels and optional reporting controls remain available below.")

    product_options = {
        f"{index + 1}. {name[:70]}": index
        for index, name in enumerate(info.product_names)
    }
    result_inputs = [item for item in info.inputs if item.role == "Résultats"] or list(info.inputs)
    canonical_keys = result_inputs[0].product_keys
    cmr_matches = state.get("cmr_matches", ())
    saved_product_labels = settings.get("product_labels", [])
    saved_product_subtitles = settings.get("product_subtitles", [])
    with st.expander("Clean product headers — optional", expanded=False):
        st.caption(
            "Le code stable sert au rapprochement technique. Le nom et la ligne complémentaire servent uniquement au rendu Excel."
        )
        if cmr_matches:
            cmr_name_options = {
                "Fantasy name (recommandé)": "fantasy",
                "Formula description": "description",
                "Formula code": "formula",
                "Conserver le nom G-Sight": "source",
            }
            saved_cmr_mode = settings.get("cmr_name_mode", "fantasy")
            cmr_name_choice = st.radio(
                "Quel nom veux-tu afficher dans les toplines ?",
                list(cmr_name_options),
                horizontal=True,
                index=list(cmr_name_options.values()).index(saved_cmr_mode)
                if saved_cmr_mode in cmr_name_options.values() else 0,
                key=f"smart_cmr_name_mode_{key}",
            )
            cmr_name_mode = cmr_name_options[cmr_name_choice]
            st.caption("Le choix est appliqué à tous les produits, puis reste modifiable ligne par ligne dans Nom affiché.")
        else:
            cmr_name_mode = "source"
        product_rows = []
        for index, (code, source_name) in enumerate(zip(canonical_keys, info.product_names)):
            cmr_match = cmr_matches[index] if index < len(cmr_matches) else None
            cmr_default = (
                cmr_product_label(cmr_match, cmr_name_mode)
                if cmr_match and cmr_match.score >= 80
                else source_name
            )
            product_row = {
                "Code stable": code,
                "Nom source": source_name,
                "Nom affiché": (
                    cmr_default
                    if cmr_matches
                    else saved_product_labels[index] if index < len(saved_product_labels) else source_name
                ),
                "Ligne complémentaire / formule": (
                    saved_product_subtitles[index]
                    if index < len(saved_product_subtitles)
                    else ""
                ),
            }
            if cmr_matches:
                product_row.update({
                    "Valeur CMR sélectionnée": cmr_default,
                    "Match CMR": cmr_match.matched_by if cmr_match else "—",
                    "Confiance CMR": cmr_match.confidence if cmr_match else "—",
                })
            product_rows.append(product_row)
        disabled_product_columns = ["Code stable", "Nom source"]
        product_column_config = {
            "Code stable": st.column_config.TextColumn(width="small"),
            "Nom source": st.column_config.TextColumn(width="large"),
            "Nom affiché": st.column_config.TextColumn(required=True, width="large"),
            "Ligne complémentaire / formule": st.column_config.TextColumn(width="large"),
        }
        if cmr_matches:
            disabled_product_columns.extend(
                ["Valeur CMR sélectionnée", "Match CMR", "Confiance CMR"]
            )
            product_column_config.update({
                "Valeur CMR sélectionnée": st.column_config.TextColumn(width="large"),
                "Match CMR": st.column_config.TextColumn(width="medium"),
                "Confiance CMR": st.column_config.TextColumn(width="small"),
            })
        product_columns = ["Code stable", "Nom source"]
        if cmr_matches:
            product_columns.extend(["Valeur CMR sélectionnée", "Match CMR", "Confiance CMR"])
        product_columns.extend(["Nom affiché", "Ligne complémentaire / formule"])
        product_table = st.data_editor(
            pd.DataFrame(product_rows, columns=product_columns),
            hide_index=True,
            width="stretch",
            disabled=disabled_product_columns,
            column_config=product_column_config,
            column_order=['Nom affiché','Ligne complémentaire / formule','Code stable','Nom source'],
            key=f"smart_product_headers_{key}_{cmr_name_mode}",
        )
        if cmr_matches:
            matched_count = sum(
                item.score >= 80 and bool(cmr_product_label(item, cmr_name_mode))
                for item in cmr_matches
            )
            st.success(
                f"{matched_count}/{len(cmr_matches)} produit(s) rapproché(s) automatiquement de la CMR. "
                "Les noms proposés sont préremplis, mais la colonne Nom affiché reste la décision finale du CMI.",
                icon="✨",
            )
    clean_product_labels = product_table["Nom affiché"].fillna("").astype(str).str.strip().tolist()
    clean_product_subtitles = product_table["Ligne complémentaire / formule"].fillna("").astype(str).str.strip().tolist()
    product_headers_ready = all(clean_product_labels)
    if not product_headers_ready:
        st.error("Chaque produit doit conserver un nom affiché.")
    if test_type == "Monadic":
        detected_codes = list(dict.fromkeys(
            code for item in result_inputs for code in item.comparison_codes if code in canonical_keys
        ))
        detected_positions = [canonical_keys.index(code) for code in detected_codes]
        detected_option_labels = [list(product_options)[position] for position in detected_positions]
        source_choices = (
            ["Détecter depuis les exports (recommandé)", "Choisir manuellement"]
            if detected_positions else ["Choisir manuellement"]
        )
        saved_source = settings.get("benchmark_source", "auto" if detected_positions else "manual")
        benchmark_source_label = st.radio(
            "Identification des benchmarks",
            source_choices,
            horizontal=True,
            index=0 if saved_source == "auto" or len(source_choices) == 1 else 1,
            help=(
                "En automatique, chaque fichier est associé au benchmark indiqué par la colonne de comparaison G-Sight. "
                "Les fichiers d’un même split sont ensuite consolidés, même si l’ordre des produits change."
            ),
            key=f"smart_benchmark_source_{key}",
        )
        benchmark_source = "auto" if benchmark_source_label.startswith("Détecter") and detected_positions else "manual"
        if benchmark_source == "auto":
            benchmark_labels = detected_option_labels
            benchmark_sheet_mode = "auto_exports"
            st.success(
                f"{len(benchmark_labels)} benchmark(s) détecté(s) dans les exports : "
                + " · ".join(detected_codes),
                icon="🧩",
            )
            st.caption(
                "Any number of benchmarks is supported. Choose the worksheet layout below."
            )
        else:
            suggested_count = min(max(1, int(settings.get("benchmark_count", info.suggested_benchmark_count))), len(product_options))
            saved_keys=settings.get('benchmark_keys')
            labels_by_code={canonical_keys[position]:label for label,position in product_options.items()}
            restored_benchmarks=[labels_by_code[code] for code in (saved_keys or []) if code in labels_by_code]
            if saved_keys is not None and len(restored_benchmarks)!=len(saved_keys):
                st.warning('Some saved benchmark codes are absent. Review benchmark selection before exporting; no substitute benchmark is chosen automatically.')
            benchmark_labels = st.multiselect(
                "Benchmark(s)",
                list(product_options),
                default=restored_benchmarks if saved_keys is not None else list(product_options)[:suggested_count],
                key=f"smart_benchmarks_{key}",
            )
            benchmark_sheet_mode = "combined"
        benchmark_count = len(benchmark_labels)
        columns = benchmark_layout == "Benchmarks side by side"
        benchmark_sheet_mode = ('auto_columns' if columns else 'auto_exports') if benchmark_source == 'auto' else ('benchmark_columns' if columns else 'separate')
        st.caption('Excel layout confirmed in Step 1: benchmarks side by side.' if columns else 'Excel layout confirmed in Step 1: separate benchmark worksheets.')
        if benchmark_count < 2:
            st.caption('Only one benchmark is selected: both layouts contain a single reading.')
        with st.expander('Preview benchmark layouts — schematic, no consumer values'):
            st.caption('The same variable/metric rows are shared on the left in consolidated mode. Scores repeat per comparison so each benchmark keeps its own significance, even with gaps off.')
            example_names = list(benchmark_labels)[:4] or ['Benchmark 1','Benchmark 2']
            st.markdown('**Columns on one sheet per split**')
            panels={'Variable / metric':['Overall opinion / Mean','Purchase intent / Top 2 Boxes']}
            for label in example_names:panels[f'Comparison vs {label}']=['Candidate scores · own significance · optional gaps']*2
            st.dataframe(pd.DataFrame(panels),hide_index=True,width='stretch')
            st.markdown('**Separate sheets**')
            st.dataframe(pd.DataFrame({'Worksheet':[f'TOTAL vs {label}' for label in example_names],
                'Contents':['Scores · significance vs this benchmark · optional gaps']*len(example_names)}),hide_index=True,width='stretch')
            if len(benchmark_labels)>4:st.caption('Only the first four benchmarks are illustrated; the export includes all available selected comparisons.')
        benchmark_short_labels = []
        if benchmark_labels:
            saved_short_labels = settings.get("benchmark_labels", [])
            label_rows = []
            for offset, label in enumerate(benchmark_labels):
                product_position = product_options[label]
                product_name = clean_product_labels[product_position] or info.product_names[product_position]
                label_rows.append({
                    "Benchmark": product_name,
                    "Nom court pour l’onglet": (
                        saved_short_labels[offset] if offset < len(saved_short_labels) else product_name
                    ),
                })
            label_table = st.data_editor(
                pd.DataFrame(label_rows, columns=["Benchmark", "Nom court pour l’onglet"]),
                hide_index=True,
                width="stretch",
                disabled=["Benchmark"],
                column_config={
                    "Benchmark": st.column_config.TextColumn(width="large"),
                    "Nom court pour l’onglet": st.column_config.TextColumn(required=True, width="medium"),
                },
                key=f"smart_benchmark_short_labels_{key}",
            )
            benchmark_short_labels = label_table["Nom court pour l’onglet"].astype(str).str.strip().tolist()
            st.caption(
                "Ces noms servent uniquement aux onglets. Les produits sont rapprochés grâce à leurs codes stables, pas à leur position A/B/F."
            )
        paired_swaps = {}
    else:
        benchmark_count = 0
        benchmark_source = "manual"
        benchmark_labels = []
        benchmark_short_labels = []
        benchmark_sheet_mode = "combined"
        pair_rows = []
        saved_swaps = settings.get("paired_swaps", {})
        for item in info.inputs:
            if item.role != "Résultats" and any(candidate.role == "Résultats" for candidate in info.inputs):
                continue
            for position in range(0, len(item.product_names) - 1, 2):
                pair_rows.append({
                    "Fichier": item.filename,
                    "Split": item.split_name,
                    "Paire": position // 2 + 1,
                    "Benchmark": item.product_names[position],
                    "Candidat": item.product_names[position + 1],
                    "Inverser": position // 2 + 1 in saved_swaps.get(item.filename, []),
                })
        st.caption(
            "Plan Paired détecté — chaque paire doit être Benchmark puis Candidat. "
            "Les splits peuvent avoir un nombre de paires actives différent."
        )
        pair_table = st.data_editor(
            pd.DataFrame(
                pair_rows,
                columns=["Fichier", "Split", "Paire", "Benchmark", "Candidat", "Inverser"],
            ),
            hide_index=True,
            width="stretch",
            disabled=["Fichier", "Split", "Paire", "Benchmark", "Candidat"],
            column_config={
                "Fichier": st.column_config.TextColumn(width="large"),
                "Inverser": st.column_config.CheckboxColumn(
                    "Inverser Benchmark/Candidat",
                    help="Inverse le sens de cette paire et recalcule le delta dans le bon sens.",
                ),
            },
            key=f"smart_pairs_{key}",
        )
        paired_swaps = {
            filename: group.loc[group["Inverser"].astype(bool), "Paire"].astype(int).tolist()
            for filename, group in pair_table.groupby("Fichier")
        }

    benchmark_positions = tuple(product_options[label] for label in benchmark_labels)
    audit = audit_input_plan(
        info,
        split_table["Nom de l’onglet"].astype(str).str.strip().tolist(),
        benchmark_positions,
        test_type=test_type,
        automatic_exports=test_type == "Monadic" and benchmark_sheet_mode in {"auto_exports","auto_columns"},
    )
    if audit['ready']:
        if test_type=='Monadic' and benchmark_sheet_mode in {'auto_exports','auto_columns'}:
            split_count=len({_normal(name) for name in split_table["Nom de l’onglet"].astype(str) if str(name).strip()})
            expected=split_count*len(benchmark_positions)
            matched=sum(row['Contrôle']=='Prêt' for row in audit['rows'])
            st.success(f'Input plan ready — {split_count} split(s) × {len(benchmark_positions)} benchmark(s): {matched}/{expected} exports matched.')
        else:
            st.success(f'Input plan ready — {len(audit["rows"])} result file(s) checked.')
    else:
        st.error(f'Input plan needs attention — {len(audit["blockers"])} issue(s) must be corrected before generation.')
    with st.expander("Contrôle des fichiers et des comparaisons", expanded=not audit["ready"]):
        st.dataframe(pd.DataFrame(audit["rows"]), hide_index=True, width="stretch")
        if audit["blockers"]:
            st.error("\n\n".join(f"• {message}" for message in audit["blockers"]))
        elif audit["warnings"]:
            st.warning("\n\n".join(f"• {message}" for message in audit["warnings"]))
        else:
            st.success("Toutes les combinaisons demandées sont présentes et les plans produits sont cohérents.", icon="✅")

    (
        mean_decimals,
        include_screeners,
        include_sections,
        include_deltas,
        output_sheet_order,
        show_monadic_gaps,
        highlight_benchmarks,
    ) = _output_options(settings, key, test_type, mean_decimals)

    with st.expander('KPI summary — optional settings'):
        st.markdown("##### KPI Summary")
        st.caption(
            "Le Templyfier présélectionne les KPI les plus décisionnels et écarte par défaut les questions techniques, "
            "les touchpoints détaillés, les batteries d’attributs et les couleurs. La colonne KPI Summary reste entièrement modifiable."
        )
        saved_summary_scope = settings.get("summary_scope", "total")
        summary_scope_label = st.radio(
            "Où créer le tableau de synthèse ?",
            ["TOTAL uniquement (recommandé)", "Tous les splits", "Ne pas ajouter de KPI Summary"],
            horizontal=True,
            index={"total": 0, "all": 1, "none": 2}.get(saved_summary_scope, 0),
            key=f"smart_summary_scope_{key}",
            help=(
                "Avec plusieurs benchmarks, un onglet Summary est créé par benchmark. "
                "En Tous les splits, les tableaux sont empilés dans ces onglets pour éviter de multiplier les feuilles."
            ),
        )
        summary_scope = (
            "total" if summary_scope_label.startswith("TOTAL")
            else "all" if summary_scope_label.startswith("Tous")
            else "none"
        )
        strategy_options = {
            "Priorité CMI (recommandé)": "priority",
            "Métrique principale uniquement": "primary",
            "Consensus entre les métriques": "consensus",
        }
        saved_strategy = settings.get("summary_metric_strategy", "priority")
        strategy_labels = list(strategy_options)
        strategy_index = next(
            (index for index, label in enumerate(strategy_labels) if strategy_options[label] == saved_strategy),
            0,
        )
        summary_strategy_label = st.radio(
            "Comment résumer plusieurs métriques significatives ?",
            strategy_labels,
            index=strategy_index,
            horizontal=True,
            key=f"smart_summary_strategy_{key}",
            help=(
                "Priorité CMI utilise Mean puis Top 2 puis Top Box. Métrique principale ignore les autres métriques. "
                "Consensus affiche ± lorsque les métriques significatives se contredisent."
            ),
        )
        summary_metric_strategy = strategy_options[summary_strategy_label]
        include_summary_details = st.checkbox(
            "Ajouter l’onglet explicatif KPI Details",
            value=bool(settings.get("include_summary_details", True)),
            key=f"smart_summary_details_{key}",
            help="Cet onglet indique les deux valeurs comparées, le gap, la métrique retenue et la raison de chaque symbole.",
            disabled=summary_scope == "none",
        )
        summary_kpis = question_table[
            question_table["Keep"].astype(bool)
            & question_table["Type"].ne("Delete")
            & question_table["KPI Summary"].astype(bool)
        ]
        if summary_scope != "none":
            st.info(f"{len(summary_kpis)} KPI(s) sélectionné(s) pour la synthèse.", icon="📊")
            if summary_kpis.empty:
                st.error("Sélectionne au moins un KPI dans la colonne KPI Summary, ou désactive la synthèse.")

    profile_settings = {
        "standard_metrics": standard_metrics,
        "benchmark_count": benchmark_count,
        "benchmark_source": benchmark_source,
        "benchmark_sheet_mode": benchmark_sheet_mode,
        "benchmark_labels": benchmark_short_labels,
        "benchmark_keys": [canonical_keys[product_options[label]] for label in benchmark_labels],
        "include_screeners": include_screeners,
        "study_format": study_format,
        "clt_block_design": locals().get("block_design", "unknown"),
        "clt_stages": locals().get("clt_stages", []),
        "clt_stage_order": locals().get("clt_stage_order", []),
        "test_type": test_type,
        "mean_decimals": mean_decimals,
        "paired_swaps": paired_swaps,
        "include_sections": include_sections,
        "include_deltas": include_deltas,
        "output_sheet_order": output_sheet_order,
        "show_monadic_gaps": show_monadic_gaps,
        "highlight_benchmarks": highlight_benchmarks,
        "product_labels": clean_product_labels,
        "product_subtitles": clean_product_subtitles,
        "cmr_name_mode": cmr_name_mode,
        "summary_scope": summary_scope,
        "summary_metric_strategy": summary_metric_strategy,
        "include_summary_details": include_summary_details,
    }
    profile_bytes = profile_to_json(question_table.to_dict("records"), profile_settings)
    configuration_hash = hashlib.sha256(profile_bytes + split_table.to_json().encode()).hexdigest()
    previous_configuration_hash = st.session_state.get(f"smart_configuration_{key}")
    if previous_configuration_hash != configuration_hash:
        st.session_state[f"smart_configuration_{key}"] = configuration_hash
        st.session_state.pop(f"smart_result_{key}", None)
        st.session_state.pop(f"smart_report_{key}", None)
        # Step 2 is already an explicit confirmation. Keep it on the first
        # default render; require reconfirmation only after a later edit.
        if previous_configuration_hash is not None:
            st.session_state[f"smart_verified_{key}"] = False
    st.subheader("Final readiness check")
    st.caption("Existing safety checks still apply before any Excel file can be generated.")
    kept = question_table[question_table["Keep"].astype(bool) & question_table["Type"].ne("Delete")]
    low_confidence = kept[kept["Confidence"].eq("Faible")]
    names = split_table["Nom de l’onglet"].astype(str).str.strip()
    duplicates = names[names.str.casefold().duplicated(keep=False)].tolist()
    result_inputs = [item for item in info.inputs if item.role == "Résultats"] or list(info.inputs)
    auto_consolidation = test_type == "Monadic" and benchmark_sheet_mode in {"auto_exports","auto_columns"}
    products_match = all(
        (set(item.product_keys) == set(result_inputs[0].product_keys) if auto_consolidation else item.product_keys == result_inputs[0].product_keys)
        for item in result_inputs
    )
    paired_plans_valid = all(len(item.product_keys) >= 2 and len(item.product_keys) % 2 == 0 for item in result_inputs)
    empty_standard_recipes = question_table[
        question_table["Keep"].astype(bool)
        & question_table["Selected metrics"].apply(lambda value: not value)
    ]

    unique_splits = list(dict.fromkeys(names.tolist()))
    planned_topline_sheets = []
    if test_type == "Paired":
        planned_topline_sheets = unique_splits
    elif benchmark_sheet_mode in {"auto_exports", "separate"}:
        combinations = (
            ((split, label) for label in benchmark_short_labels for split in unique_splits)
            if output_sheet_order == "benchmark_first"
            else ((split, label) for split in unique_splits for label in benchmark_short_labels)
        )
        planned_topline_sheets = [f"{split} vs {label}" for split, label in combinations]
    else:
        planned_topline_sheets = unique_splits
    planned_summary_sheets = []
    if summary_scope != "none":
        if test_type == "Paired" or len(benchmark_short_labels) <= 1:
            planned_summary_sheets = ["KPI Summary"]
        else:
            planned_summary_sheets = [f"KPI Summary vs {label}" for label in benchmark_short_labels]
        if include_summary_details:
            planned_summary_sheets.append("KPI Details")
    with st.expander("Final file preview — optional", expanded=False):
        preview_cols = st.columns(3)
        preview_cols[0].metric("Onglets toplines prévus", len(planned_topline_sheets))
        preview_cols[1].metric("Onglets de synthèse", len(planned_summary_sheets))
        preview_cols[2].metric("Questions gardées", len(kept))
        st.write("**Toplines :** " + " · ".join(planned_topline_sheets))
        if planned_summary_sheets:
            st.write("**Synthèse :** " + " · ".join(planned_summary_sheets))
        st.caption(
            f"Produits affichés : {' · '.join(clean_product_labels)} · "
            f"Méthode KPI : {summary_strategy_label}."
        )
        if audit["warnings"]:
            st.warning("Points à connaître : " + " · ".join(audit["warnings"]))

    available_by_id = {p.question_id:p.metrics for p in info.questions}
    metric_availability_by_id = {p.question_id:{metric:list(files) for metric,files in p.metric_availability} for p in info.questions}
    question_audit = audit_questions(question_table.to_dict('records'), available_by_id, names.tolist())
    render_structure_preview(question_table.to_dict('records'), available_by_id, names.tolist(), key,
        metric_availability_by_id, len(result_inputs))
    pending_metrics = bool(st.session_state.get(f'metric_batch_{key}'))
    if question_audit['blockers']:
        st.error(f"{len({i['Question ID'] for i in question_audit['blockers']})} question(s) à corriger avant export : métriques, libellés ou filtre de splits.")
        with st.expander('Détail des corrections nécessaires', expanded=True):
            st.dataframe(pd.DataFrame(question_audit['blockers']).drop(columns=['Code']), hide_index=True, width='stretch')
    if pending_metrics:
        st.warning('Un changement groupé de métriques attend ta décision dans l’éditeur. Confirme-le ou abandonne son aperçu avant de générer ou télécharger.')

    if low_confidence.empty:
        verification_label = "J’ai vérifié les propositions et je valide cette configuration"
    else:
        verification_label = f"J’ai vérifié les {len(low_confidence)} proposition(s) à faible confiance"
    verified = st.checkbox(verification_label, key=f"smart_verified_{key}")

    if duplicates and not auto_consolidation:
        st.error(f"Noms d’onglets en double : {', '.join(sorted(set(duplicates)))}")
    if test_type == "Monadic" and not products_match:
        st.error("Le plan produits n’est pas identique dans tous les exports.")
    if test_type == "Paired" and not paired_plans_valid:
        st.error("Chaque split Paired doit contenir un nombre pair de produits actifs : Benchmark puis Candidat.")
    if not empty_standard_recipes.empty:
        st.error(f"{len(empty_standard_recipes)} question(s) gardée(s) n’ont aucune métrique cochée.")
    incomplete_comparisons = [
        item.split_name for item in result_inputs
        if len(item.comparison_codes) < benchmark_count
    ] if test_type == "Monadic" and not auto_consolidation else []
    if incomplete_comparisons:
        st.info(
            "Comparaisons sans colonne Delta dédiée pour : " + ", ".join(incomplete_comparisons)
            + ". Le Templyfier utilisera les lettres G-Sight, benchmark par benchmark, pour restituer la significativité."
        )

    ready = (
        verified
        and (test_type == "Paired" or products_match)
        and len(kept) > 0
        and (not duplicates or auto_consolidation)
        and names.ne("").all()
        and (test_type == "Paired" or benchmark_count > 0)
        and (test_type == "Paired" or all(benchmark_short_labels))
        and (test_type == "Monadic" or paired_plans_valid)
        and empty_standard_recipes.empty
        and product_headers_ready
        and (summary_scope == "none" or not summary_kpis.empty)
        and audit["ready"]
        and question_audit["ready"]
        and not pending_metrics
    )
    if ready:
        st.success('Ready to generate. Your reviewed choices will be used in the Excel workbook.')
    else:
        next_steps=[]
        if pending_metrics:next_steps.append('Confirm or cancel the pending metric batch in step 2.')
        if not question_audit['ready'] or not empty_standard_recipes.empty:next_steps.append('In step 2, correct the marked questions and keep at least one source metric for each retained question.')
        if not audit['ready']:next_steps.append('In Advanced options, open File and comparison checks and correct the reported issue.')
        if not names.ne('').all() or (duplicates and not auto_consolidation):next_steps.append('In Step 0, provide valid split names; manual split names must be unique.')
        if not product_headers_ready:next_steps.append('In Advanced options, give every product a display name.')
        if test_type=='Monadic' and (not products_match or benchmark_count==0 or not all(benchmark_short_labels)):next_steps.append('In Advanced options, check the product plan, select a benchmark and name each reading.')
        if test_type=='Paired' and not paired_plans_valid:next_steps.append('In Advanced options, check that every pair contains a benchmark and a candidate.')
        if summary_scope!='none' and summary_kpis.empty:next_steps.append('In Advanced options, select a summary KPI or turn off the KPI summary.')
        if not verified:next_steps.append('In step 4, review the final preview and tick the confirmation box above.')
        if next_steps:st.info('What to do next\n\n'+ '\n'.join(f'{i}. {item}' for i,item in enumerate(next_steps,1)))

    with quick_generate_slot.container(border=True):
        st.markdown('**Your Excel at a glance**')
        quick_summary = st.columns(4)
        quick_summary[0].metric('Questions', len(kept))
        quick_summary[1].metric('Splits', len(unique_splits))
        quick_summary[2].metric('Benchmarks', benchmark_count if test_type == 'Monadic' else 'Paired')
        quick_summary[3].metric('Worksheets', len(planned_topline_sheets) + len(planned_summary_sheets))
        st.caption('Generate with the confirmed defaults. Optional ordering and advanced settings can be skipped.')
        quick_generate = st.button('Generate now', type='primary', width='stretch', disabled=not ready,
            key=f'smart_generate_quick_{key}', icon=':material/play_arrow:')
    with sidebar_generate_slot:
        sidebar_generate = st.button('Generate now', type='primary', width='stretch', disabled=not ready,
            key=f'smart_generate_sidebar_{key}', icon=':material/play_arrow:')

    output_name = st.text_input("Nom du fichier final", "Toplines_clean.xlsx", key=f"smart_output_{key}")
    navigation_status.progress(1.0 if ready else .75, text='Prêt à générer' if ready else 'Vérifie le contenu et confirme l’aperçu final')
    if not output_name.lower().endswith(".xlsx"):
        output_name += ".xlsx"

    final_generate = st.button("Generate my toplines", type="primary", width="stretch", disabled=not ready,
        key=f'smart_generate_final_{key}', icon=':material/play_arrow:')
    if quick_generate or sidebar_generate or final_generate:
        try:
            with st.status("Création des toplines…", expanded=True) as status:
                st.write("Application des décisions métier validées")
                result_filenames = set(split_table["Fichier"].tolist())
                result_exports = [(item.name, item.getvalue()) for item in exports if item.name in result_filenames]
                result, report = build_smart_toplines(
                    result_exports,
                    question_table.to_dict("records"),
                    split_names=names.tolist(),
                    benchmark_positions=benchmark_positions,
                    standard_metrics=standard_metrics,
                    include_screeners=include_screeners,
                    test_type=test_type,
                    mean_decimals=mean_decimals,
                    paired_swaps=paired_swaps,
                    include_deltas=include_deltas,
                    include_sections=include_sections,
                    benchmark_sheet_mode=benchmark_sheet_mode,
                    benchmark_labels=benchmark_short_labels,
                    output_sheet_order=output_sheet_order,
                    show_monadic_gaps=show_monadic_gaps,
                    product_labels=clean_product_labels,
                    product_subtitles=clean_product_subtitles,
                    highlight_benchmarks=highlight_benchmarks,
                    summary_scope=summary_scope,
                    summary_metric_strategy=summary_metric_strategy,
                    include_summary_details=include_summary_details,
                )
                st.write("Calcul des gaps, des significativités et du KPI Summary")
                status.update(label="Toplines terminées", state="complete", expanded=False)
            st.session_state[f"smart_result_{key}"] = result
            st.session_state[f"smart_report_{key}"] = report
        except TemplyfierError as exc:
            st.error(str(exc))
        except Exception as exc:
            st.exception(exc)

    if st.session_state.get(f"smart_result_{key}") and not pending_metrics:
        report = st.session_state[f"smart_report_{key}"]
        st.success(
            f"Fichier prêt : {report['test_type']}, {report['questions']} questions sélectionnées et {len(report['splits'])} onglets générés.",
            icon="✅",
        )
        if report.get("missing_benchmark_exports"):
            st.warning(
                "Combinaisons non générées faute d’export correspondant : "
                + " · ".join(report["missing_benchmark_exports"])
            )
        if report.get('missing_panel_metrics'):
            st.warning(f"{len(report['missing_panel_metrics'])} source metric(s) are missing from individual benchmark readings. Their cells are blank and annotated in Excel; no missing score or gap has been invented.")
        with st.expander("Voir le résumé de la génération"):
            summary_cols = st.columns(4)
            summary_cols[0].metric("Questions gardées", report.get("questions", 0))
            summary_cols[1].metric("Questions écartées", report.get("questions_deleted", 0))
            summary_cols[2].metric("Lignes écrites", report.get("data_rows_written", 0))
            summary_cols[3].metric("Produits", report.get("products", 0))
            st.caption(
                f"Type de test : {report.get('test_type', '—')} · "
                f"Splits générés : {len(report.get('splits', []))} · "
                f"Synthèses KPI : {len(report.get('summary_sheets', []))}"
            )
        st.download_button(
            "⬇️ Télécharger mes toplines",
            data=st.session_state[f"smart_result_{key}"],
            file_name=Path(output_name).name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            width="stretch",
        )

    # Preserve all downstream widget state when an editor form changes rows.
    editor_refresh = st.session_state.pop(f'editor_refresh_{key}', False)
    memory_refresh = st.session_state.pop('memory_refresh_requested', False)
    if editor_refresh or memory_refresh:
        st.rerun()
