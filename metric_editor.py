import hashlib

import pandas as pd
import streamlit as st

from templyfier.review import metric_presets, plan_metric_change
from templyfier.editor_model import QUESTION_TYPES
from templyfier.smart import _metric_key
from templyfier.english_catalog import TEXT


def render_type_metric_editor(rows, key, revision, commit=None):
    """Offer one visible recipe per question type before question-level exceptions."""
    kept = [row for row in rows if row.get('Keep')]
    if not kept:
        return
    st.markdown('### Default results by question type')
    st.caption(
        'Set the default once for every question type. These defaults are applied automatically; '
        'you can still change the Metrics cell of any question in the table below.'
    )
    selected_type = st.segmented_control(
        'Question type recipe', list(QUESTION_TYPES),
        format_func=lambda value: TEXT.get(value, value),
        default=QUESTION_TYPES[0], key=f'type_metric_kind_{key}_{revision}',
    )
    candidates = [row for row in kept if row['Type'] == selected_type]
    type_display = TEXT.get(selected_type, selected_type)
    if not candidates:
        defaults = {
            'Standard': 'Mean, Top Box, Top 2 Boxes and Bottom 2 Boxes when available.',
            'Strength': 'The available Too weak, Just about right and Too strong responses.',
            'CATA': 'The positive / 2- response for each item.',
            'Listing': 'All individual response options.',
            'Bipolaire': 'All individual scale points.',
            'Preference': 'All individual products or preference options.',
            'Autres': 'All individual project-specific response options.',
        }
        st.info(
            f'No {type_display} question is currently detected. Its preset is already ready: '
            f'{defaults[selected_type]} If you change a question to this type in the table, '
            'Templyfier applies this preset automatically.'
        )
        return
    source = candidates[0]
    current_recipes = {tuple(_metric_key(metric) for metric in row['Selected metrics']) for row in candidates}
    if len(current_recipes) == 1:
        st.caption(f'{len(candidates)} {type_display} question(s) currently use the same recipe.')
    else:
        st.caption(f'{len(candidates)} {type_display} question(s) currently contain {len(current_recipes)} recipes. Applying a type recipe keeps questions without a complete safe match unchanged.')
    available = source['Available metric list']
    selected = st.multiselect(
        f'Results shown in Excel for {type_display}', available,
        default=[metric for metric in available if _metric_key(metric) in {_metric_key(value) for value in source['Selected metrics']}],
        key=f'type_metric_values_{key}_{revision}_{selected_type}',
        help='The list uses one representative question. Matching response codes and boxes are transferred only when the correspondence is complete and safe.',
    )
    if st.button(f'Apply to all {type_display} questions', key=f'apply_type_metrics_{key}_{revision}_{selected_type}'):
        try:
            changed, preview = plan_metric_change(
                rows, source['Question ID'], selected, source.get('Metric labels', {}),
                'Toutes les questions de ce type',
            )
            if commit is not None:
                skipped = sum(item['R�sultat'].startswith('Inchang�e') for item in preview)
                commit(
                    changed,
                    f'Metric recipe applied to {type_display}; '
                    f'{skipped} question(s) left unchanged because no safe match was available.',
                )
            else:
                st.session_state[f'metric_batch_{key}'] = {
                    'revision': revision, 'rows': changed, 'preview': preview,
                }
                st.session_state[f'editor_refresh_{key}'] = True
        except ValueError as exc:
            st.error(str(exc))


