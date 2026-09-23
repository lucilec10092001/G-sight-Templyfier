"""Portable review of explicit choices, without survey values or input contents."""
import hashlib
import json
from .english_catalog import TEXT


def configuration_report(profile_bytes, configuration_hash, memory=None, server=False):
    profile = json.loads(profile_bytes)
    def cell(value):
        return str(value).replace('|', '\\|').replace('\n', ' ').replace('\r', ' ')
    lines = ['# G-Sight Templyfier v53 configuration', '',
        'This document describes project choices; it contains no consumer results.',
        'Status: review this configuration in the tool before generation.', '',
        f'Configuration fingerprint : `{configuration_hash}`',
        f'Profile fingerprint : `{hashlib.sha256(profile_bytes).hexdigest()}`',
        'Hosting : ' + ('internal server' if server else 'local computer'), '',
        'Memory suggests choices; only applied and confirmed choices are used.']
    if memory:
        lines += ['Memory consulted : ' + cell(memory['name']), 'Version consulted : `' + memory.get('expected','unavailable') + '`']
    lines += ['', '## Settings', '', '```json', json.dumps(profile.get('settings',{}),ensure_ascii=False,indent=2), '```', '',
        '## Questions', '', '| Question | Keep | Type | Clean label | Metrics |', '|---|---|---|---|---|']
    questions = profile.get('questions', [])
    if isinstance(questions, dict):
        questions = [dict(value, **{'Question ID':key}) for key,value in questions.items()]
    for row in questions:
        if not isinstance(row,dict):
            continue
        lines.append('| ' + ' | '.join(cell(TEXT.get(row.get(k,''),row.get(k,'')) if k=='Type' else row.get(k,'')) for k in ('Question ID','Keep','Type','Display label','Selected metrics')) + ' |')
    return ('\n'.join(lines)+'\n').encode('utf-8')
