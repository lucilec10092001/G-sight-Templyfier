from __future__ import annotations

import streamlit as st

from templyfier.preferences import has_seen_onboarding, mark_onboarding_seen


TUTORIAL_STEPS = (
    {
        "eyebrow": "1 · À quoi sert le Templyfier ?",
        "title": "Passer des exports G-Sight à des toplines prêtes à lire",
        "body": (
            "Le Templyfier consolide les exports, nettoie la structure et propose une lecture CMI. "
            "Il reconnaît notamment les formats CLT/HUT, les tests Monadic/Paired, les splits et les benchmarks."
        ),
        "points": (
            "Un seul fichier Excel final au lieu d’une consolidation manuelle",
            "Un ordre de questions et des labels propres proposés automatiquement",
            "Des gaps, significativités et KPI Summary cohérents avec le benchmark choisi",
            "Une explication détaillée de chaque win, parité, résultat partagé ou loss",
        ),
        "callout": "Le Templyfier propose ; le CMI valide toujours avant la génération.",
    },
    {
        "eyebrow": "2 · Ce qu’il faut préparer",
        "title": "Dépose tous les exports utiles en une seule fois",
        "body": (
            "Pour chaque benchmark que tu veux utiliser, exporte dans G-Sight tous les splits que tu souhaites retrouver "
            "dans les toplines. Sélectionne ensuite tous ces fichiers ensemble dans le Templyfier."
        ),
        "points": (
            "Obligatoire : un export G-Sight pour chaque combinaison split × benchmark souhaitée",
            "Exemple : 5 splits face à 2 benchmarks = 10 exports G-Sight à charger ensemble",
            "Facultatif : CMR request export pour les Fantasy names ou Formula descriptions/codes",
            "Facultatif : profil CMI enregistré ou fichier de réglages d’un précédent projet",
        ),
        "callout": "N’oublie aucun couple split × benchmark : l’outil ne peut créer que les comparaisons présentes dans les exports chargés.",
    },
    {
        "eyebrow": "3 · Le parcours recommandé",
        "title": "Quatre vérifications simples, puis le fichier est prêt",
        "body": "Tu peux accepter les propositions telles quelles ou ouvrir uniquement les réglages dont tu as besoin.",
        "points": (
            "1. Ajouter les fichiers",
            "2. Vérifier les questions, l’ordre, les labels et les métriques",
            "3. Contrôler les noms produits, splits, benchmarks et les éventuels fichiers manquants",
            "4. Prévisualiser les onglets, choisir le KPI Summary puis générer les toplines",
        ),
        "callout": "Pour une question à échelle, Mean, Top/Bottom Box, T2B/T3B et B2B/B3B restent sélectionnables question par question.",
    },
    {
        "eyebrow": "4 · Exemple concret",
        "title": "Un TOTAL et plusieurs splits face à deux benchmarks",
        "body": (
            "Tu déposes tous les exports, même si G-Sight a réordonné les produits. Le Templyfier rapproche les codes stables, "
            "détecte le split et crée une lecture séparée pour chaque benchmark."
        ),
        "points": (
            "Des onglets comme TOTAL vs. BENCH 1 et TOTAL vs. BENCH 2",
            "Les gaps et significativités correspondant uniquement au benchmark de la feuille",
            "Un KPI Summary sur TOTAL seulement ou sur tous les splits",
            "Un onglet KPI Details pour comprendre les valeurs et la métrique derrière chaque symbole",
            "Des noms produits remplaçables par les Fantasy names de la CMR",
        ),
        "callout": "En cas de doute, les colonnes Type d’information et Point d’attention expliquent les propositions sans les imposer.",
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
    st.progress((step + 1) / len(TUTORIAL_STEPS), text=f"Étape {step + 1} sur {len(TUTORIAL_STEPS)}")

    previous_col, spacer, next_col = st.columns([1, 2.2, 1])
    if previous_col.button("← Précédent", disabled=step == 0, width='stretch'):
        st.session_state.tutorial_step = step - 1
        st.session_state.tutorial_reopen = True
        st.rerun()
    if step < len(TUTORIAL_STEPS) - 1:
        if next_col.button("Suivant →", type="primary", width='stretch'):
            st.session_state.tutorial_step = step + 1
            st.session_state.tutorial_reopen = True
            st.rerun()
    elif next_col.button("Commencer", type="primary", width='stretch'):
        st.session_state.tutorial_step = 0
        st.rerun()


def render_onboarding() -> None:
    """Non-blocking first visit; the full guide is always available on demand."""
    _, help_col = st.columns([7, 1.35])
    help_clicked = help_col.button(
        "❔ Aide",
        key="open_tutorial",
        width='stretch',
        help="Rouvrir le didacticiel d’utilisation.",
    )

    first_visit = "onboarding_checked" not in st.session_state
    show_tutorial = help_clicked or bool(st.session_state.pop("tutorial_reopen", False))
    if first_visit:
        st.session_state.onboarding_checked = True
        if not has_seen_onboarding():
            mark_onboarding_seen()
            st.session_state.tutorial_step = 0
            st.info('Pour commencer : dépose tes exports, vérifie les suggestions puis génère le fichier. Le bouton Aide reste disponible ; aucun réglage avancé n’est obligatoire.')
    if help_clicked:
        st.session_state.tutorial_step = 0
    if show_tutorial:
        _tutorial_dialog()
