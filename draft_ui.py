import json
import streamlit as st
from templyfier import drafts
from templyfier.server_storage import server_mode

def _sources(exports,cmr):
    return drafts.fingerprints([(f.name,f.getvalue()) for f in exports],(cmr.name,cmr.getvalue()) if cmr else None)

def render_draft_resume(exports,cmr):
    selected=None
    def selection_changed():st.session_state['apply_resumed_draft']=False
    with st.expander('Resume an interrupted project — settings only'):
        st.caption('Drafts keep applied settings and source fingerprints, not raw exports or consumer scores. Reload the original exports and optional CMR to resume. Unsaved table edits and undo history are not included.')
        if server_mode():
            try:
                days=drafts.retention_days()
                if days:
                    records=drafts.list_drafts()
                    identifier=st.selectbox('Personal server draft',['']+list(records),format_func=lambda k:records[k]['name'] if k else 'No draft selected',key='resume_draft_id',on_change=selection_changed)
                    if identifier not in {'',*records}:raise ValueError('Unknown draft selection.')
                    if identifier:
                        record=records[identifier];selected=record['bundle']
                        st.caption(f"Saved {record['saved'][:10]} · Expires {record['expires'][:10]} · Personal workspace only")
                        confirmed=st.checkbox('Confirm deletion of this personal draft',key=f'delete_draft_confirm_{identifier}')
                        if st.button('Delete selected draft',disabled=not confirmed,key=f'delete_draft_{identifier}'):
                            drafts.delete_draft(identifier,record['token'])
                            st.session_state.pop('resume_draft_id',None);st.rerun()
                else:st.info('Server drafts are disabled until IT sets TEMPLYFIER_DRAFT_RETENTION_DAYS. Portable draft files remain available.')
            except ValueError as exc:st.error(str(exc))
        uploaded=st.file_uploader('Portable project draft',type=['json'],key='portable_draft_upload',on_change=selection_changed)
        if uploaded:
            try:
                if uploaded.size>5*1024*1024:raise ValueError('Draft files must be at most 5 MB.')
                selected=drafts.validate_bundle(json.loads(uploaded.getvalue()))
            except (ValueError,TypeError,KeyError,RecursionError) as exc:
                st.error(f'Cannot load this draft: {exc}');selected=None
        if selected:
            compatible=bool(exports) and drafts.matches(selected,_sources(exports,cmr))
            if not compatible:st.warning('Source files do not match this draft. Reload the original DataViz files and CMR. To adapt choices to another wave, use a reusable settings profile instead.')
            if st.checkbox('Use this draft for the reloaded project',disabled=not compatible,key='apply_resumed_draft') and compatible:return selected
    return None

def render_draft_save(profile_bytes,exports,cmr,split_names,key,pending):
    with st.expander('Save a project draft — resume later'):
        st.caption('Only applied choices are saved. Click Apply in edited tables first. Raw files and result workbooks are never saved in the draft.')
        try:bundle=drafts.make_bundle(json.loads(profile_bytes),_sources(exports,cmr),split_names)
        except (ValueError,TypeError) as exc:
            st.error(f'Cannot save this draft: {exc}');return
        st.download_button('Download portable project draft',json.dumps(bundle,ensure_ascii=False,indent=2).encode(),
            file_name='Templyfier_project_draft.json',mime='application/json',disabled=pending,key=f'draft_download_{key}')
        if server_mode():
            try:
                days=drafts.retention_days()
                if not days:
                    st.info('Ask IT to configure draft retention before enabling personal server drafts.')
                    return
                st.caption(f'Server drafts expire after {days} days and are private, including when Team reference is selected.')
                name=st.text_input('Draft name',key=f'draft_name_{key}',max_chars=100)
                if st.button('Save new personal server draft',disabled=pending or not name.strip(),key=f'draft_save_{key}'):
                    drafts.save_draft(name,bundle);st.success('Personal draft saved. It is available in Resume an interrupted project on the next refresh.')
            except ValueError as exc:st.error(str(exc))
