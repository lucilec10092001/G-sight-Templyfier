from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
import streamlit as st

from onboarding import render_onboarding
from smart_ui import render_smart_mode
from server_ui import initialize_access
from templyfier.server_storage import server_mode
from templyfier.core import TemplyfierError, build_toplines, inspect_package, inspect_reference
from templyfier.smart import cmr_product_label, inspect_smart_package, match_cmr_products


st.set_page_config(
    page_title="G-Sight Templyfier",
    page_icon="✨",
    layout="wide",
    initial_sidebar_state="auto",
)

from english_ui import install
install()

initialize_access()
privacy_text = ('Internal server processing • files are not sent to an external AI service'
                if server_mode() else 'Session-only processing · files are not sent to an external AI service')

st.markdown(
    """
    <style>
      .block-container {max-width:1440px; padding-top:4rem; padding-bottom:3rem;}
      .hero {padding:1rem 1.3rem; border-radius:12px; background:#183d45; color:white; margin-bottom:.7rem;}
      .hero h1 {margin:0; font-size:1.8rem; line-height:1.2;}
      .hero p {margin:.55rem 0 0; opacity:.92; font-size:1rem;}
      .privacy {display:inline-block; margin-top:.8rem; padding:.25rem .65rem; border-radius:999px; background:rgba(255,255,255,.15); font-size:.8rem;}
      .step-title {display:flex; align-items:center; gap:.65rem; margin-top:1.25rem; margin-bottom:.25rem; font-size:1.12rem; font-weight:750; color:#183d45; scroll-margin-top:5rem;}
      .step-number {display:inline-flex; align-items:center; justify-content:center; width:28px; height:28px; border-radius:50%; background:#087f83; color:white; font-size:.85rem;}
      .hint {color:#696777; font-size:.9rem; margin-bottom:.8rem;}
      .ok-card {padding:.8rem 1rem; border:1px solid #d9eadf; border-radius:12px; background:#f5fbf7; color:#245c38;}
      .route-card {padding:.65rem 1rem; border:1px solid #dbe5e5; border-radius:10px; background:#f7fafa; margin:.35rem 0 .8rem;}
      .route-card b {color:#183d45;}
      .analysis-card {min-height:112px; padding:.9rem 1rem; border:1px solid #dbe5e5; border-radius:12px; background:#f7fafa;}
      .analysis-card .diagram {font-size:1.25rem; letter-spacing:.15rem; color:#087f83; font-weight:700; margin:.2rem 0 .35rem;}
      .analysis-card p {margin:.2rem 0 0; color:#5f6670; font-size:.88rem;}
      [data-testid="stMetric"] {background:#f7fafa; border:1px solid #dbe5e5; padding:10px 14px; border-radius:10px;}
      [data-testid="stFileUploader"] {border-radius:14px;}
      [data-testid="stButton"] button, [data-testid="stFormSubmitButton"] button {min-height:2.75rem;}
      div[data-testid="stButton"] button[kind="primary"], div[data-testid="stDownloadButton"] button {min-height:3rem; font-weight:700; border-radius:12px;}
    </style>
    <div class="hero">
      <h1>G-Sight Templyfier <span style="font-size:.85rem;opacity:.75">v55</span></h1>
      <p>Turn your G-Sight outputs into review-ready Excel toplines.</p>
      <span class="privacy">🔒 PRIVACY_TEXT</span>
    </div>
    """.replace('PRIVACY_TEXT', privacy_text),
    unsafe_allow_html=True,
)

render_onboarding()

with st.sidebar:
    with st.expander("Use an old clean as a strict template — advanced"):
        st.caption("Use only when the questionnaire, product plan and workbook structure are identical.")
        use_legacy_template = st.checkbox(
            "Use legacy template mode", value=False, key="use_legacy_template"
        )

if not use_legacy_template:
    render_smart_mode()
    st.stop()

st.info(
    "Mode avancé activé : le fichier final suivra strictement la structure de l’ancien clean.",
    icon="📐",
)


def step_title(number: int, title: str, hint: str):
    st.markdown(
        f'<div class="step-title"><span class="step-number">{number}</span>{title}</div>'
        f'<div class="hint">{hint}</div>',
        unsafe_allow_html=True,
    )