def render_metric_editor(rows, key, revision, commit):
    st.markdown('#### Question-specific metric exception')
    st.caption('Use this only when one question needs a different result from its question-type recipe.')
    by_id={r['Question ID']:r for r in rows}
    selected_id=st.selectbox('1. Question to edit',list(by_id),
        format_func=lambda q:f"{by_id[q]['Display label']}"+(f" — {by_id[q]['Metric label']}" if by_id[q].get('Metric label') else ''),
        key=f'metric_question_{key}',persist_state='session')
    row=by_id[selected_id]
    qkey=hashlib.sha1(selected_id.encode()).hexdigest()[:12]
    type_display=TEXT.get(row['Type'],row['Type'])
    st.caption(f"Detected type: {type_display} · {len(row['Selected metrics'])} result row(s) will be shown in Excel")
    st.caption(f"Source question: {selected_id} · {len(row['Available metric list'])} source metrics available")
    type_help={
        'Standard':'Standard scale: the suggested recipe usually contains Mean, Top Box, Top 2 Boxes and Bottom 2 Boxes. You can add or remove any available box.',
        'Strength':'Strength scale: keep the individual response levels that explain whether the product is too weak, just right or too strong.',
        'CATA':'CATA: choose the positive response (usually 2-) or the No response (usually 1-No), depending on the client convention.',
        'Bipolaire':'Bipolar scale: keep individual scale points or choose the available top/bottom boxes. Mean is optional.',
        'Listing':'Listing: keep the individual response options. Mean and box shortcuts are normally not relevant.',
        'Preference':'Preference: keep the individual products or options such as preferred, I prefer or liked the most. Mean and box shortcuts are normally not relevant.',
        'Autres':'Project-specific question: keep only the source responses needed for this project.',
    }
    st.caption('Suggested approach — '+type_help.get(row['Type'],'Review the available source metrics and keep only those needed for the output.'))
    if row.get('CMI note'):
        st.caption('Point métier : '+str(row['CMI note']))
    available=row['Available metric list']
    missing=[m for m in row['Selected metrics'] if _metric_key(m) not in {_metric_key(a) for a in available}]
    if missing:st.warning('Métriques du profil absentes de ces exports : '+', '.join(missing))
    presets=metric_presets(row)
    preset_labels={name:(f'Current selection — {len(metrics)} metric(s)' if name=='Choix actuels'
        else f'Recommended for {type_display} — {len(metrics)} metric(s)' if name=='Proposition du type'
        else f'{name} — {len(metrics)} metric(s)') for name,metrics in presets.items()}
    preset=st.selectbox('2. Start from a suggested selection',list(presets),format_func=lambda name:preset_labels[name],key=f'metric_preset_{key}_{qkey}_{revision}',
        help='This only prepares the checkboxes below. Nothing changes until you select Apply.')
    pkey=hashlib.sha1(preset.encode()).hexdigest()[:8]
    selected_keys={_metric_key(m) for m in presets[preset]}
    show_all=st.checkbox('Optional customisation — show all source metrics',value=False,
        key=f'metric_show_all_{key}_{qkey}_{revision}',
        help='Turn this on to add metrics outside the current recipe, such as Top 3 Boxes or individual response levels.')
    with st.form(f'metric_form_{key}_{qkey}_{revision}'):
        presence=row.get('Metric availability',{})
        total=row.get('Result export count',0)
        displayed=available if show_all else [m for m in available if _metric_key(m) in selected_keys]
        records=[]
        for metric in displayed:
            record={'Garder':_metric_key(metric) in selected_keys,'Métrique G-Sight':metric,
                'Libellé clean':row['Metric labels'].get(metric,metric)}
            if total>1:record['Présence dans les exports contenant la question']=f"{len(presence.get(metric,[]))}/{total}"
            records.append(record)
        columns=['Garder','Métrique G-Sight']+(['Présence dans les exports contenant la question'] if total>1 else [])+['Libellé clean']
        frame=pd.DataFrame(records,columns=columns)
        disabled=['Métrique G-Sight']+(['Présence dans les exports contenant la question'] if total>1 else [])
        edits=st.data_editor(frame,hide_index=True,width='stretch',height=min(480,38+35*max(1,len(displayed))),
            disabled=disabled,key=f'metric_table_{key}_{qkey}_{revision}_{pkey}_{int(show_all)}',
            column_config={'Garder':st.column_config.CheckboxColumn(),
                           'Métrique G-Sight':st.column_config.TextColumn('Source metric'),
                           'Libellé clean':st.column_config.TextColumn('Name shown in Excel',required=True)})
        group_count=sum(1 for candidate in rows if candidate.get('Keep') and row.get('Group ID') and candidate.get('Group ID')==row.get('Group ID'))
        type_count=sum(1 for candidate in rows if candidate.get('Keep') and candidate.get('Type')==row.get('Type'))
        scopes=['Cette question']
        if row.get('Group ID') and group_count>1:
            scopes.append('Tout le groupe')
        if type_count>1:
            scopes.append('Toutes les questions de ce type')
        scope_labels={
            'Cette question':'Only this question',
            'Tout le groupe':f'All {group_count} items in this group',
            'Toutes les questions de ce type':f'All {type_count} questions detected as {type_display}',
        }
        scope=st.radio('3. Apply the selection to',scopes,format_func=lambda value:scope_labels[value],
            horizontal=False,key=f'metric_target_{key}_{qkey}_{revision}',
            help='Choose the first option when unsure. Multiple-question changes always show a preview before confirmation.')
        st.caption('Example: applying a Standard recipe to all Standard questions updates only questions with the same available results. Questions without a safe match stay unchanged. Names shown in Excel remain specific to this question.')
        if st.form_submit_button('Save metric changes',type='primary'):
            chosen=edits.loc[edits['Garder'],'Métrique G-Sight'].tolist()
            labels=dict(zip(edits['Métrique G-Sight'],edits['Libellé clean']))
            try:
                changed,preview=plan_metric_change(rows,selected_id,chosen,labels,scope)
                if scope=='Cette question':
                    commit(changed,'Metric selection updated for this question.')
                else:
                    st.session_state[f'metric_batch_{key}']={'revision':revision,'rows':changed,'preview':preview}
                    # Upstream memory controls must also reflect this pending batch.
                    st.session_state[f'editor_refresh_{key}']=True
            except ValueError as exc:
                st.error(str(exc))

    pending_key=f'metric_batch_{key}'
    pending=st.session_state.get(pending_key)
    if pending and pending['revision']!=revision:
        st.session_state.pop(pending_key,None)
        st.info('L’aperçu groupé a été annulé car les questions ont changé. Reprépare la sélection si nécessaire.')
        pending=None
    if pending:
        with st.container(border=True):
            st.markdown('**Vérifier l’effet du changement groupé**')
            st.dataframe(pd.DataFrame(pending['preview']),hide_index=True,width='stretch',height=min(330,38+35*len(pending['preview'])))
            skipped=sum(p['Résultat'].startswith('Inchangée') for p in pending['preview'])
            if skipped:st.warning(f'{skipped} question(s) laissée(s) inchangée(s) faute de correspondance complète et sûre.')
            st.caption('Les autres questions ne seront pas modifiées. La génération est suspendue jusqu’à confirmation ou abandon de cet aperçu.')
            with st.container(horizontal=True):
                if st.button('Confirmer les métriques groupées',key=f'confirm_metric_batch_{key}',type='primary'):
                    st.session_state.pop(pending_key,None)
                    commit(pending['rows'],f'Métriques groupées appliquées ; {skipped} question(s) laissée(s) inchangée(s).')
                if st.button('Abandonner cet aperçu',key=f'cancel_metric_batch_{key}'):
                    st.session_state.pop(pending_key,None)
                    st.session_state[f'editor_refresh_{key}']=True
