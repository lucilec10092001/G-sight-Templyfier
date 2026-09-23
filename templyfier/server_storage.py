"""Internal-server persistence. Identity comes exclusively from the OIDC gate.

One host, durable local disk, short SQLite transactions. No survey result storage.
ContextVars keep identities isolated between Streamlit ScriptRunner threads.
"""
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3


@dataclass(frozen=True)
class Identity:
    key: str
    admin: bool = False


_identity = ContextVar('templyfier_identity', default=None)
_library = ContextVar('templyfier_library', default='personal')


def server_mode():
    mode = os.environ.get('TEMPLYFIER_MODE', 'desktop').strip().lower()
    if mode not in {'desktop', 'server'}:
        raise ValueError('TEMPLYFIER_MODE doit être desktop ou server. Aucun repli automatique.')
    return mode == 'server'


def identity_key(issuer, subject):
    return hashlib.sha256((str(issuer) + '\n' + str(subject)).encode()).hexdigest()


def verified_identity(claims):
    """Validate already authenticated st.user claims against the IT allowlist."""
    issuer = os.environ.get('TEMPLYFIER_OIDC_ISSUER', '').strip()
    allowed = {s.strip() for s in os.environ.get('TEMPLYFIER_ALLOWED_USERS', '').split(',') if s.strip()}
    admins = {s.strip() for s in os.environ.get('TEMPLYFIER_ADMINS', '').split(',') if s.strip()}
    if not issuer or not allowed or not admins.issubset(allowed):
        raise ValueError('L’IT doit configurer l’émetteur OIDC, les accès CMI et les référents.')
    if claims.get('iss') != issuer or not isinstance(claims.get('sub'), str) or not claims['sub']:
        raise ValueError('Identité SSO non reconnue pour cette application.')
    key = identity_key(issuer, claims['sub'])
    if key not in allowed:
        raise ValueError('Ce compte n’a pas accès au Templyfier. Contacte le référent CMI.')
    return Identity(key, key in admins)


def bind_identity(identity):
    _identity.set(identity)
    _library.set('personal')


def current_identity():
    identity = _identity.get()
    if not isinstance(identity, Identity):
        raise ValueError('Connexion SSO requise pour accéder à la mémoire serveur.')
    return identity


def select_library(library):
    if library not in {'personal', 'team'}:
        raise ValueError('Espace de mémoire inconnu.')
    if server_mode():
        current_identity()
    _library.set(library)


def can_write_memory():
    return not server_mode() or _library.get() != 'team' or current_identity().admin


def _scope(document, write=False):
    identity = current_identity()
    if document == 'memory' and _library.get() == 'team':
        if write and not identity.admin:
            raise ValueError('Seul un référent autorisé peut modifier la référence équipe.')
        return 'team'
    if document not in {'memory', 'preferences', 'drafts'}:
        raise ValueError('Document de préférences inconnu.')
    return 'personal:' + identity.key


def database_path():
    raw = os.environ.get('TEMPLYFIER_DATA_DIR', '').strip()
    folder = Path(raw)
    code = Path(__file__).resolve().parents[1]
    if not raw or not folder.is_absolute() or raw.startswith(('\\\\', '//')):
        raise ValueError('TEMPLYFIER_DATA_DIR doit désigner un dossier absolu sur disque local persistant, séparé du code.')
    folder = folder.resolve()
    if folder == code or code in folder.parents or not folder.is_dir():
        raise ValueError('Le dossier de mémoire doit exister et être séparé du dossier du code.')
    return folder / 'templyfier.sqlite3'


def _connect():
    connection = sqlite3.connect(database_path(), timeout=10, isolation_level=None)
    try:
        connection.execute('PRAGMA busy_timeout=10000')
        connection.execute('PRAGMA synchronous=FULL')
        if connection.execute('PRAGMA journal_mode').fetchone()[0].lower() != 'delete':
            raise ValueError('Journalisation serveur non prise en charge ; l’IT doit vérifier la base sans la réinitialiser.')
        # Rollback journal: brief serialized writes, no WAL/shared-memory dependency.
        version = connection.execute('PRAGMA user_version').fetchone()[0]
        if version not in {0, 1}:
            raise ValueError('Version de base serveur inconnue ; aucune modification effectuée.')
        connection.execute('CREATE TABLE IF NOT EXISTS documents (scope TEXT NOT NULL, name TEXT NOT NULL, payload TEXT NOT NULL, revision INTEGER NOT NULL, PRIMARY KEY(scope,name))')
        connection.execute('CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL, actor TEXT NOT NULL, scope TEXT NOT NULL, action TEXT NOT NULL, revision INTEGER NOT NULL)')
        connection.execute('PRAGMA user_version=1')
        return connection
    except Exception:
        connection.close()
        raise


def read_document(name, default):
    scope = _scope(name)
    try:
        with _connect() as connection:
            found = connection.execute('SELECT payload FROM documents WHERE scope=? AND name=?', (scope, name)).fetchone()
            value = json.loads(found[0]) if found else default
            if not isinstance(value, dict):
                raise ValueError('Document serveur incorrect.')
            return value
    except (sqlite3.Error, OSError, json.JSONDecodeError) as exc:
        raise ValueError('Mémoire serveur indisponible ou illisible ; aucune donnée écrasée. Contacte l’IT.') from exc
    finally:
        if 'connection' in locals():
            connection.close()


def mutate_document(name, default, action, change):
    """change(latest) -> (validated_payload, result), inside a write transaction."""
    scope = _scope(name, write=True)
    connection = None
    try:
        connection = _connect()
        connection.execute('BEGIN IMMEDIATE')
        found = connection.execute('SELECT payload,revision FROM documents WHERE scope=? AND name=?', (scope,name)).fetchone()
        latest, revision = (json.loads(found[0]), found[1]) if found else (default, 0)
        if not isinstance(latest, dict):
            raise ValueError('Document serveur incorrect ; aucune modification effectuée.')
        payload, result = change(deepcopy(latest))
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        if encoded != json.dumps(latest, ensure_ascii=False, sort_keys=True) or not found:
            revision += 1
            connection.execute('INSERT INTO documents VALUES (?,?,?,?) ON CONFLICT(scope,name) DO UPDATE SET payload=excluded.payload, revision=excluded.revision', (scope,name,encoded,revision))
            connection.execute('INSERT INTO audit(timestamp,actor,scope,action,revision) VALUES (?,?,?,?,?)', (datetime.now(timezone.utc).isoformat(timespec='seconds'), current_identity().key, scope, action, revision))
        connection.commit()
        return result
    except (sqlite3.Error, OSError, json.JSONDecodeError) as exc:
        raise ValueError('Enregistrement serveur impossible ; aucun choix perdu ou partiellement enregistré. Recharge, puis contacte l’IT si cela persiste.') from exc
    finally:
        if connection is not None:
            if connection.in_transaction:
                connection.rollback()
            connection.close()


def audit_events(limit=50):
    if not current_identity().admin:
        raise ValueError('Journal réservé aux référents autorisés.')
    connection = _connect()
    try:
        rows = connection.execute('SELECT timestamp,actor,scope,action,revision FROM audit ORDER BY id DESC LIMIT ?', (max(1,min(200,int(limit))),)).fetchall()
        return [dict(zip(('Date UTC','Auteur technique','Espace','Action','Version'), row)) for row in rows]
    finally:
        connection.close()
