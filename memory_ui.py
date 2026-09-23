"""Native Streamlit controls for teaching and reviewing local client habits."""
from copy import deepcopy
import hashlib
import json

import pandas as pd
import streamlit as st

from templyfier.client_memory import (SCOPES, apply_suggestions, delete_rules,
    ensure_client, load_memories, memory_suggestions, teach, teaching_candidates, client_token,
    import_client_memory, validate_memories)
from templyfier import server_storage as storage


def _fingerprint(value):
    return hashlib.sha1(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]


def render_memory_client():
    st.markdown('**Mémoire du client — facultatif**')
    st.caption('Le tool retient uniquement les corrections que tu lui enseignes et propose leur réutilisation sur des questionnaires compatibles. La mémoire conserve des libellés et des choix de structure, pas les résultats consommateurs.')
    writable = storage.can_write_memory()
    try:
        payload = load_memories()
    except ValueError as exc:
        st.warning(str(exc))
        st.caption('Le reste du Templyfier fonctionne sans cette mémoire. Le fichier illisible est conservé pour réparation.')
        return None
    clients = payload['clients']
    if writable:
        with st.expander('Transférer une mémoire existante — ordinateur vers serveur, par exemple'):
            st.caption('Charge une sauvegarde de mémoire Templyfier. Vérifie le client et les choix avant import : rien n’est enregistré au simple chargement. Une référence équipe ne se modifie que dans l’espace d’un référent.')
            upload = st.file_uploader('Sauvegarde de mémoire client', type=['json'], key='memory_import_file')
            if upload:
                try:
                    raw = upload.getvalue()
                    if len(raw) > 2*1024*1024:
                        raise ValueError('Sauvegarde trop grande : limite de 2 Mo.')
                    imported = validate_memories(json.loads(raw.decode('utf-8-sig')))
                    options = list(imported['clients'])
                    if not options:
                        raise ValueError('Cette sauvegarde ne contient aucun client.')
                    cid = st.selectbox('Client à importer', options, format_func=lambda c:imported['clients'][c]['name'])
                    existing = clients.get(cid)
                    prior = {r['id']:r for r in existing['rules']} if existing else {}
                    incoming = imported['clients'][cid]['rules']
                    preview = [{'Habitude':r['description'], 'Choix importé':str(r['value']),
                        'Choix actuel':str(prior[r['id']]['value']) if r['id'] in prior else 'Nouvelle habitude'} for r in incoming]
                    st.dataframe(pd.DataFrame(preview), hide_index=True, width='stretch')
                    st.caption('Les habitudes affichées remplacent les choix du même contexte. Les autres habitudes existantes sont conservées. Le projet ouvert reste inchangé.')
                    import_token = _fingerprint([payload, imported, cid])
                    checked = st.checkbox('Je valide ces habitudes pour l’espace sélectionné', key=f'memory_import_confirm_{import_token}')
                    if st.button('Importer les habitudes affichées', disabled=not checked, key=f'memory_import_apply_{import_token}') and checked:
                        import_client_memory(imported, cid, client_token(existing) if existing else 'absent')
                        st.session_state['memory_new_client'] = cid
                        st.session_state['memory_refresh_requested'] = True
                except (ValueError, OSError, KeyError) as exc:
                    st.error(str(exc))
    choices = ['Sans mémoire client'] + [c['name'] for c in clients.values()] + (['Nouveau client…'] if writable else [])
    current = st.session_state.get('memory_client', choices[0])
    if current not in choices:
        st.session_state['memory_client'] = choices[0]
    selected = st.selectbox('Client de ce projet', choices, key='memory_client', persist_state='session')
    if selected == 'Nouveau client…':
        with st.form('new_memory_client'):
            name = st.text_input('Nom du client à mémoriser', max_chars=100)
            if st.form_submit_button('Créer la mémoire de ce client'):
                try:
                    cid = ensure_client(name)
                    st.session_state['memory_new_client'] = cid
                    st.session_state['memory_refresh_requested'] = True
                except (ValueError, OSError) as exc:
                    st.error(str(exc))
        return None
    client_id = next((cid for cid,c in clients.items() if c['name'] == selected), None)
    if client_id is None:
        return None
    client = clients[client_id]
    rules = client['rules']
    expected = client_token(client)
    token = _fingerprint([client_id, rules])
    with st.expander(f"Consulter ou effacer les habitudes de {client['name']} ({len(rules)})"):
        st.download_button('Sauvegarder la mémoire de ce client',
            data=json.dumps({'version':1,'clients':{client_id:client}},ensure_ascii=False,indent=2).encode('utf-8'),
            file_name='Templyfier_memoire_client.json', mime='application/json', key=f'memory_backup_{token}')
        st.caption('Cette sauvegarde contient les libellés et les habitudes du client. À conserver dans un emplacement interne autorisé, même sans résultats consommateurs.')
        if rules:
            st.dataframe(pd.DataFrame([{'Habitude':r['description'], 'Portée':r['scope'],
                'Dernière validation':r['updated'][:10], 'Projets mémorisés':len(r['evidence'])} for r in rules]),
                hide_index=True, width='stretch')
            to_delete = st.multiselect('Habitudes à oublier', [r['id'] for r in rules],
                format_func=lambda rid:next(r['description'] for r in rules if r['id']==rid), key=f'memory_delete_{token}')
            if st.button('Oublier les habitudes sélectionnées', disabled=not to_delete or not writable, key=f'memory_delete_apply_{token}') and writable:
                try:
                    delete_rules(client_id, to_delete, expected=expected)
                    st.session_state['memory_refresh_requested'] = True
                except (ValueError, OSError) as exc:
                    st.error(str(exc))
        else:
            st.caption('Aucune habitude apprise. Tu pourras lui enseigner tes corrections dans l’éditeur.')
        confirmed = st.checkbox('Je souhaite effacer toute la mémoire de ce client', key=f'memory_forget_confirm_{client_id}')
        if st.button('Effacer toute la mémoire du client', disabled=not confirmed or not writable, key=f'memory_forget_{client_id}') and confirmed and writable:
            try:
                delete_rules(client_id, expected=expected)
                st.session_state['memory_refresh_requested'] = True
            except (ValueError, OSError) as exc:
                st.error(str(exc))
        st.caption('Effacer une habitude ne modifie pas le projet ouvert. Pour corriger une habitude, enseigne un nouveau choix sur la même question ou la même échelle : il remplacera le précédent.')
    return {'id':client_id, 'name':client['name'], 'rules':rules, 'expected':expected, 'writable':writable}