def package_key(reference, exports, cmr=None) -> str:
    digest = hashlib.sha1(reference.getvalue())
    for item in exports:
        digest.update(item.name.encode("utf-8"))
        digest.update(item.getvalue())
    if cmr is not None:
        digest.update(cmr.name.encode("utf-8"))
        digest.update(cmr.getvalue())
    return digest.hexdigest()


def shorten(text: str, limit: int = 62) -> str:
    text = str(text or "")
    return text if len(text) <= limit else f"{text[:limit - 1]}…"


progress_slot = st.empty()
progress_slot.progress(0.08, text="Étape 1 sur 3 · Ajout des fichiers")

step_title(
    1,
    "Ajoute les fichiers",
    "Le clean sert de modèle. Ajoute ensuite tous les exports correspondant aux différents splits.",
)
left, middle, right = st.columns([1, 1.25, 1], gap="large")
with left:
    reference = st.file_uploader(
        "Fichier clean de référence",
        type=["xlsx", "xls"],
        key="reference",
        help="La feuille TOTAL sera utilisée automatiquement lorsqu’elle existe.",
    )
with middle:
    exports = st.file_uploader(
        "Exports G-Sight DataViz",
        type=["xlsx", "xls"],
        accept_multiple_files=True,
        key="exports",
        help="Tu peux sélectionner tous les fichiers en une seule fois.",
    )
with right:
    cmr = st.file_uploader(
        "CMR request export — facultatif",
        type=["xlsx", "xls"],
        key="legacy_cmr",
        help="Charge les Fantasy names, Formula descriptions et Formula codes associés aux produits.",
    )

if not reference or not exports:
    st.info("Ajoute un clean de référence et au moins un export G-Sight pour continuer.", icon="👆")
    with st.expander("Pourquoi faut-il un clean de référence ?"):
        st.write(
            "Il permet à l’application d’apprendre les questions conservées, leurs libellés, les titres de sections, "
            "la position des gaps et toute la mise en forme. Tu n’as donc pas besoin de reclasser les questions pour chaque split."
        )
    st.stop()

key = package_key(reference, exports, cmr)
if st.session_state.get("package_key") != key:
    try:
        with st.spinner("Lecture du template et reconnaissance des splits…"):
            ref_info = inspect_reference(reference.getvalue())
            ref_sheet, infos = inspect_package(
                reference.getvalue(),
                [(item.name, item.getvalue()) for item in exports],
                ref_info.sheet_name,
            )
            if cmr:
                smart_info = inspect_smart_package([(item.name, item.getvalue()) for item in exports])
                result_inputs = [item for item in smart_info.inputs if item.role == "Résultats"] or list(smart_info.inputs)
                legacy_cmr_matches = match_cmr_products(
                    result_inputs[0].product_keys,
                    infos[0].product_names,
                    cmr.getvalue(),
                )
            else:
                legacy_cmr_matches = ()
    except Exception as exc:
        st.error(f"Je ne peux pas analyser ces fichiers : {exc}")
        st.stop()

    st.session_state.package_key = key
    st.session_state.ref_info = ref_info
    st.session_state.reference_sheet = ref_sheet
    st.session_state.infos = infos
    st.session_state.legacy_cmr_matches = legacy_cmr_matches
    st.session_state.split_table = pd.DataFrame(
        {
            "Statut": ["✓ Reconnu" for _ in infos],
            "Fichier G-Sight": [info.filename for info in infos],
            "Nom de l’onglet": [info.split_name for info in infos],
            "Bases produits": [" · ".join("?" if n is None else str(n) for n in info.counts) for info in infos],
        }
    )
    st.session_state.pop("result_bytes", None)
    st.session_state.pop("report", None)

ref_info = st.session_state.ref_info
infos = st.session_state.infos
progress_slot.progress(0.52, text="Étape 2 sur 3 · Vérification des splits et du benchmark")

step_title(
    2,
    "Vérifie ce qui a été reconnu",
    "Tout est prérempli. Modifie seulement un nom d’onglet si nécessaire.",
)

