"""Local, explicitly taught CMI habits. No survey values or external AI calls.

Question numbers never form a matching key. Matching uses source wording,
stage, type and response semantics; an incomplete recipe is never applied.
"""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from threading import RLock
from uuid import uuid4

from .editor_model import QUESTION_TYPES, group_rows, set_metric_selection
from .grouping import (_body, _normal, accept_suggestion,
                       separate_group, stage_for, suggest_groups)
from .preferences import preferences_path
from . import server_storage as storage
from .review import _cata_yes_no, safe_metric_match
from .smart import STANDARD_METRICS, _metric_key

SCOPES = ('Question équivalente', 'Type et échelle compatibles')
_LOCK = RLock()
_AGGREGATES = {_metric_key(m) for m in STANDARD_METRICS}


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:20]


def memory_path():
    return preferences_path().with_name('client_memory.json')


def validate_memories(payload):
    if not isinstance(payload, dict) or payload.get('version') != 1 or not isinstance(payload.get('clients'), dict):
        raise ValueError('Format de mémoire client non reconnu.')
    result = {'version': 1, 'clients': {}}
    for cid, client in payload['clients'].items():
        if not isinstance(client, dict) or not isinstance(client.get('name'), str) or not client['name'].strip() or cid != _normal(client['name']):
            raise ValueError('Nom de client incorrect dans la mémoire.')
        rules = client.get('rules')
        if not isinstance(rules, list) or len(rules) > 2000:
            raise ValueError('Liste des habitudes incorrecte ou trop longue.')
        clean = []
        seen = set()
        for rule in rules:
            if not isinstance(rule, dict) or rule.get('kind') not in {'question', 'metrics', 'group'}:
                raise ValueError('Habitude non reconnue.')
            anchor, value = rule.get('anchor'), rule.get('value')
            if not isinstance(anchor, dict) or not isinstance(value, dict):
                raise ValueError('Habitude incomplète.')
            if set(anchor) != {'type', 'stage', 'section', 'shape', 'wording', 'theme', 'items'} or anchor['type'] not in QUESTION_TYPES:
                raise ValueError('Contexte de question incorrect.')
            if not all(isinstance(anchor[k], str) for k in ('stage', 'section', 'wording', 'theme')) or not all(
                    isinstance(anchor[k], list) and all(isinstance(v, str) for v in anchor[k]) for k in ('shape', 'items')):
                raise ValueError('Structure du contexte incorrecte.')
            if rule.get('scope') not in SCOPES or rule.get('id') != _rule_id(rule) or rule['id'] in seen:
                raise ValueError('Identifiant ou portée de mémoire incorrect.')
            if rule['kind'] == 'question':
                if rule['scope'] != SCOPES[0] or not value or not set(value).issubset({'Type', 'label', 'Keep'}):
                    raise ValueError('Choix de question incorrect.')
                if ('Type' in value and value['Type'] not in QUESTION_TYPES) or ('Keep' in value and not isinstance(value['Keep'], bool)) or (
                        'label' in value and (not isinstance(value['label'], str) or not value['label'].strip())):
                    raise ValueError('Valeur de question incorrecte.')
            elif rule['kind'] == 'metrics':
                if set(value) != {'selected', 'labels', 'available', 'type'} or value['type'] not in QUESTION_TYPES or not value['selected']:
                    raise ValueError('Recette de métriques incorrecte.')
                if not all(isinstance(value[k], list) and all(isinstance(m, str) for m in value[k]) for k in ('selected', 'available')) or not set(value['selected']).issubset(value['available']):
                    raise ValueError('Métrique source inconnue.')
                if not isinstance(value['labels'], dict) or not all(k in value['available'] and isinstance(v, str) and v.strip() for k, v in value['labels'].items()):
                    raise ValueError('Renommage de métrique incorrect.')
                if rule['scope'] == SCOPES[1] and (anchor['type'] != value['type'] or not _can_widen(value)):
                    raise ValueError('Cette recette ne peut pas être généralisée à un type.')
            else:
                if rule['scope'] != SCOPES[0] or set(value) != {'decision', 'label'} or value['decision'] not in {'rename', 'group', 'ignore'} or not isinstance(value['label'], str) or not value['label'].strip():
                    raise ValueError('Décision de regroupement incorrecte.')
            evidence = rule.get('evidence', [])
            if not isinstance(evidence, list) or len(evidence) > 20 or not all(isinstance(e, str) and re.fullmatch(r'[a-f0-9]{20}', e) for e in evidence):
                raise ValueError('Historique de mémoire incorrect.')
            if not isinstance(rule.get('updated'), str) or not isinstance(rule.get('description'), str):
                raise ValueError('Description de mémoire incorrecte.')
            seen.add(rule['id'])
            clean.append({k: deepcopy(rule[k]) for k in ('id', 'kind', 'scope', 'anchor', 'value', 'description', 'updated', 'evidence')})
        result['clients'][cid] = {'name': client['name'].strip(), 'rules': clean}
    return result


