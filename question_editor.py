from copy import deepcopy
import hashlib
import re

import pandas as pd
import streamlit as st

from question_order import question_order
from grouping_ui import render_group_assistant
from templyfier.grouping import remember_edit, undo_edit, redo_edit
from templyfier.review import editor_view_key
from review_ui import render_review_center
from metric_editor import render_metric_editor, render_type_metric_editor
from memory_ui import render_memory_assistant
from templyfier.editor_model import (
    QUESTION_TYPES, change_type, export_rows, group_rows, prepare_rows,
    rename_group, reorder_rows, set_metric_selection,
)
from templyfier.smart import STANDARD_METRICS, _metric_key, default_metric_selection, proposal_to_row
from templyfier.english_catalog import TEXT

TYPE_EXPLANATIONS={
    'Standard':'A rating scale such as liking or purchase intent. Excel usually shows Mean and selected Top/Bottom Boxes.',
    'Strength':'An intensity or JAR scale such as too weak, just right or too strong. Excel shows the useful response levels.',
    'CATA':'A Check All That Apply question. Excel can show the positive response, the No response, or both.',
    'Bipolaire':'A scale between two opposite attributes. Excel can show individual points and available Top/Bottom Boxes.',
    'Listing':'A list of answer choices such as colours or benefits. Excel shows the selected answer options, without Mean.',
    'Preference':'A preference question such as preferred product, I prefer or liked the most. Excel shows the available choices.',
    'Autres':'A project-specific question such as comparison with current. Choose the useful source responses.',
}