metrics = st.columns(4)
metrics[0].metric("Splits", len(exports))
metrics[1].metric("Produits", len(ref_info.product_names))
metrics[2].metric("Lignes retenues", ref_info.retained_rows)
metrics[3].metric("Template détecté", ref_info.sheet_name)

split_table = st.data_editor(
    st.session_state.split_table,
    hide_index=True,
    width="stretch",
    disabled=["Statut", "Fichier G-Sight", "Bases produits"],
    column_config={
        "Statut": st.column_config.TextColumn(width="small"),
        "Fichier G-Sight": st.column_config.TextColumn(width="large"),
        "Nom de l’onglet": st.column_config.TextColumn(required=True, width="medium"),
        "Bases produits": st.column_config.TextColumn(width="large"),
    },
    key=f"split_editor_{key}",
)

product_options = {
    f"{index + 1}. {shorten(name) or f'Produit {index + 1}'}": index
    for index, name in enumerate(ref_info.product_names)
}
benchmark_count = max(1, len(ref_info.benchmark_positions))
default_benchmark_labels = [
    label for label, position in product_options.items()
    if position in ref_info.benchmark_positions
] or list(product_options)[:1]

benchmark_col, check_col = st.columns([1.55, 1], gap="large")
with benchmark_col:
    selected_benchmarks = st.multiselect(
        "Benchmark détecté",
        options=list(product_options),
        default=default_benchmark_labels,
        max_selections=benchmark_count,
        help="Le nombre de benchmarks est déduit des colonnes Gap du template.",
        key=f"benchmarks_{key}",
    )
with check_col:
    products_match = all(info.product_names == infos[0].product_names for info in infos)
    if products_match:
        st.markdown(
            '<div class="ok-card"><b>✓ Contrôle réussi</b><br>Le plan produits est identique dans tous les exports.</div>',
            unsafe_allow_html=True,
        )
    else:
        st.error("Le plan produits diffère entre certains exports.")

legacy_cmr_matches = st.session_state.get("legacy_cmr_matches", ())
with st.expander("Vérifier ou actualiser les noms produits", expanded=bool(legacy_cmr_matches)):
    if legacy_cmr_matches:
        legacy_cmr_options = {
            "Fantasy name (recommandé)": "fantasy",
            "Formula description": "description",
            "Formula code": "formula",
            "Conserver le nom du modèle": "source",
        }
        legacy_cmr_choice = st.radio(
            "Quel nom veux-tu afficher dans les toplines ?",
            list(legacy_cmr_options),
            horizontal=True,
            key=f"legacy_cmr_name_mode_{key}",
        )
        legacy_cmr_mode = legacy_cmr_options[legacy_cmr_choice]
    else:
        legacy_cmr_mode = "source"
    product_rows = []
    for index, source_name in enumerate(ref_info.product_names):
        cmr_match = legacy_cmr_matches[index] if index < len(legacy_cmr_matches) else None
        cmr_value = (
            cmr_product_label(cmr_match, legacy_cmr_mode)
            if cmr_match and cmr_match.score >= 80 else source_name
        )
        product_rows.append({
            "Position": index + 1,
            "Nom du modèle": source_name,
            "Valeur CMR sélectionnée": cmr_value,
            "Nom affiché": cmr_value,
            "Confiance CMR": cmr_match.confidence if cmr_match else "—",
        })
    legacy_product_frame = pd.DataFrame(product_rows)
    legacy_disabled_columns = ["Position", "Nom du modèle"]
    if legacy_cmr_matches:
        legacy_disabled_columns.extend(["Valeur CMR sélectionnée", "Confiance CMR"])
    else:
        legacy_product_frame = legacy_product_frame.drop(columns=["Valeur CMR sélectionnée", "Confiance CMR"])
    product_table = st.data_editor(
        legacy_product_frame,
        hide_index=True,
        width="stretch",
        disabled=legacy_disabled_columns,
        column_config={
            "Position": st.column_config.NumberColumn(width="small"),
            "Nom du modèle": st.column_config.TextColumn(width="large"),
            "Valeur CMR sélectionnée": st.column_config.TextColumn(width="large"),
            "Nom affiché": st.column_config.TextColumn(required=True, width="large"),
            "Confiance CMR": st.column_config.TextColumn(width="small"),
        },
        key=f"legacy_products_{key}_{legacy_cmr_mode}",
    )
    if legacy_cmr_matches:
        matched = sum(
            item.score >= 80 and bool(cmr_product_label(item, legacy_cmr_mode))
            for item in legacy_cmr_matches
        )
        st.success(f"{matched}/{len(legacy_cmr_matches)} nom(s) proposé(s) depuis la CMR.", icon="✨")