def load_memories(path=None):
    if storage.server_mode():
        if path is not None:
            raise ValueError('Un chemin de mémoire personnalisé est interdit en mode serveur.')
        return validate_memories(storage.read_document('memory', {'version':1, 'clients':{}}))
    target = Path(path) if path is not None else memory_path()
    try:
        return validate_memories(json.loads(target.read_text(encoding='utf-8')))
    except FileNotFoundError:
        return {'version': 1, 'clients': {}}
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise ValueError(f"Mémoire client illisible ; elle n'a pas été modifiée : {exc}") from exc


def _write(payload, path=None):
    if storage.server_mode():
        raise ValueError('La mémoire serveur doit être modifiée dans une transaction.')
    target = Path(path) if path is not None else memory_path()
    payload = validate_memories(payload)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.parent/f'memory_{uuid4().hex}.tmp'
    created = False
    try:
        with temporary.open('x', encoding='utf-8') as handle:
            created = True
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        os.replace(temporary, target)
    finally:
        if created and temporary.exists():
            temporary.unlink()


def client_token(client):
    return _digest(client)


def _mutate(change, path=None, action='memory:update'):
    if storage.server_mode():
        if path is not None:
            raise ValueError('Un chemin personnalisé est interdit en mode serveur.')
        def update(payload):
            payload = validate_memories(payload)
            result = change(payload)
            return validate_memories(payload), result
        return storage.mutate_document('memory', {'version':1,'clients':{}}, action, update)
    with _LOCK:
        payload = load_memories(path)
        result = change(payload)
        _write(payload, path)
        return result


def _check_client_version(client, expected):
    if storage.server_mode() and expected is None:
        raise ValueError('Recharge la mémoire avant de la modifier : version de lecture requise.')
    if expected is not None and client_token(client) != expected:
        raise ValueError('Cette mémoire a changé depuis ta lecture. Aucun choix écrasé : recharge et vérifie les nouvelles habitudes.')


def import_client_memory(imported, client_id, expected, path=None):
    """Explicit, reviewed merge of one portable client; never import survey data."""
    imported = validate_memories(imported)
    if client_id not in imported['clients']:
        raise ValueError('Client absent de la mémoire importée.')
    def change(payload):
        prior = payload['clients'].get(client_id)
        if prior is not None:
            _check_client_version(prior, expected)
        elif expected != 'absent':
            raise ValueError('La mémoire cible a changé ; recharge avant l’import.')
        rules = {r['id']:r for r in prior['rules']} if prior else {}
        rules.update({r['id']:r for r in imported['clients'][client_id]['rules']})
        payload['clients'][client_id] = {'name':prior['name'] if prior else imported['clients'][client_id]['name'], 'rules':list(rules.values())}
        return len(imported['clients'][client_id]['rules'])
    return _mutate(change, path, 'memory:import-client')


def ensure_client(name, path=None):
    clean = ' '.join(str(name).split())
    if not clean or len(clean) > 100 or _normal(clean) in {_normal('Sans mémoire client'), _normal('Nouveau client…')}:
        raise ValueError('Donne un nom de client distinct de 1 à 100 caractères.')
    def change(payload):
        cid = _normal(clean)
        payload['clients'].setdefault(cid, {'name': clean, 'rules': []})
        return cid
    return _mutate(change, path, 'memory:create-client')


def _shape(row):
    if _cata_yes_no(row):
        return ['cata:no/yes']
    responses = sorted({_normal(_metric_key(m)) for m in row.get('Available metric list', []) if _metric_key(m) not in _AGGREGATES})
    return responses or ['échelle non détaillée']


