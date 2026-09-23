"""CMI review of proposed clean-label groups."""
from copy import deepcopy
import hashlib

import pandas as pd
import streamlit as st

from templyfier.editor_model import group_rows, rename_group
from templyfier.grouping import (accept_suggestion, create_group, dismiss_suggestion,
                                reset_suggestions, separate_group, suggest_groups)


def render_group_assistant(rows, key, revision, commit, ignored_by_memory=(), stage_names=()):
    by_id = {r['Question ID']:r for r in rows}
    suggestions = [g for g in suggest_groups(rows, stage_names=stage_names) if g['id'] not in ignored_by_memory]
    view_token = hashlib.sha1('\0'.join(g['id'] for g in suggestions).encode()).hexdigest()[:12]
    groups = group_rows(rows)
    st.markdown('**Assistant de regroupement des clean labels**')
    st.caption('Le regroupement recherche des préfixes et des batteries dans tout le questionnaire : attributs, émotions, bénéfices, comparaisons ou tout autre sujet. Les suggestions restent séparées par section, stage, type et structure de métriques. Elles ne modifient ni les réponses ni leurs valeurs.')
    if suggestions:
        st.info(f'{len(suggestions)} regroupement(s) proposé(s). Vérifie les exemples, choisis un nom et décide lesquels appliquer.')
        with st.expander('Voir les items avant / après regroupement', expanded=False):
            sid = st.selectbox('Proposition à examiner', [g['id'] for g in suggestions],
                format_func=lambda value:next(f"{g['label']} · {len(g['members'])} items · {g['section']} · {g['family']}" for g in suggestions if g['id']==value),
                key=f'group_preview_{key}_{revision}_{view_token}')
            g = next(g for g in suggestions if g['id']==sid)
            st.caption(g['reason'])
            st.dataframe(pd.DataFrame([{'Question G-Sight':qid, 'Libellé actuel':by_id[qid]['Display label'],
                'Groupe proposé':g['label'], 'Item proposé':g['items'][qid],
                'Métriques conservées':' · '.join(by_id[qid]['Selected metrics'])} for qid in g['members']]),
                hide_index=True, width='stretch')
        with st.form(f'group_suggestions_form_{key}_{revision}_{view_token}'):
            records = [{'id':g['id'],'Décision':'À décider','Nom du groupe':g['label'],
                        'Items':len(g['members']),'Exemples':' · '.join(list(g['items'].values())[:3]),
                        'Repérage':g['confidence'],'Section':g['section'],'Type':g['type'],
                        'Pourquoi ?':g['reason']} for g in suggestions]
            decisions = st.data_editor(pd.DataFrame(records), hide_index=True, width='stretch', height=min(390,38+35*len(records)),
                key=f'group_suggestions_table_{key}_{revision}_{view_token}',
                disabled=['id','Items','Exemples','Repérage','Section','Type','Pourquoi ?'],
                column_config={'id':None,
                    'Décision':st.column_config.SelectboxColumn(options=['À décider','Regrouper','Ignorer'],required=True,pinned=True),
                    'Nom du groupe':st.column_config.TextColumn(required=True,width='medium'),
                    'Exemples':st.column_config.TextColumn(width='large'),
                    'Pourquoi ?':st.column_config.TextColumn(width='large')})
            st.caption('Regrouper rassemble les items à la position du premier, dans leur ordre actuel. Leurs métriques restent inchangées. Ignorer mémorise le refus dans le profil. « À décider » ne change rien.')
            if st.form_submit_button('Appliquer les décisions de regroupement'):
                changed = deepcopy(rows)
                by_suggestion = {g['id']:g for g in suggestions}
                applied, dismissed = 0, 0
                try:
                    for decision in decisions.to_dict('records'):
                        g = by_suggestion[decision['id']]
                        if decision['Décision']=='Regrouper':
                            accept_suggestion(changed,g,decision['Nom du groupe'])
                            applied += 1
                        elif decision['Décision']=='Ignorer':
                            dismiss_suggestion(changed,g)
                            dismissed += 1
                    commit(changed, f'{applied} groupe(s) créé(s), {dismissed} proposition(s) ignorée(s).')
                except ValueError as exc:
                    st.error(str(exc))
    else:
        st.caption('Aucun nouveau regroupement suffisamment étayé. Tu peux créer un groupe manuellement ci-dessous.')

    if groups:
        st.markdown('**Libellés communs des groupes**')
        st.caption('Renomme un groupe une seule fois : tous ses items sont mis à jour. Color → Colour, Emotions → Feelings, ou le vocabulaire de ton client. Les identifiants G-Sight restent inchangés.')
        with st.form(f'groups_form_{key}_{revision}'):
            frame = pd.DataFrame([{'id':g['id'],'Variable clean':g['label'],'Items':len(g['members']),
                'Exemples':' · '.join(str(by_id[q].get('Metric label','')) for q in g['members'][:3]),
                'Section':by_id[g['members'][0]]['Section']} for g in groups])
            edits = st.data_editor(frame, hide_index=True, width='stretch',
                disabled=['id','Items','Exemples','Section'], column_config={'id':None,
                'Variable clean':st.column_config.TextColumn(required=True)}, key=f'groups_table_{key}_{revision}')
            if st.form_submit_button('Appliquer les noms des groupes'):
                changed = deepcopy(rows)
                try:
                    for g in edits.to_dict('records'):
                        rename_group(changed,g['id'],g['Variable clean'])
                    commit(changed,'Libellés communs mis à jour.')
                except ValueError as exc:
                    st.error(str(exc))

    with st.expander('Créer, séparer ou réexaminer des groupes', expanded=False):
        candidates = [r['Question ID'] for r in rows if not r.get('Group ID')]
        with st.form(f'manual_group_{key}_{revision}'):
            chosen = st.multiselect('Questions à regrouper', candidates,
                format_func=lambda q:f"{by_id[q]['Display label']} ({q})")
            label = st.text_input('Nom du nouveau groupe')
            st.caption('Choisis des questions de la même section et du même stage. Les types et métriques restent propres à chaque question. Le groupe sera rassemblé à la position de son premier item.')
            if st.form_submit_button('Créer ce groupe'):
                changed = deepcopy(rows)
                try:
                    create_group(changed,chosen,label,stage_names=stage_names)
                    commit(changed,f'Groupe « {label.strip()} » créé.')
                except ValueError as exc:
                    st.error(str(exc))
        if groups:
            with st.form(f'separate_group_{key}_{revision}'):
                gid = st.selectbox('Groupe à séparer', [g['id'] for g in groups],
                    format_func=lambda value:next(f"{g['label']} · {len(g['members'])} items · {by_id[g['members'][0]]['Section']} · {g['members'][0]}" for g in groups if g['id']==value))
                st.caption('Chaque item redevient indépendant avec un libellé « Groupe · Item ». Aucun renommage ni aucune métrique ne sera perdu. Ces items ne seront plus regroupés automatiquement.')
                if st.form_submit_button('Séparer les items de ce groupe'):
                    changed = deepcopy(rows)
                    separate_group(changed,gid)
                    commit(changed,'Groupe séparé ; libellés et métriques conservés.')
        if any(r.get('Dismissed groups') or r.get('Grouping choice')=='separate' for r in rows):
            if st.button('Réexaminer les regroupements ignorés',key=f'reset_group_suggestions_{key}_{revision}'):
                changed = deepcopy(rows)
                reset_suggestions(changed)
                commit(changed,'Les regroupements ignorés peuvent de nouveau être proposés.')

    duplicates = []
    for g in groups:
        labels = [str(by_id[q].get('Metric label','')).strip().casefold() for q in g['members']]
        if len(set(labels)) < len(labels):
            duplicates.append(g['label'])
    if duplicates:
        st.warning('Libellés d’items répétés à vérifier dans : '+', '.join(dict.fromkeys(duplicates))+'. Les questions sources restent distinctes ; aucune n’a été fusionnée.')