clean_product_labels = product_table["Nom affiché"].fillna("").astype(str).str.strip().tolist()

names = split_table["Nom de l’onglet"].astype(str).str.strip()
duplicate_names = names[names.str.casefold().duplicated(keep=False)].tolist()
missing_names = names.eq("").any()
benchmark_ready = len(selected_benchmarks) == benchmark_count
ready = products_match and not duplicate_names and not missing_names and benchmark_ready and all(clean_product_labels)

if duplicate_names:
    st.error(f"Deux onglets portent le même nom : {', '.join(sorted(set(duplicate_names)))}")
if not benchmark_ready:
    st.warning(f"Sélectionne exactement {benchmark_count} benchmark(s).")

progress_slot.progress(0.82 if ready else 0.62, text="Étape 3 sur 3 · Création du fichier clean")
step_title(
    3,
    "Crée les toplines",
    "Les valeurs, gaps, couleurs de significativité et noms d’onglets seront générés en une seule fois.",
)

output_col, action_col = st.columns([1, 1.25], gap="large")
with output_col:
    output_name = st.text_input("Nom du fichier final", "Toplines_clean.xlsx")
    if not output_name.lower().endswith(".xlsx"):
        output_name += ".xlsx"
with action_col:
    st.write("")
    st.write("")
    generate = st.button(
        "✨ Créer mon fichier clean",
        type="primary",
        width="stretch",
        disabled=not ready,
    )

if generate:
    try:
        with st.status("Création des toplines…", expanded=True) as status:
            st.write("Apprentissage des lignes et des libellés du template")
            st.write("Application aux différents splits")
            result, report = build_toplines(
                reference.getvalue(),
                [(item.name, item.getvalue()) for item in exports],
                split_names=names.tolist(),
                reference_sheet=ref_info.sheet_name,
                benchmark_positions=tuple(product_options[name] for name in selected_benchmarks),
                product_labels=clean_product_labels,
            )
            st.write("Création des formules de gap et reprise des couleurs")
            status.update(label="Fichier clean terminé", state="complete", expanded=False)
        st.session_state.result_bytes = result
        st.session_state.report = report
        st.session_state.result_config = (tuple(names.tolist()), tuple(selected_benchmarks), output_name)
        progress_slot.progress(1.0, text="Terminé · Le fichier est prêt à être téléchargé")
    except TemplyfierError as exc:
        st.error(str(exc))
    except Exception as exc:
        st.exception(exc)

current_config = (tuple(names.tolist()), tuple(selected_benchmarks), output_name)
if st.session_state.get("result_bytes") and st.session_state.get("result_config") == current_config:
    report = st.session_state.report
    st.success(
        f"Fichier prêt : {len(report['splits'])} splits, {report['mapped_rows']} lignes mappées et {report['products']} produits.",
        icon="✅",
    )
    st.download_button(
        "⬇️ Télécharger les toplines clean",
        data=st.session_state.result_bytes,
        file_name=Path(output_name).name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
        width="stretch",
    )
    with st.expander("Afficher le résumé de la génération"):
        report_cols = st.columns(3)
        report_cols[0].metric("Splits", len(report.get("splits", [])))
        report_cols[1].metric("Lignes reprises", report.get("mapped_rows", 0))
        report_cols[2].metric("Produits", report.get("products", 0))
elif st.session_state.get("result_bytes"):
    st.info("La configuration a changé. Relance la création pour mettre à jour le fichier.")

st.divider()
st.caption("G-Sight Templyfier · Interface locale Streamlit · Aucun fichier n’est envoyé vers un service externe.")
