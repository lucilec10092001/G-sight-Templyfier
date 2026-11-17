import pandas as pd
import streamlit as st

from templyfier.review import audit_questions, preview_rows


def render_review_center(rows, key):
    audit=audit_questions(rows)
    with st.container(border=True):
        st.markdown('**CMI review priorities**')
        columns=st.columns(3)
        columns[0].metric('Questions to correct',len({i['Question ID'] for i in audit['blockers']}))
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
            st.info('No question is currently kept. Tick Keep for at least one question before generating.')
        else:
            st.success('No issue was detected by these checks. Review the study choices before generating.')
    return audit


def render_structure_preview(rows, available_by_id, split_names, key, metric_availability_by_id=None, result_export_count=None):
    with st.expander('Preview the Excel row structure',expanded=False):
        st.caption('Preview of the selected labels and results in their planned order. No score is simulated; values are read from the uploaded sources during generation.')
        split=st.selectbox('Split filter for this preview',['All selections']+list(dict.fromkeys(split_names)),key=f'preview_split_{key}')
        planned=preview_rows(rows,None if split=='All selections' else split,available_by_id,metric_availability_by_id,result_export_count)
        st.caption(f'{len(planned)} result row(s) planned in this view, excluding section headers and KPI summaries.')
        if planned:
            st.dataframe(pd.DataFrame(planned),hide_index=True,width='stretch',height=360)
        else:
            st.info('No row is planned for this filter. Check the kept questions, selected results and included splits.')