def render_question_editor(frame, proposals, key, memory=None, protected_ids=(), project_key=None, show_optional=True, stage_order=()):
    model_key = f'question_model_{key}'
    if model_key not in st.session_state:
        initial_rows = prepare_rows(frame.to_dict('records'), proposals, stage_order)
        if len(stage_order) > 1:
            normalized = [(index, re.sub(r'[\W_]+', ' ', str(stage).casefold()).strip()) for index, stage in enumerate(stage_order)]
            def stage_rank(item):
                text = re.sub(r'[\W_]+', ' ', ' '.join(str(item.get(field, '')) for field in ('Question ID', 'Display label', 'Section')).casefold()).strip()
                matched = next((index for index, stage in normalized if stage and re.search(rf'\b{re.escape(stage)}\b', text)), len(normalized))
                return matched, int(item.get('Order', 999999))
            initial_rows = sorted(initial_rows, key=stage_rank)
            for index, row in enumerate(initial_rows, 1):
                row['Order'] = index
        st.session_state[model_key] = {'rows': initial_rows, 'revision': 0, 'history': [],
                                       'stage_order': list(stage_order)}
    model = st.session_state[model_key]
    if 'learning_baseline' not in model:
        model['learning_baseline'] = prepare_rows([proposal_to_row(p) for p in proposals], proposals, stage_order)
    rows, revision = model['rows'], model['revision']

    def commit(changed, action='Réglages des questions mis à jour.'):
        if remember_edit(model, changed, action):
            # Render the whole page before rerunning, preserving downstream widgets.
            st.session_state[f'editor_refresh_{key}'] = True
        else:
            st.info('Aucun changement à appliquer.')

    with st.container(horizontal=True):
        st.button('Annuler la dernière modification', key=f'undo_questions_{key}',
                     disabled=not model.get('history'), icon=':material/undo:',
                     help='Restaure les questions, groupes, métriques et ordre. Historique des 20 dernières actions appliquées dans cette session.',
                     on_click=undo_edit,args=(model,))
        st.button('Rétablir la modification', key=f'redo_questions_{key}',
                     disabled=not model.get('redo'), icon=':material/redo:',on_click=redo_edit,args=(model,))
    if model.get('notice'):
        st.success(model['notice'])

    st.subheader('Questions, groupes et métriques')
    st.success('Templyfier has already prepared a complete selection. If the suggestions look right, you do not need to edit or apply every question.')
    st.caption('Focus on questions marked for review. Use the table or metric editor only when you want to change a suggestion; click Save after an edit. Grouping and reordering are optional.')
    audit = render_review_center(rows, key)

    attention_ids=audit['attention_ids']
    by_id={row['Question ID']:row for row in rows}
    guided_options=list(by_id)
    default_id=next((row['Question ID'] for row in rows if row['Question ID'] in attention_ids),guided_options[0])
    guided_key=f'guided_question_{key}'
    if st.session_state.get(guided_key) not in by_id:
        st.session_state[guided_key]=default_id
    type_attention_ids = {
        item['Question ID'] for item in audit['issues']
        if item.get('Code') in {'uncertain_type', 'unknown_type'}
    }
    type_issue_by_id = {
        item['Question ID']: item.get('Point à traiter', 'Recognition needs confirmation.')
        for item in audit['issues']
        if item.get('Code') in {'uncertain_type', 'unknown_type'}
    }
    summary = st.columns(3)
    summary[0].metric('Questions detected', len(rows))
    summary[1].metric('Question types', len({row['Type'] for row in rows if row.get('Keep')}))
    summary[2].metric('Types to check', len(type_attention_ids))
    if not type_attention_ids:
        st.caption('All question types have a confident proposal. Continue to Metric selection unless you want to make a correction.')
    type_rows = []
    blocking_ids = {item['Question ID'] for item in audit['blockers']}
    for row in rows:
        needs_review = row['Question ID'] in type_attention_ids
        type_rows.append({
            'Review status': 'Please check' if needs_review else 'Ready',
            'Why check': type_issue_by_id.get(row['Question ID'], ''),
            'Question shown in Excel': row.get('Metric label') or row['Display label'],
            'Question type': row['Type'],
            'Question ID': row['Question ID'],
        })
    st.markdown('#### Check question types')
    st.caption('Templyfier classified every question. Open the table only when a row says Please check or when you want to correct a type.')
    with st.expander(f"Review question types - {len(type_attention_ids)} to check", expanded=bool(type_attention_ids)):
        with st.form(f'type_review_form_{key}_{revision}'):
            type_edits = st.data_editor(
                pd.DataFrame(type_rows), hide_index=True, width='stretch',
                disabled=['Review status', 'Why check', 'Question shown in Excel', 'Question ID'],
                column_order=['Review status', 'Question shown in Excel', 'Question type', 'Why check', 'Question ID'],
                key=f'type_review_table_{key}_{revision}',
                column_config={
                    'Review status': st.column_config.TextColumn('Status', width='small'),
                    'Why check': st.column_config.TextColumn('Why Templyfier asks', width='large'),
                    'Question shown in Excel': st.column_config.TextColumn('Question', width='large'),
                    'Question type': st.column_config.SelectboxColumn('Question type', options=list(QUESTION_TYPES), required=True, width='medium'),
                    'Question ID': st.column_config.TextColumn('Source ID', width='medium'),
                },
            )
            if st.form_submit_button('Save question types', type='primary'):
                changed = deepcopy(rows)
                changed_by_id = {row['Question ID']: row for row in changed}
                for edit in type_edits.to_dict('records'):
                    change_type(changed_by_id[edit['Question ID']], edit['Question type'])
                commit(changed, 'Question types updated.')

    render_type_metric_editor(rows, key, revision)
    with st.expander('Optional customisation - change metrics for one question', expanded=bool(st.session_state.get(f'metric_batch_{key}'))):
        render_metric_editor(rows, key, revision, commit)

    with st.expander('Optional customisation — edit all questions in a table'):
        scope = st.selectbox('Afficher les questions', ['Toutes','À corriger','À vérifier','Gardées','Écartées'], key=f'question_scope_{key}',persist_state='session')
        search = st.text_input('Rechercher une question, un groupe ou un item', key=f'question_search_{key}',persist_state='session')
        def clear_filters():
            st.session_state[f'question_search_{key}']=''
            st.session_state[f'question_scope_{key}']='Toutes'
            st.session_state[f'only_attention_{key}']=False
        st.button('Effacer les filtres',key=f'clear_question_filters_{key}',on_click=clear_filters,
                  disabled=not search and scope=='Toutes')
        st.caption('Save table changes before changing the search. Filtering hides rows without excluding them from the export.')

        # The group label is edited once above; only its individual item appears here.
        visible=[]
        previous_group = None
        blocking_ids = {i['Question ID'] for i in audit['blockers']}
        for row in rows:
            if ((scope == 'À corriger' and row['Question ID'] not in blocking_ids)
                or (scope == 'À vérifier' and row['Question ID'] not in audit['attention_ids'])
                or (scope == 'Gardées' and not row['Keep'])
                or (scope == 'Écartées' and row['Keep'])):
                continue
            searchable = ' '.join(str(row.get(field,'')) for field in ('Question ID','Display label','Metric label','Section','Type')).casefold()
            if search.strip() and search.strip().casefold() not in searchable:
                continue
            visible.append({
                'Question ID':row['Question ID'], 'Keep':row['Keep'], 'Type':row['Type'], 'Confidence':row.get('Confidence',''),
                'Variable / item':row.get('Metric label') if row.get('Group ID') else row['Display label'],
                'Groupe':row['Display label'] if row.get('Group ID') and row['Group ID'] != previous_group else '',
                'Section':row['Section'], 'KPI Summary':row['KPI Summary'],
                'Summary label':row['Summary label'], 'Sens favorable':row['Sens favorable'],
                'Included splits':row['Included splits'],
                'Métriques retenues':' · '.join(row['Selected metrics']),
            })
            previous_group = row.get('Group ID')
        st.caption(f'{len(visible)} / {len(rows)} questions affichées.')
        view_key = editor_view_key(visible, search, scope)
        with st.form(f'questions_form_{key}_{revision}'):
            edited = st.data_editor(pd.DataFrame(visible, columns=['Question ID','Keep','Type','Confidence','Variable / item','Groupe','Section','KPI Summary','Summary label','Sens favorable','Included splits','Métriques retenues']), hide_index=True, width='stretch',height=440,
                column_order=['Keep','Type','Variable / item','Groupe','Section','Included splits','KPI Summary','Summary label','Sens favorable','Confidence','Question ID','Métriques retenues'],
                key=f'questions_table_{key}_{revision}_{view_key}', disabled=['Question ID','Confidence','Groupe','Métriques retenues'],
                column_config={
                    'Confidence':st.column_config.TextColumn('Recognition confidence',help='Heuristic recognition level, not a statistical probability. Review unfamiliar or ambiguous questions.'),
                    'Keep':st.column_config.CheckboxColumn('Garder',pinned=True),
                    'Type':st.column_config.SelectboxColumn('Type de question',options=list(QUESTION_TYPES),required=True,pinned=True),
                    'Variable / item':st.column_config.TextColumn('Variable / item',required=True,width='large'),
                    'Question ID':st.column_config.TextColumn('Question G-Sight',width='large'),
                    'Summary label':st.column_config.TextColumn('Label KPI court'),
                    'Sens favorable':st.column_config.SelectboxColumn(options=['Automatique','Plus haut','Plus bas','Idéal au centre','Neutre']),
                    'Included splits':st.column_config.TextColumn('Splits inclus'),
                })
            st.caption('Changer le type repropose une sélection de métriques pour cette question. Tu pourras ensuite la modifier ci-dessous. Les métriques de type listing ne sont pas interprétées comme des moyennes.')
            if st.form_submit_button('Save question changes'):
                changed=deepcopy(rows)
                by_id={r['Question ID']:r for r in changed}
                try:
                    for edit in edited.to_dict('records'):
                        row=by_id[edit['Question ID']]
                        change_type(row,edit['Type'])
                        for field in ('Keep','Section','KPI Summary','Summary label','Sens favorable','Included splits'):
                            row[field]=edit[field]
                        label=str(edit['Variable / item']).strip()
                        if not label:
                            raise ValueError('Un libellé de variable ou d’item est vide.')
                        row['Metric label' if row.get('Group ID') else 'Display label']=label
                    commit(changed)
                except ValueError as exc:
                    st.error(str(exc))


    if show_optional:
        render_optional_question_tools(key, memory, protected_ids, project_key, stage_order=stage_order)
    empty=[r for r in rows if r['Keep'] and not r['Selected metrics']]
    if empty:
        st.warning(f'{len(empty)} question(s) gardée(s) sans métrique : sélectionne au moins une métrique ou décoche Garder.')
    return pd.DataFrame(export_rows(model['rows']))


