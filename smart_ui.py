from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import streamlit as st
from question_editor import render_question_editor

from templyfier.core import TemplyfierError
from templyfier.review import audit_questions, preview_rows
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


def _step(stage, title, hint):
    step_number = {
        "upload": 1,
        "setup": 2,
        "questions": 3,
        "generate": 4,
    }.get(str(stage), stage)
    st.markdown(
        f'<div class="step-title" id="etape-{stage}"><span class="step-number">{step_number}</span>{title}</div>'
        f'<div class="hint">{hint}</div>',
        unsafe_allow_html=True,
    )


def render_smart_mode():
    with st.sidebar:
        st.subheader("Your journey")
        st.markdown("[1 · Add files](#etape-upload)\n\n[2 · Confirm setup](#etape-setup)\n\n[3 · Review questions](#etape-questions)\n\n[4 · Generate](#etape-generate)")
        navigation_status = st.empty()
        sidebar_generate_slot = st.empty()
        navigation_status.progress(.1, text="Start by adding the study files")

    _step(
        "upload", "Select your study files",
        "Select all G-Sight outputs and the matching CMR export.",
    )
    st.caption("Use either one G-Sight output containing every split, or one G-Sight output per split. Select all files together.")
    exports_col, cmr_col = st.columns(2, gap="large")
    with exports_col:
        exports = st.file_uploader(
            "G-Sight DataViz outputs", type=["xlsx", "xls"], accept_multiple_files=True,
            key="smart_exports", help="Select every output needed for this study.",
        )
    with cmr_col:
        cmr_upload = st.file_uploader(
            "CMR export", type=["xlsx", "xls"], key="smart_cmr",
            help="Required to identify and name products reliably.",
        )
    if not exports or cmr_upload is None:
        missing = []
        if not exports:
            missing.append("G-Sight output(s)")
        if cmr_upload is None:
            missing.append("CMR export")
        st.info("Add " + " and ".join(missing) + " to continue.", icon=":material/upload_file:")
        st.stop()

    local_profile_name = "None"
    profile_upload = None
    resumed_draft = None
    local_profiles = {}
    client_memory = None
    key = _files_key(exports, profile_upload, cmr_upload, local_profile_name, None)
    state_key = f"smart_state_{key}"
    if state_key not in st.session_state:
        try:
            with st.spinner("Reading the study files and preparing the review…"):
                info = inspect_smart_package([(item.name, item.getvalue()) for item in exports])
                question_rows = [proposal_to_row(item) for item in info.questions]
                result_inputs = [item for item in info.inputs if item.role == "Résultats"] or list(info.inputs)
                cmr_matches = match_cmr_products(
                    result_inputs[0].product_keys, info.product_names, cmr_upload.getvalue()
                )
        except Exception as exc:
            st.error(f"The files could not be analysed: {exc}")
            st.stop()
        st.session_state[state_key] = {
            "info": info,
            "questions": pd.DataFrame(question_rows),
            "splits": pd.DataFrame({
                "Fichier": [item.filename for item in result_inputs],
                "Source": [
                    f"{item.filename} / {item.source_sheet}"
                    if item.embedded_split_count > 1 and item.source_sheet
                    else item.filename
                    for item in result_inputs
                ],
                "Nom de l'onglet": [item.split_name for item in result_inputs],
                "Benchmark détecté": [" · ".join(item.comparison_codes) or "—" for item in result_inputs],
                "Bases": [" · ".join("?" if n is None else str(n) for n in item.counts) for item in result_inputs],
                "Split detection": [item.split_detection for item in result_inputs],
            }),
            "settings": {},
            "profile_comparison": None,
            "profile_protected_ids": [],
            "cmr_matches": cmr_matches,
        }

    state = st.session_state[state_key]
    info = state["info"]
    settings = state["settings"]

    result_inputs = [item for item in info.inputs if item.role == "Résultats"] or list(info.inputs)
    if "Source" not in state["splits"].columns:
        state["splits"]["Source"] = [
            f"{item.filename} / {item.source_sheet}"
            if item.embedded_split_count > 1 and item.source_sheet
            else item.filename
            for item in result_inputs
        ]
    suggested_test_type = "Paired" if info.suggested_test_type.startswith("Paired") else "Monadic"
    saved_test_type = settings.get("test_type", suggested_test_type)
    gate_prefix = f"journey_{key}"
    qa_skip_gates = bool(st.session_state.get("_qa_skip_journey_gates", False))

    _step("setup", "Confirm the study setup and output", "Check the few choices that change the final workbook.")
    detected_format = info.study_format if info.study_format in {"HUT / in-use", "CLT"} else None
    study_format = st.segmented_control(
        "Study format", ["HUT / in-use", "CLT"], default=detected_format,
        key=f"detected_study_format_{key}",
    )
    if study_format == "HUT / in-use":
        test_type = st.segmented_control(
            "Analysis design", ["Monadic", "Paired"], default=saved_test_type,
            key=f"smart_test_type_{key}",
        )
    elif study_format == "CLT":
        test_type = "Monadic"
    else:
        test_type = saved_test_type
        st.warning("Choose the study format to continue.", icon=":material/warning:")
    block_design = "unknown"
    clt_stages = [stage for stage in info.stages
                  if str(stage).strip() and _normal(stage) not in {"not specified", "non precise"}]
    clt_stage_order = list(clt_stages)

    st.markdown("**Outputs to include**")
    output_cols = st.columns(2)
    include_screeners = output_cols[0].checkbox(
        "Add Screener worksheet", value=bool(settings.get("include_screeners", True)),
        key=f"smart_screeners_{key}",
    )
    include_kpi_summary = output_cols[1].checkbox(
        "Add KPI Summary", value=settings.get("summary_scope", "total") != "none",
        key=f"smart_include_kpi_{key}",
    )

    st.markdown("**Output format**")
    saved_mode = settings.get("benchmark_sheet_mode", "auto_columns")
    benchmark_layout = st.segmented_control(
        "Benchmark reading",
        ["All benchmarks side by side", "One worksheet per benchmark"],
        default="All benchmarks side by side"
        if saved_mode in {"combined", "auto_columns", "benchmark_columns"}
        else "One worksheet per benchmark",
        key=f"smart_benchmark_layout_{key}",
        help="Side by side keeps every benchmark reading on one split worksheet. The second option creates a split × benchmark worksheet.",
    )
    format_cols = st.columns(2)
    mean_decimals = format_cols[0].segmented_control(
        "Mean decimals", [0, 1, 2], default=int(settings.get("mean_decimals", 0)),
        format_func=lambda value: "0 decimals" if value == 0 else f"{value} decimal" + ("s" if value > 1 else ""),
        key=f"smart_mean_decimals_{key}",
    )
    show_difference = format_cols[1].checkbox(
        "Show gap / delta columns", value=bool(settings.get(
            "show_monadic_gaps" if test_type == "Monadic" else "include_deltas", True
        )), key=f"smart_gap_delta_{key}",
        help="Candidate score minus benchmark score. Significance remains available when this is off.",
    )
    include_deltas = show_difference if test_type == "Paired" else True
    show_monadic_gaps = show_difference if test_type == "Monadic" else True
    include_sections = bool(settings.get("include_sections", True))
    output_sheet_order = settings.get("output_sheet_order", "benchmark_first")
    highlight_benchmarks = bool(settings.get("highlight_benchmarks", True))

    detected_codes = list(dict.fromkeys(code for item in result_inputs for code in item.comparison_codes))
    if detected_codes:
        st.caption("Benchmarks detected automatically: " + " · ".join(detected_codes))
    else:
        st.warning("No benchmark could be identified automatically in these outputs.", icon=":material/warning:")

    st.markdown("**Splits shown in Excel**")
    split_table = st.data_editor(
        state["splits"], hide_index=True, width="stretch",
        disabled=["Fichier", "Source", "Benchmark détecté", "Bases", "Split detection"],
        column_order=["Nom de l'onglet", "Source", "Benchmark détecté", "Bases"],
        column_config={
            "Nom de l'onglet": st.column_config.TextColumn("Split name shown in Excel", required=True, width="large"),
            "Source": st.column_config.TextColumn(
                "G-Sight source", width="large",
                help="The uploaded file, followed by the worksheet when several result sheets are inside one workbook.",
            ),
            "Benchmark détecté": st.column_config.TextColumn("Benchmark found", width="large"),
            "Bases": st.column_config.TextColumn("Base", width="medium"),
            "Fichier": None,
            "Split detection": None,
        }, key=f"smart_splits_{key}",
    )
    uncertain = int(split_table["Split detection"].astype(str).eq("Review recommended").sum())
    if uncertain:
        st.warning(f"Please check {uncertain} proposed split name(s). Edit only the first column.", icon=":material/edit:")
    else:
        st.caption("Split names were detected with high confidence. They remain editable.")

    setup_signature = hashlib.sha1((
        str(study_format) + str(test_type) + benchmark_layout + str(mean_decimals)
        + str(include_screeners) + str(include_kpi_summary) + str(show_difference)
        + split_table["Nom de l'onglet"].astype(str).str.strip().str.casefold().str.cat(sep="|")
    ).encode("utf-8")).hexdigest()
    if st.session_state.get(f"{gate_prefix}_setup_signature") not in {None, setup_signature}:
        st.session_state[f"{gate_prefix}_setup"] = False
    st.session_state[f"{gate_prefix}_setup_signature"] = setup_signature
    if st.button("Continue to question review", type="primary", key=f"confirm_setup_{key}",
                 icon=":material/arrow_forward:", disabled=study_format is None):
        st.session_state[f"{gate_prefix}_setup"] = True
    setup_confirmed = qa_skip_gates or bool(st.session_state.get(f"{gate_prefix}_setup"))
    if not setup_confirmed:
        st.caption("Confirm these settings to open the question table.")
        st.stop()

    _step("questions", "Review the questions", "Keep the suggestions or adjust everything from one table.")
    standard_metrics = settings.get("standard_metrics", ["Mean", "Top Box", "Top 2 Boxes", "Bottom 2 Boxes"])
    question_table = render_question_editor(
        state["questions"], info.questions, key, memory=client_memory,
        protected_ids=state.get("profile_protected_ids", []), project_key=_files_key(exports),
        show_optional=False, stage_order=clt_stage_order,
    )
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
        benchmark_labels = [list(product_options)[position] for position in detected_positions]
        benchmark_source = "auto"
        benchmark_count = len(benchmark_labels)
        columns = benchmark_layout == "All benchmarks side by side"
        benchmark_sheet_mode = "auto_columns" if columns else "auto_exports"
        benchmark_short_labels = [
            clean_product_labels[position] or info.product_names[position]
            for position in detected_positions
        ]
        if benchmark_labels:
            st.caption(
                f"Automatic benchmark detection: {benchmark_count} benchmark(s) — "
                + " · ".join(benchmark_short_labels)
            )
        else:
            st.error("Automatic benchmark detection failed. Check that each G-Sight output contains its comparison columns.")
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
            source_key = f"{item.filename}::{item.source_sheet}"
            for position in range(0, len(item.product_names) - 1, 2):
                pair_rows.append({
                    "Source key": source_key,
                    "Fichier": item.filename,
                    "Split": item.split_name,
                    "Paire": position // 2 + 1,
                    "Benchmark": item.product_names[position],
                    "Candidat": item.product_names[position + 1],
                    "Inverser": position // 2 + 1 in saved_swaps.get(
                        source_key, saved_swaps.get(item.filename, [])
                    ),
                })
        st.caption(
            "Plan Paired détecté — chaque paire doit être Benchmark puis Candidat. "
            "Les splits peuvent avoir un nombre de paires actives différent."
        )
        pair_table = st.data_editor(
            pd.DataFrame(
                pair_rows,
                columns=["Source key", "Fichier", "Split", "Paire", "Benchmark", "Candidat", "Inverser"],
            ),
            hide_index=True,
            width="stretch",
            disabled=["Fichier", "Split", "Paire", "Benchmark", "Candidat"],
            column_order=["Split", "Paire", "Benchmark", "Candidat", "Inverser"],
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
            source_key: group.loc[group["Inverser"].astype(bool), "Paire"].astype(int).tolist()
            for source_key, group in pair_table.groupby("Source key")
        }

    benchmark_positions = tuple(product_options[label] for label in benchmark_labels)
    audit = audit_input_plan(
        info,
        split_table["Nom de l'onglet"].astype(str).str.strip().tolist(),
        benchmark_positions,
        test_type=test_type,
        automatic_exports=test_type == "Monadic" and benchmark_sheet_mode in {"auto_exports","auto_columns"},
    )
    if audit['ready']:
        if test_type=='Monadic' and benchmark_sheet_mode in {'auto_exports','auto_columns'}:
            split_count=len({_normal(name) for name in split_table["Nom de l'onglet"].astype(str) if str(name).strip()})
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

    summary_scope = "total" if include_kpi_summary else "none"
    summary_metric_strategy = "priority"
    include_summary_details = bool(include_kpi_summary)
    summary_kpis = question_table[
        question_table["Keep"].astype(bool)
        & question_table["Type"].ne("Delete")
        & question_table["KPI Summary"].astype(bool)
    ]
    if include_kpi_summary and summary_kpis.empty:
        st.error("Add at least one question to KPI Summary in the review table, or turn KPI Summary off.")

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
    # Any configuration change invalidates the previously generated workbook.
    kept = question_table[question_table["Keep"].astype(bool) & question_table["Type"].ne("Delete")]
    names = split_table["Nom de l'onglet"].astype(str).str.strip()
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
    question_audit = audit_questions(question_table.to_dict("records"),
                                     {p.question_id: p.metrics for p in info.questions}, names.tolist())
    pending_metrics = bool(st.session_state.get(f'metric_batch_{key}'))
    if question_audit['blockers']:
        st.error(f"{len({i['Question ID'] for i in question_audit['blockers']})} question(s) à corriger avant export : métriques, libellés ou filtre de splits.")
        with st.expander('Détail des corrections nécessaires', expanded=True):
            st.dataframe(pd.DataFrame(question_audit['blockers']).drop(columns=['Code']), hide_index=True, width='stretch')
    if pending_metrics:
        st.warning('Un changement groupé de métriques attend ta décision dans l’éditeur. Confirme-le ou abandonne son aperçu avant de générer ou télécharger.')

    verified = True

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
        (test_type == "Paired" or products_match)
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
        if next_steps:st.info('What to do next\n\n'+ '\n'.join(f'{i}. {item}' for i,item in enumerate(next_steps,1)))

    _step("generate", "Generate the Excel file", "The existing safety checks still protect the export.")
    planned_workbook_sheets = (
        (["Screener(s)"] if include_screeners else [])
        + planned_topline_sheets
        + planned_summary_sheets
    )
    with st.container(border=True):
        st.markdown("### Preview the final Excel")
        st.caption(
            "Check the workbook structure before generation. Scores are shown as dashes "
            "because this preview never fabricates results."
        )
        if not ready:
            st.warning(
                "This is a preliminary preview. Items marked above must still be corrected "
                "before the Excel file can be generated.",
                icon=":material/visibility:",
            )
        preview_sheet = st.selectbox(
            "Worksheet to preview",
            planned_workbook_sheets or ["No worksheet available"],
            index=(
                planned_workbook_sheets.index(planned_topline_sheets[0])
                if planned_topline_sheets and planned_topline_sheets[0] in planned_workbook_sheets
                else 0
            ),
            key=f"excel_preview_sheet_{key}",
        )
        st.caption(
            f"Planned workbook: {len(planned_workbook_sheets)} worksheet(s) · "
            + " · ".join(planned_workbook_sheets[:8])
            + (" · …" if len(planned_workbook_sheets) > 8 else "")
        )
        if preview_sheet == "Screener(s)":
            st.info(
                "The Screener worksheet(s) will be copied from the G-Sight source and kept "
                "separate from the topline reading."
            )
        elif preview_sheet in planned_summary_sheets:
            summary_preview = pd.DataFrame([
                {
                    "KPI": row.get("Summary label") or row.get("Display label"),
                    "Result used": " · ".join(row.get("Selected metrics", [])[:2]),
                }
                for row in question_table.to_dict("records")
                if row.get("Keep") and row.get("KPI Summary")
            ])
            for label in (benchmark_short_labels or clean_product_labels):
                summary_preview[str(label)] = "—"
            if summary_preview.empty:
                st.info("Select at least one KPI in the question table to populate this worksheet.")
            else:
                st.dataframe(summary_preview, hide_index=True, width="stretch", height=300)
        elif preview_sheet in planned_topline_sheets:
            preview_split = next(
                (
                    split for split in sorted(unique_splits, key=len, reverse=True)
                    if preview_sheet == split or preview_sheet.startswith(f"{split} vs ")
                ),
                unique_splits[0] if unique_splits else None,
            )
            structure = preview_rows(
                question_table.to_dict("records"),
                split_name=preview_split,
            )
            visual_rows = pd.DataFrame([
                {
                    "Section": row.get("Section", ""),
                    "Variable shown in Excel": row.get("Variable clean", ""),
                    "Result shown in Excel": row.get("Item / métrique", ""),
                }
                for row in structure[:20]
            ])
            used_headers = set(visual_rows.columns)
            for index, label in enumerate(clean_product_labels, 1):
                header = str(label or f"Product {index}")
                if header in used_headers:
                    header = f"{header} ({index})"
                used_headers.add(header)
                visual_rows[header] = "—"
            if show_difference:
                delta_labels = benchmark_short_labels or ["benchmark"]
                for index, label in enumerate(delta_labels, 1):
                    header = f"Δ vs {label}" if test_type == "Monadic" else f"Delta {index}"
                    if header in used_headers:
                        header = f"{header} ({index})"
                    used_headers.add(header)
                    visual_rows[header] = "—"
            if visual_rows.empty:
                st.info("No retained question currently applies to this worksheet.")
            else:
                st.dataframe(visual_rows, hide_index=True, width="stretch", height=420)
                if len(structure) > len(visual_rows):
                    st.caption(
                        f"First {len(visual_rows)} of {len(structure)} result rows shown. "
                        "The generated worksheet will contain the complete selection."
                    )
    output_name = st.text_input("Final file name", "Toplines_clean.xlsx", key=f"smart_output_{key}")
    if not output_name.lower().endswith(".xlsx"):
        output_name += ".xlsx"
    with st.container(border=True):
        quick_summary = st.columns(4)
        quick_summary[0].metric("Questions", len(kept))
        quick_summary[1].metric("Splits", len(unique_splits))
        quick_summary[2].metric("Benchmarks", benchmark_count if test_type == "Monadic" else "Paired")
        quick_summary[3].metric("Worksheets", len(planned_topline_sheets) + len(planned_summary_sheets))
        st.caption("Optional settings can be left untouched. Generate uses the choices and question table above.")
        quick_generate = st.button("Generate now", type="primary", width="stretch", disabled=not ready,
                                   key=f"smart_generate_quick_{key}", icon=":material/play_arrow:")
    with sidebar_generate_slot:
        sidebar_generate = st.button("Generate now", type="primary", width="stretch", disabled=not ready,
                                     key=f"smart_generate_sidebar_{key}", icon=":material/play_arrow:")
    navigation_status.progress(1.0 if ready else .75,
                               text="Ready to generate" if ready else "Review the items marked above")

    if quick_generate or sidebar_generate:
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
