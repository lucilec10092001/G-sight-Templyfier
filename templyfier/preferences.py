from __future__ import annotations

import json
import os
from pathlib import Path
from . import server_storage as storage


PREFERENCES_VERSION = 1


def preferences_path() -> Path:
    """Return a per-Windows-user path that survives browser and app restarts."""
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if base:
        return Path(base) / "G-Sight Templyfier" / "preferences.json"
    return Path.home() / ".g_sight_templyfier" / "preferences.json"


def read_preferences(path: Path | None = None) -> dict:
    if storage.server_mode():
        if path is not None:
            raise ValueError('Chemin personnalisé interdit en mode serveur.')
        return storage.read_document('preferences', {})
    target = path or preferences_path()
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def has_seen_onboarding(path: Path | None = None) -> bool:
    return bool(read_preferences(path).get("onboarding_seen"))


def mark_onboarding_seen(path: Path | None = None) -> bool:
    """Persist first-run completion; failure never prevents use of the app."""
    if storage.server_mode():
        if path is not None:
            raise ValueError('Chemin personnalisé interdit en mode serveur.')
        def update(payload):
            payload.update({'preferences_version':PREFERENCES_VERSION, 'onboarding_seen':True})
            return payload, True
        return storage.mutate_document('preferences', {}, 'preferences:onboarding', update)
    target = path or preferences_path()
    payload = read_preferences(target)
    payload.update({
        "preferences_version": PREFERENCES_VERSION,
        "onboarding_seen": True,
    })
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(target)
    except OSError:
        return False
    return True


def saved_cmi_profiles(path: Path | None = None) -> dict[str, dict]:
    profiles = read_preferences(path).get("cmi_profiles", {})
    return profiles if isinstance(profiles, dict) else {}


def save_cmi_profile(name: str, profile: dict, path: Path | None = None) -> bool:
    """Save an explicit, user-named CMI profile on this computer."""
    clean_name = " ".join(str(name).split()).strip()
    if not clean_name or not isinstance(profile, dict):
        return False
    if storage.server_mode():
        if path is not None:
            raise ValueError('Chemin personnalisé interdit en mode serveur.')
        def update(payload):
            profiles = payload.get('cmi_profiles', {})
            if not isinstance(profiles, dict):
                raise ValueError('Profils serveur illisibles ; aucune modification effectuée.')
            profiles[clean_name] = profile
            payload.update({'preferences_version':PREFERENCES_VERSION, 'cmi_profiles':profiles})
            return payload, True
        return storage.mutate_document('preferences', {}, 'preferences:save-profile', update)
    target = path or preferences_path()
    payload = read_preferences(target)
    profiles = payload.get("cmi_profiles", {})
    if not isinstance(profiles, dict):
        profiles = {}
    profiles[clean_name] = profile
    payload.update({
        "preferences_version": PREFERENCES_VERSION,
        "cmi_profiles": profiles,
    })
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(target)
    except OSError:
        return False
    return True


def delete_cmi_profile(name: str, path: Path | None = None) -> bool:
    if storage.server_mode():
        if path is not None:
            raise ValueError('Chemin personnalisé interdit en mode serveur.')
        def update(payload):
            profiles = payload.get('cmi_profiles', {})
            if not isinstance(profiles, dict):
                raise ValueError('Profils serveur illisibles ; aucune modification effectuée.')
            if name not in profiles:
                return payload, False
            del profiles[name]
            return payload, True
        return storage.mutate_document('preferences', {}, 'preferences:delete-profile', update)
    target = path or preferences_path()
    payload = read_preferences(target)
    profiles = payload.get("cmi_profiles", {})
    if not isinstance(profiles, dict) or name not in profiles:
        return False
    del profiles[name]
    payload["cmi_profiles"] = profiles
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(target)
    except OSError:
        return False
    return True