def prepare_memory_client_selection():
    # Called before the widget renders, including after client creation.
    cid = st.session_state.pop('memory_new_client', None)
    if cid is not None:
        try:
            st.session_state['memory_client'] = load_memories()['clients'][cid]['name']
        except (ValueError, KeyError):
            pass


def render_memory_assistant(rows, baseline, memory, key, revision, commit, protected_ids=(), pending_metrics=False, project_key=None):
    if not memory:
        return set()
    client_id, name, rules = memory['id'], memory['name'], memory['rules']
    token = _fingerprint([client_id, rules, revision, rows])
    st.markdown(f'**Reusable preferences for {name}**')
    st.caption('How it works: Templyfier compares this project with choices previously approved for this client. It shows safe suggestions; you choose what to apply. Nothing changes or becomes a preference automatically.')
    proposals, omissions, ignored = memory_suggestions(baseline, rows, rules, protected_ids)
    if proposals:
        st.info(f'{len(proposals)} suggestion(s) issue(s) des habitudes du client.')
        with st.form(f'memory_apply_form_{key}_{token}'):
            records = [{'id':p['id'], 'Appliquer':False, 'Choix':{'question':'Question','metrics':'Métriques','group':'Regroupement'}[p['kind']],
                'Questions':' · '.join(p['members']), 'Avant':str(p['before']), 'Après':str(p['after']),
                'Libellés proposés':json.dumps(p.get('renamings',{}),ensure_ascii=False) if p.get('renamings') else '', 'Pourquoi ?':p['why']} for p in proposals]
            edits = st.data_editor(pd.DataFrame(records), hide_index=True, width='stretch', height=min(340,38+35*len(records)),
                key=f'memory_suggestions_{key}_{token}', disabled=['id','Choix','Questions','Avant','Après','Libellés proposés','Pourquoi ?'],
                column_config={'id':None, 'Appliquer':st.column_config.CheckboxColumn(pinned=True)})
            apply_selected = st.form_submit_button('Appliquer les suggestions du client', disabled=pending_metrics)
            apply_all = st.form_submit_button('Appliquer toutes les suggestions affichées', disabled=pending_metrics)
            if (apply_selected or apply_all) and not pending_metrics:
                try:
                    selected = [p['id'] for p in proposals] if apply_all else edits.loc[edits['Appliquer'], 'id'].tolist()
                    commit(apply_suggestions(rows, proposals, selected), f'Habitudes de {name} appliquées ; tu peux Annuler.')
                except ValueError as exc:
                    st.error(str(exc))
    elif rules:
        st.caption('Aucun changement à proposer : choix déjà identiques, profil prioritaire ou questionnaire sans correspondance sûre.')
    if omissions:
        with st.expander('Habitudes non proposées par prudence'):
            st.dataframe(pd.DataFrame(omissions), hide_index=True, width='stretch')
    if ignored:
        st.caption(f'{len(ignored)} regroupement(s) déjà refusé(s) pour ce client sont masqués dans l’assistant général. Les questions restent intactes.')
        if st.checkbox('Réexaminer les regroupements refusés pour ce client', key=f'memory_reconsider_{key}_{client_id}'):
            ignored = set()
    if pending_metrics:
        st.caption('Termine ou abandonne l’aperçu de métriques groupées avant d’appliquer ou d’enseigner des habitudes.')

    if not memory.get('writable', True):
        st.caption('Référence équipe en consultation : applique ses habitudes au projet. Pour enseigner tes corrections, sélectionne Mon espace dans la barre latérale.')
        return ignored
    with st.expander('Save reviewed choices for future projects', expanded=not rules):
        candidates = teaching_candidates(baseline, rows)
        # Do not treat generated defaults or a previously taught identical choice as new learning.
        known = {(r['kind'], json.dumps(r['anchor'],sort_keys=True), json.dumps(r['value'],sort_keys=True)) for r in rules}
        candidates = [c for c in candidates if (c['kind'],json.dumps(c['anchor'],sort_keys=True),json.dumps(c['value'],sort_keys=True)) not in known]
        st.caption('After you edit and review this project, select only the choices that should be suggested again for this client. Consumer results are never stored, and every future suggestion still requires approval.')
        if candidates:
            with st.form(f'memory_teach_form_{key}_{token}'):
                records = [{'id':c['candidate_id'], 'Retenir':False, 'Correction':c['description'],
                    'Portée':SCOPES[0], 'Élargissement possible':'Oui' if c['can_widen'] else 'Non'} for c in candidates]
                edits = st.data_editor(pd.DataFrame(records), hide_index=True, width='stretch', height=min(340,38+35*len(records)),
                    key=f'memory_teaching_{key}_{token}', disabled=['id','Correction','Élargissement possible'],
                    column_config={'id':None, 'Retenir':st.column_config.CheckboxColumn(pinned=True),
                        'Portée':st.column_config.SelectboxColumn(options=list(SCOPES), required=True)})
                st.caption('Question équivalente compare le wording source sans son numéro. Type et échelle compatibles exige les mêmes réponses et le même stage ; réservé aux recettes Standard, Strength ou CATA reconnues. Les renommages de métriques restent propres à la question. Deux recettes contradictoires ne peuvent pas être apprises ensemble.')
                if st.form_submit_button('Retenir ces choix pour le client', disabled=pending_metrics) and not pending_metrics:
                    try:
                        by_id = {c['candidate_id']:c for c in candidates}
                        selected = []
                        for record in edits.to_dict('records'):
                            if record['Retenir']:
                                candidate = deepcopy(by_id[record['id']])
                                candidate['scope'] = record['Portée']
                                selected.append(candidate)
                        count = teach(client_id, selected, project_key or key, expected=memory.get('expected'))
                        st.session_state[f'memory_notice_{key}'] = f'{count} habitude(s) retenue(s) pour {name}. Elles seront proposées sur les prochains projets compatibles.'
                        st.session_state[f'editor_refresh_{key}'] = True
                    except (ValueError, OSError, KeyError) as exc:
                        st.error(str(exc))
        else:
            st.caption('Aucune nouvelle correction à retenir. Applique d’abord tes modifications de questions, groupes ou métriques.')
        if st.session_state.get(f'memory_notice_{key}'):
            st.success(st.session_state[f'memory_notice_{key}'])
    return ignored