def render_optional_question_tools(key, memory=None, protected_ids=(), project_key=None, *, include_reorder=True, include_grouping=True, stage_order=()):
    """Render optional tools against the existing editor model without changing saved data."""
    model = st.session_state[f'question_model_{key}']
    rows, revision = model['rows'], model['revision']

    def commit(changed, action='Question settings updated.'):
        if remember_edit(model, changed, action):
            st.session_state[f'editor_refresh_{key}'] = True
        else:
            st.info('No change to apply.')

    ignored_by_memory = ()
    if include_grouping:
        if memory is not None:
            with st.expander('Apply saved client preferences — optional'):
                st.caption('Use this only when a previous client habit is useful for the current project. Results are never stored.')
                ignored_by_memory = render_memory_assistant(rows, model['learning_baseline'], memory, key, revision, commit,
                    protected_ids=protected_ids, pending_metrics=bool(st.session_state.get(f'metric_batch_{key}')), project_key=project_key)
        with st.expander('Optional customisation - rename or group repeated items once'):
            render_group_assistant(rows, key, revision, commit, ignored_by_memory=ignored_by_memory,
                                   stage_names=stage_order)

    if include_reorder:
        st.caption('Select one or several questions or whole groups, then drag any selected handle. Shift + click selects a range. Make as many moves as needed, then click Save order once.')
        result = question_order(rows, revision, f'order_{key}')
        event = result.reordered
        if event and event.get('revision') == revision:
            try:
                changed = reorder_rows(rows, event['ids'])
                if event['ids'] != [r['Question ID'] for r in rows]:
                    commit(changed, 'Question order updated.')
            except (ValueError, KeyError, TypeError) as exc:
                st.error(f'Move not applied: {exc}')
    return pd.DataFrame(export_rows(model['rows']))