def _anchor(row):
    return {'type': row['Type'], 'stage': stage_for(row), 'shape': _shape(row),
            'section':'', 'wording': _normal(re.sub(r'[^\w\s]', ' ', _body(row['Question ID']))), 'theme': '', 'items': []}


def _group_anchor(baseline, ids, theme):
    by_id = {r['Question ID']: r for r in baseline}
    members = [by_id[q] for q in ids]
    if not members or len({r['Type'] for r in members}) != 1 or len({stage_for(r) for r in members}) != 1 or len({_normal(r.get('Section','')) for r in members}) != 1:
        return None
    anchor = _anchor(members[0])
    anchor['section'] = _normal(members[0].get('Section',''))
    # A group can retain different response scales per item. Only the inventory
    # of scales is matched; grouping never copies one item's metric recipe.
    anchor['shape'] = sorted({_digest(_shape(r)) for r in members})
    anchor['wording'] = ''
    anchor['theme'] = '' if re.match(r'^Batterie Q[-_ ]', str(theme), re.I) else _normal(theme)
    anchor['items'] = sorted({_anchor(r)['wording'] for r in members})
    return anchor


def _rule_id(rule):
    return _digest([rule['kind'], rule['scope'], rule['anchor']])


def _can_widen(value):
    row = {'Type': value['type'], 'Available metric list': value['available']}
    if _cata_yes_no(row):
        return True
    if value['type'] not in {'Standard', 'Strength'} or _shape(row) == ['échelle non détaillée']:
        return False
    return value['type'] == 'Strength' or all(_metric_key(m) in _AGGREGATES for m in value['selected'])


def teaching_candidates(baseline, rows):
    """Only differences from fresh G-Sight proposals are eligible for teaching."""
    original = {r['Question ID']: r for r in baseline}
    structural = suggest_groups(baseline, include_dismissed=True)
    current_groups = group_rows(rows)
    result = []

    def add(kind, anchor, value, description, source, broad=False):
        if anchor is None:
            return
        if kind == 'group' and value['decision'] == 'rename' and anchor['theme']:
            # A vocabulary habit is independent of this battery's item inventory.
            anchor['items'] = []
            anchor['section'] = ''
        result.append({'kind': kind, 'anchor': anchor, 'value': value, 'description': description,
                       'scope': SCOPES[0], 'source': source, 'can_widen': broad,
                       'candidate_id': _digest([kind, source, anchor, value])})

    for row in rows:
        base = original[row['Question ID']]
        anchor = _anchor(base)
        coded = not anchor['wording'] or bool(re.fullmatch(r'[a-z]\d{1,2}', anchor['wording']))
        values = {}
        if row['Type'] != base['Type']:
            values['Type'] = row['Type']
        if bool(row.get('Keep')) != bool(base.get('Keep')):
            values['Keep'] = bool(row.get('Keep'))
        label = row.get('Metric label') if row.get('Group ID') else row['Display label']
        old_label = base.get('Metric label') if base.get('Group ID') else base['Display label']
        # Group creation strips a prefix mechanically; this is not an item rename.
        if row.get('Group ID') and not base.get('Group ID'):
            group = next(g for g in current_groups if g['id'] == row['Group ID'])
            proposal = next((g for g in structural if set(g['members']) == set(group['members'])), None)
            old_label = proposal['items'][row['Question ID']] if proposal else old_label
        if label != old_label and row.get('Grouping choice') != 'separate':
            values['label'] = label
        if values and not coded:
            add('question', anchor, values, f"Question « {_body(row['Question ID'])} » : "+'; '.join(f'{k} → {v}' for k,v in values.items()), row['Question ID'])
        labels = {k:v for k,v in row.get('Metric labels', {}).items() if v != k}
        old_labels = {k:v for k,v in base.get('Metric labels', {}).items() if v != k}
        if row.get('Keep') and row['Selected metrics'] and not coded and (row['Selected metrics'] != base['Selected metrics'] or labels != old_labels):
            value = {'selected': list(row['Selected metrics']), 'labels': labels,
                     'available': list(row['Available metric list']), 'type': row['Type']}
            add('metrics', anchor, value, f"{_body(row['Question ID'])} : "+' + '.join(value['selected'])+
                (' ; libellés : '+json.dumps(labels,ensure_ascii=False) if labels else ''), row['Question ID'], base['Type'] == row['Type'] and _can_widen(value))

    initial_groups = {g['id']:g for g in group_rows(baseline)}
    by_current = {r['Question ID']:r for r in rows}
    for group in group_rows(rows):
        base_group = initial_groups.get(group['id'])
        proposal = next((g for g in structural if set(g['members']) == set(group['members'])), None)
        if base_group and base_group['label'] == group['label']:
            continue
        theme = base_group['label'] if base_group else proposal['label'] if proposal else ''
        add('group', _group_anchor(baseline, group['members'], theme), {'decision':'rename' if base_group else 'group', 'label':group['label']},
            f"Regrouper / nommer « {theme or 'ces items'} » → « {group['label']} »", group['id'])
    for proposal in structural + list(initial_groups.values()):
        was_ignored = any(proposal['id'] in original[q].get('Dismissed groups', []) for q in proposal['members'])
        ignored = any(proposal['id'] in by_current[q].get('Dismissed groups', []) for q in proposal['members']) or all(
            by_current[q].get('Grouping choice') == 'separate' for q in proposal['members'])
        if ignored and not was_ignored:
            add('group', _group_anchor(baseline, proposal['members'], proposal['label']), {'decision':'ignore', 'label':proposal['label']},
                f"Ne plus proposer le regroupement « {proposal['label']} »", proposal['id'])
    return result


