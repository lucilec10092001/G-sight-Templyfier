"""Authentication precedes uploads, help and all persistent preferences."""
import time
import streamlit as st
from templyfier import server_storage as storage


def initialize_access():
    storage.bind_identity(None)
    try:
        enabled = storage.server_mode()
        if not enabled:
            return
        storage.database_path()  # Fail closed, never fall back to desktop storage.
        if not st.user.is_logged_in:
            st.title('G-Sight Templyfier')
            st.info('Connecte-toi avec ton compte professionnel pour ouvrir ton espace CMI.')
            if st.button('Se connecter avec le SSO', type='primary'):
                st.login()
            st.stop()
        identity = storage.verified_identity(dict(st.user))
        expiry = st.user.get('exp')
        if not isinstance(expiry, (int, float)) or expiry <= time.time():
            raise ValueError('La session SSO a expiré. Déconnecte-toi puis reconnecte-toi.')
        if st.session_state.get('_authenticated_identity') != identity.key:
            st.session_state.clear()
            st.session_state['_authenticated_identity'] = identity.key
        storage.bind_identity(identity)
        storage.read_document('preferences', {})
        with st.sidebar:
            st.caption('Serveur interne • espace authentifié')
            if st.button('Se déconnecter', key='server_logout', width='stretch'):
                st.session_state.clear()
                storage.bind_identity(None)
                st.logout()
                st.stop()
            with st.expander('Informations de mon accès'):
                st.code(identity.key, language=None)
                st.caption('Identifiant technique pour l’IT. Il ne donne aucun accès par lui-même.')
            library = st.selectbox('Habitudes à consulter', ['Mon espace', 'Référence équipe'], key='server_library')
            if st.session_state.get('_memory_library') != library:
                st.session_state['_memory_library'] = library
                st.session_state['memory_client'] = 'Sans mémoire client'
                st.session_state.pop('memory_new_client', None)
            storage.select_library('team' if library == 'Référence équipe' else 'personal')
            if library == 'Référence équipe':
                st.caption('Choix validés par les référents. ' + ('Tu peux publier les corrections validées ici.' if identity.admin else 'Consultation et application uniquement.'))
            else:
                st.caption('Tes habitudes et tes profils restent séparés de ceux des autres CMI.')
            if identity.admin:
                with st.expander('Journal des modifications de mémoire'):
                    st.dataframe(storage.audit_events(), hide_index=True, width='stretch')
    except (ValueError, OSError) as exc:
        st.error(str(exc))
        st.caption('Access suspended: ask IT to review SERVER_DEPLOYMENT.md. Local mode is not activated as a replacement.')
        if st.user.is_logged_in and st.button('Changer de compte / se reconnecter'):
            st.session_state.clear()
            storage.bind_identity(None)
            st.logout()
        st.stop()
