import pandas as pd
import streamlit as st

from templyfier.review import audit_questions, preview_rows


def render_review_center(rows, key):
    audit=audit_questions(rows)
    with st.container(border=True):
        st.markdown('**Priorités de vérification CMI**')
        columns=st.columns(3)
        columns[0].metric('Questions à corriger',len({i['Question ID'] for i in audit['blockers']}))
        columns[1].metric('Questions avec un point à vérifier',len(audit['attention_ids']))
        columns[2].metric('Questions gardées',audit['kept'])
        if not audit['blockers']:
            st.success('No correction is required. The remaining review suggestions are optional CMI checks.')
        else:
            st.error('Correct the items marked as errors before generation. Other review suggestions remain optional.')
        if audit['issues']:
            ordered=sorted(audit['issues'],key=lambda i:(i['Niveau']!='À corriger',i['Question ID']))
            with st.expander('All review points — details',expanded=bool(audit['blockers'])):
                st.dataframe(pd.DataFrame(ordered).drop(columns=['Code']),hide_index=True,width='stretch',height=min(275,38+35*len(ordered)))
            st.caption('Use the guided question review below to check or change these suggestions one by one.')
        elif not audit['kept']:
            st.info('Aucune question gardée. Coche « Garder » sur au moins une question avant de générer.')
        else:
            st.success('Aucune anomalie détectée par ces contrôles. Relis les choix métier avant de valider.')
    return audit


def render_structure_preview(rows, available_by_id, split_names, key, metric_availability_by_id=None, result_export_count=None):
    with st.expander('Voir la structure des lignes avant génération',expanded=False):
        st.caption('Aperçu des libellés et des métriques sélectionnées, dans leur ordre prévu. Aucune valeur n’est simulée. La disponibilité peut varier entre les exports ; les valeurs seront prises dans les fichiers source lors de la génération.')
        split=st.selectbox('Filtre de splits de cet aperçu',['Tous les choix']+list(dict.fromkeys(split_names)),key=f'preview_split_{key}')
        planned=preview_rows(rows,None if split=='Tous les choix' else split,available_by_id,metric_availability_by_id,result_export_count)
        st.caption(f'{len(planned)} ligne(s) de métriques prévues dans cette vue, hors en-têtes de section et synthèses KPI.')
        if planned:
            st.dataframe(pd.DataFrame(planned),hide_index=True,width='stretch',height=360)
        else:
            st.info('Aucune ligne prévue pour ce filtre. Vérifie les questions gardées, les métriques et les splits inclus.')