def teach(client_id, candidates, project_key, path=None, expected=None):
    if not candidates:
        raise ValueError('Sélectionne au moins un choix à retenir.')
    taught = {}
    for candidate in candidates:
        rule = {k:deepcopy(candidate[k]) for k in ('kind', 'anchor', 'value', 'description', 'scope')}
        if rule['scope'] == SCOPES[1]:
            if rule['kind'] != 'metrics' or not candidate.get('can_widen'):
                raise ValueError('Seule une recette compatible peut être élargie à un type et une échelle.')
            rule['anchor']['wording'] = ''
            # A type recipe does not rename individual answer labels globally.
            rule['value']['labels'] = {}
        rule['id'] = _rule_id(rule)
        rule['updated'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
        rule['evidence'] = [_digest(project_key)]
        if rule['id'] in taught and _effect(taught[rule['id']]) != _effect(rule):
            raise ValueError('Deux choix différents visent le même type et la même échelle. Retiens une seule recette, ou garde la portée Question équivalente.')
        taught[rule['id']] = rule
    def change(payload):
        if client_id not in payload['clients']:
            raise ValueError('Client introuvable ; sélectionne ou crée le client.')
        _check_client_version(payload['clients'][client_id], expected)
        prior = {r['id']:r for r in payload['clients'][client_id]['rules']}
        for rid, rule in taught.items():
            if rid in prior and _effect(prior[rid]) == _effect(rule):
                rule['evidence'] = list(dict.fromkeys(prior[rid]['evidence'] + rule['evidence']))[-20:]
            prior[rid] = rule
        payload['clients'][client_id]['rules'] = list(prior.values())
    _mutate(change, path, 'memory:teach')
    return len(taught)


def _effect(rule):
    value = rule['value']
    if rule['kind'] != 'metrics':
        return value
    keys = sorted(_metric_key(m) for m in value['selected'])
    if rule['scope'] == SCOPES[1] and _cata_yes_no({'Type':value['type'], 'Available metric list':value['available']}):
        keys = sorted(re.match(r'^\s*(\d+)\s*[-_.: ]', m).group(1) if re.match(r'^\s*(\d+)\s*[-_.: ]', m) else _metric_key(m) for m in value['selected'])
    return [value['type'], keys, value['labels']]


def delete_rules(client_id, rule_ids=None, path=None, expected=None):
    def change(payload):
        if client_id not in payload['clients']:
            raise ValueError('Client introuvable.')
        _check_client_version(payload['clients'][client_id], expected)
        if rule_ids is None:
            del payload['clients'][client_id]
        else:
            known = {r['id'] for r in payload['clients'][client_id]['rules']}
            if not set(rule_ids).issubset(known):
                raise ValueError('Habitude introuvable ; recharge la mémoire.')
            payload['clients'][client_id]['rules'] = [r for r in payload['clients'][client_id]['rules'] if r['id'] not in rule_ids]
    return _mutate(change, path, 'memory:delete')


def _same_context(anchor, other):
    return all(anchor[k] == other[k] for k in ('type', 'stage', 'shape'))


def _same_group(anchor, other):
    if not _same_context(anchor, other) or anchor['theme'] != other['theme'] or anchor['section'] != other['section']:
        return False
    left, right = set(anchor['items']), set(other['items'])
    return left == right if not anchor['theme'] else bool(left | right) and len(left & right) >= 2 and len(left & right) / len(left | right) >= .75


def memory_suggestions(baseline, rows, rules, protected_ids=()):
    """Return explained proposals, safe omissions and display-only remembered refusals."""
    by_base = {r['Question ID']:r for r in baseline}
    source_anchors = {qid:_anchor(r) for qid,r in by_base.items()}
    structural = suggest_groups(baseline, include_dismissed=True)
    groups = []
    for group in group_rows(rows):
        original_group = next((g for g in group_rows(baseline) if set(g['members']) == set(group['members'])), None)
        proposal = next((g for g in structural if set(g['members']) == set(group['members'])), None)
        theme = original_group['label'] if original_group else proposal['label'] if proposal else ''
        groups.append({'group':group, 'anchor':_group_anchor(baseline, group['members'], theme), 'existing':True})
    for group in suggest_groups(rows):
        groups.append({'group':group, 'anchor':_group_anchor(baseline, group['members'], group['label']), 'existing':False})
    proposals, omissions, ignored = [], [], set()
    precise_metrics = set()
    protected = set(protected_ids)
    for rule in rules:
        anchor = rule['anchor']
        why = f"Choix enseigné le {rule['updated'][:10]} ; {len(rule['evidence'])} projet(s) mémorisé(s). "
        if rule['kind'] == 'group':
            for target in groups:
                group = target['group']
                same_theme = (target['anchor'] is not None and bool(anchor['theme']) and _same_context(anchor,target['anchor']) and anchor['theme'] == target['anchor']['theme'])
                if target['anchor'] is None or not (same_theme if rule['value']['decision'] == 'rename' and anchor['theme'] else _same_group(anchor, target['anchor'])):
                    continue
                if any(q in protected for q in group['members']):
                    continue
                if rule['value']['decision'] == 'ignore':
                    if not target['existing']:
                        ignored.add(group['id'])
                        continue
                if target['existing'] and group['label'] == rule['value']['label'] and rule['value']['decision'] != 'ignore':
                    continue
                proposals.append({'id':_digest([rule['id'], group['members']]), 'rule':rule, 'kind':'group',
                    'members':group['members'], 'group':group, 'existing':target['existing'],
                    'before':group['label'], 'after':'Séparer les items' if rule['value']['decision'] == 'ignore' else rule['value']['label'],
                    'why':why+('Même thème source, stage et structure de réponses.' if rule['value']['decision'] == 'rename' else 'Même thème, stage et structure ; au moins 75 % des items communs.')})
            continue
        matches = [r for r in rows if _same_context(anchor, source_anchors[r['Question ID']]) and (
            not anchor['wording'] or anchor['wording'] == source_anchors[r['Question ID']]['wording'])]
        if rule['kind'] == 'metrics' and anchor['wording']:
            precise_metrics.update(r['Question ID'] for r in matches)
        if anchor['wording'] and len(matches) > 1:
            omissions.append({'Habitude':rule['description'], 'Motif':'Plusieurs questions équivalentes : choix manuel nécessaire.'})
            continue
        for row in matches:
            qid = row['Question ID']
            if qid in protected or (rule['kind'] == 'metrics' and not row.get('Keep')):
                continue
            if rule['scope'] == SCOPES[1] and row['Type'] != anchor['type']:
                continue
            if rule['kind'] == 'question':
                before = {k:(row.get('Metric label') if row.get('Group ID') else row['Display label']) if k == 'label' else row.get(k) for k in rule['value']}
                after = rule['value']
                if before == after:
                    continue
                action = {'values':deepcopy(after)}
            else:
                source = {'Type':rule['value']['type'], 'Available metric list':rule['value']['available']}
                matched, missing = safe_metric_match(source, row, rule['value']['selected'])
                if missing:
                    omissions.append({'Habitude':rule['description'], 'Motif':f"{qid} : recette conservée, métriques manquantes ou ambiguës : "+', '.join(missing)})
                    continue
                labels = {}
                for old, label in rule['value']['labels'].items():
                    # Renaming is safe only for full metric identity, not a CATA code.
                    found = [m for m in row['Available metric list'] if _metric_key(m) == _metric_key(old)]
                    if len(found) == 1:
                        labels[found[0]] = label
                merged_labels = {**row.get('Metric labels', {}), **labels}
                if matched == row['Selected metrics'] and merged_labels == row.get('Metric labels', {}):
                    continue
                def recipe_text(metrics, names):
                    return ' + '.join(m+(f" → {names[m]}" if names.get(m,m) != m else '') for m in metrics)
                before, after = recipe_text(row['Selected metrics'], row.get('Metric labels',{})), recipe_text(matched, merged_labels)
                action = {'selected':matched, 'labels':merged_labels}
            proposals.append({'id':_digest([rule['id'], qid]), 'rule':rule, 'kind':rule['kind'], 'members':[qid],
                'before':before, 'after':after, 'renamings':labels if rule['kind'] == 'metrics' else {},
                'why':why+('Même wording source, stage et échelle.' if anchor['wording'] else 'Même type, stage et réponses de l’échelle.'), **action})
    # A precise question recipe takes precedence over a broad type recipe.
    proposals = [p for p in proposals if p['kind'] != 'metrics' or p['rule']['anchor']['wording'] or p['members'][0] not in precise_metrics]
    # Concordant habits from overlapping batteries are evidence, not a conflict.
    concordant = {}
    for proposal in proposals:
        effect = proposal.get('values') if proposal['kind'] == 'question' else (
            [sorted(proposal['selected']), proposal['labels']] if proposal['kind'] == 'metrics' else
            ['separate' if proposal['rule']['value']['decision'] == 'ignore' else 'group', proposal['after']])
        identity = (proposal['kind'], tuple(proposal['members']), _digest(effect))
        if identity not in concordant:
            concordant[identity] = proposal
        elif proposal['rule']['updated'] > concordant[identity]['rule']['updated']:
            concordant[identity] = proposal
    proposals = list(concordant.values())
    counts = Counter((p['kind'], tuple(p['members'])) for p in proposals)
    ambiguous = [p for p in proposals if counts[(p['kind'], tuple(p['members']))] > 1]
    for proposal in ambiguous:
        omissions.append({'Habitude':proposal['rule']['description'], 'Motif':'Plusieurs habitudes correspondent : choix manuel nécessaire.'})
    proposals = [p for p in proposals if counts[(p['kind'], tuple(p['members']))] == 1]
    return proposals, omissions, ignored


def apply_suggestions(rows, proposals, selected_ids):
    if not selected_ids or not set(selected_ids).issubset({p['id'] for p in proposals}):
        raise ValueError('Sélectionne des suggestions présentes dans cet aperçu.')
    changed = deepcopy(rows)
    by_id = {r['Question ID']:r for r in changed}
    originals = {r['Question ID']:r for r in rows}
    for proposal in sorted((p for p in proposals if p['id'] in selected_ids), key=lambda p: {'question':0, 'metrics':1, 'group':2}[p['kind']]):
        if proposal['kind'] == 'group':
            if proposal['rule']['value']['decision'] == 'ignore':
                separate_group(changed, proposal['group']['id'])
            elif proposal['existing']:
                for qid in proposal['members']:
                    by_id[qid]['Display label'] = proposal['after']
            else:
                items = {q:by_id[q]['Display label'] if by_id[q]['Display label'] != originals[q]['Display label'] else proposal['group']['items'][q] for q in proposal['members']}
                accept_suggestion(changed, proposal['group'], proposal['after'], items)
        elif proposal['kind'] == 'metrics':
            set_metric_selection(by_id[proposal['members'][0]], proposal['selected'], proposal['labels'])
        else:
            row = by_id[proposal['members'][0]]
            for field, value in proposal['values'].items():
                if field == 'Type':
                    # Keep the current recipe: a type suggestion cannot silently erase it.
                    row['Type'] = value
                    row['Selection type'] = value
                else:
                    target_field = ('Metric label' if row.get('Group ID') else 'Display label') if field == 'label' else field
                    row[target_field] = value
    return changed
