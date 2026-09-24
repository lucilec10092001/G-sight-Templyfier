"""Explainable grouping suggestions, independent of Streamlit and source values.

A shared prefix works for any subject, not just a fixed list of CMI attributes.
Question family, section, stage, type and metric structure constrain suggestions.
Nothing here changes metric selections or source question identifiers.
"""
from collections import defaultdict
from copy import deepcopy
import hashlib
import re
import unicodedata

from .smart import _metric_key


def _normal(value):
    value = unicodedata.normalize('NFKD', str(value))
    return ' '.join(''.join(c for c in value if not unicodedata.combining(c)).casefold().split())


def _body(qid):
    return re.sub(r'^Q\s*[-_]?\s*\d+[A-Z]?(?:\s*[-_]\s*\d+[A-Z]?)*\s*[-_:=]?\s*',
                  '', str(qid), flags=re.I).strip()


def question_family(qid):
    # Require a numeric sub-question: adjacent unrelated Q1 and Q2 are not a battery.
    match = re.match(r'^Q\s*[-_]?\s*(\d+[A-Z]?)\s*[-_]\s*\d+[A-Z]?(?:[-_\s]|$)', str(qid), re.I)
    return 'Q-' + match.group(1).upper().lstrip('0') if match else ''


def stages_for(row, stage_names=()):
    """Return stages explicitly present in a question, including CMI-defined ones."""
    def stage_text(value):
        return re.sub(r'[\W_]+', ' ', _normal(value)).strip()

    explicit = str(row.get('Stage', '')).strip()
    if explicit and stage_text(explicit) not in {'unassigned', 'not specified', 'non precise', 'none'}:
        return tuple(dict.fromkeys(
            value.strip() for value in re.split(r'[;|\n]+', explicit) if value.strip()
        ))

    values = stage_text(' '.join(str(row.get(field, '')) for field in
                                 ('Question ID', 'Display label', 'Metric label', 'Section')))
    candidates = list(dict.fromkeys(['NEAT', 'WET', 'DRY', 'DAMP', *stage_names]))
    # Prefer long labels first so "Skin dry-down" is not reduced to "DRY".
    ordered = sorted(candidates, key=lambda value: (-len(stage_text(value)), stage_text(value)))
    matched = []
    for stage in ordered:
        normalized = stage_text(stage)
        if normalized and re.search(rf'(?<!\w){re.escape(normalized)}(?!\w)', values):
            if not any(normalized in stage_text(existing) for existing in matched):
                matched.append(str(stage).strip())
    return tuple(matched)


def stage_for(row, stage_names=()):
    """Stable legacy grouping key for the stages matched by :func:`stages_for`."""
    return '/'.join(stages_for(row, stage_names))


def metric_structure(row):
    codes, other = set(), set()
    for metric in row.get('Available metric list', []):
        match = re.match(r'^\s*(\d+)\s*[-_.: ]', metric)
        if match:
            codes.add(int(match.group(1)))
        else:
            other.add(_metric_key(metric))
    # Extra aggregate rows (for example Mean on some CATA items) do not change
    # the response scale. Their individual selections are never overwritten.
    return (tuple(sorted(codes)), ()) if codes else ((), tuple(sorted(other)))


def _prefixes(text):
    """Candidate prefixes terminate at separators or word boundaries."""
    found = {}
    for match in re.finditer(r'\s*[-_:|\u2013\u2014]\s*', text):
        prefix, item = text[:match.start()].strip(), text[match.end():].strip()
        if 3 <= len(prefix) <= 65 and item and not re.fullmatch(r'q[-_ ]?[a-z]?\d*', prefix, re.I):
            found[_normal(prefix)] = (prefix, item)
            break  # Prefer the named battery boundary, keeping the item intact.
    if found:
        return found
    words = list(re.finditer(r'\S+', text))
    for count in range(1, min(6, len(words))):
        end = words[count-1].end()
        prefix, item = text[:end].strip(' -_:'), text[end:].strip(' -_:')
        if len(prefix) >= 4 and item and _normal(prefix) not in {'this','that','these','overall product','the','les','des','cette','ce','mon','mes'}:
            found.setdefault(_normal(prefix), (prefix, item))
    return found


def _theme_label(members, family):
    # Vocabulary only helps name a structural proposal; it never joins unrelated IDs.
    emotion = {'happy','cared for','energised','energized','surprised','uplifted','comforted',
               'relaxed','nostalgic','reassured','irritated','disappointed','neutral',
               'heureux','rassure','detendu','surpris','reconforte'}
    matches = sum(_normal(_body(r['Question ID'])) in emotion for r in members)
    if matches >= 3 and matches / len(members) >= .6:
        return 'Emotions', 'Thème suggéré à confirmer'
    return f'Battery {family}', 'Nom à préciser'


def suggest_groups(rows, include_dismissed=False, stage_names=()):
    """Return non-overlapping, unapplied proposals; a saved CMI choice always wins."""
    buckets = defaultdict(list)
    for row in rows:
        if row.get('Group ID') or not row.get('Keep', True):
            continue
        if row.get('Grouping choice') == 'separate' and not include_dismissed:
            continue
        context = (str(row.get('Section','')), row['Type'], stage_for(row, stage_names),
                   metric_structure(row), question_family(row['Question ID']))
        buckets[context].append(row)
    suggestions = []

    def add(members, label, items, reason, confidence, context, identity_label=None):
        member_ids = [r['Question ID'] for r in members]
        sid = hashlib.sha1(('\0'.join(sorted(member_ids))+'\0'+_normal(identity_label or label)).encode()).hexdigest()[:16]
        if not include_dismissed and any(sid in r.get('Dismissed groups', []) for r in members):
            return
        suggestions.append({'id':sid, 'label':label, 'members':member_ids, 'items':items,
                            'reason':reason, 'confidence':confidence, 'section':context[0],
                            'type':context[1], 'stage':context[2], 'family':context[4]})

    for context, members in buckets.items():
        prefix_buckets = defaultdict(dict)
        for row in members:
            # Source keeps battery prefixes that the legacy humanizer removed.
            for value in (str(row['Display label']), _body(row['Question ID'])):
                for normalized, (prefix, item) in _prefixes(value).items():
                    prefix_buckets[normalized].setdefault(row['Question ID'], (prefix, item))
        claimed = set()
        for prefix, matches in sorted(prefix_buckets.items(), key=lambda pair:(-len(pair[1]), -len(pair[0]))):
            subset = [r for r in members if r['Question ID'] in matches and r['Question ID'] not in claimed]
            if len(subset) < 2:
                continue
            if context[4] and len(subset) < .6 * len(members):
                continue  # Do not fragment a battery for a coincidental phrase.
            # Without an explicit numeric family, require an actual separator.
            if not context[4] and not all(re.match(re.escape(matches[r['Question ID']][0])+r'\s*[-_:|\u2013\u2014]', _body(r['Question ID']), re.I) for r in subset):
                continue
            label = matches[subset[0]['Question ID']][0]
            items = {}
            for row in subset:
                qid = row['Question ID']
                current = str(row['Display label'])
                # Never erase a label already customized by the CMI.
                item = re.sub(r'^'+re.escape(label)+r'(?:\s*[-_:|\u2013\u2014]\s*|\s+)', '', current, count=1, flags=re.I)
                items[qid] = item or current
            why = f'Préfixe partagé « {label} » ; même type et structure de métriques.'
            if context[4]:
                why += f' Sous-questions de {context[4]}.'
            add(subset, label, items, why, 'Libellé commun', context)
            claimed.update(r['Question ID'] for r in subset)
        remaining = [r for r in members if r['Question ID'] not in claimed]
        if context[4] and len(remaining) >= 3:
            label, confidence = _theme_label(remaining, context[4])
            add(remaining, label, {r['Question ID']:r['Display label'] for r in remaining},
                f'Sous-questions de {context[4]} ; même type et structure de métriques. Le nom du groupe reste à valider.',
                confidence, context, identity_label=f'Batterie {context[4]}' if label==f'Battery {context[4]}' else None)
    positions = {r['Question ID']:i for i,r in enumerate(rows)}
    return sorted(suggestions, key=lambda g:min(positions[q] for q in g['members']))


def create_group(rows, member_ids, label, items=None, group_id=None, stage_names=()):
    if not str(label).strip():
        raise ValueError('Le nom du groupe ne peut pas être vide.')
    selected = set(member_ids)
    if len(selected) < 2 or len(selected) != len(member_ids):
        raise ValueError('Choisis au moins deux questions distinctes.')
    members = [r for r in rows if r['Question ID'] in selected]
    if len(members) != len(selected) or any(r.get('Group ID') for r in members):
        raise ValueError('Une question est absente ou appartient déjà à un groupe. Sépare le groupe avant de la déplacer.')
    if len({str(r['Section']) for r in members}) > 1:
        raise ValueError('Place les questions dans la même section avant de les regrouper.')
    if len({stage_for(r, stage_names) for r in members}) > 1:
        raise ValueError('Ces questions concernent des stages différents ; crée un groupe par stage.')
    gid = group_id or hashlib.sha1(('manual\0'+'\0'.join(sorted(selected))).encode()).hexdigest()[:16]
    labels = {r['Question ID']:str((items or {}).get(r['Question ID'], r.get('Metric label') or r['Display label'])).strip() for r in members}
    if not all(labels.values()):
        raise ValueError('Le libellé d’un item ne peut pas être vide.')
    for row in members:
        qid = row['Question ID']
        row['Metric label'] = labels[qid]
        row['Display label'] = str(label).strip()
        row['Group ID'] = gid
        row['Grouping choice'] = 'accepted'
    # Put the accepted group together at its first member, retaining internal order.
    # The preview explicitly tells the CMI this effect before applying.
    first = next(i for i,r in enumerate(rows) if r['Question ID'] in selected)
    before = [r for r in rows[:first] if r['Question ID'] not in selected]
    after = [r for r in rows[first:] if r['Question ID'] not in selected]
    rows[:] = before + members + after
    for order, row in enumerate(rows, 1):
        row['Order'] = order


def accept_suggestion(rows, suggestion, label=None, items=None):
    create_group(rows, suggestion['members'], label if label is not None else suggestion['label'],
                 suggestion['items'] if items is None else items, suggestion['id'])


def dismiss_suggestion(rows, suggestion):
    for row in rows:
        if row['Question ID'] in suggestion['members']:
            row['Dismissed groups'] = sorted(set(row.get('Dismissed groups', []) + [suggestion['id']]))


def separate_group(rows, group_id):
    for row in rows:
        if row.get('Group ID') != group_id:
            continue
        # Keep the latest edited item; do not revert a CMI rename on separation.
        row['Display label'] = ' · '.join(str(row.get(f,'')).strip() for f in ('Display label','Metric label') if row.get(f))
        row['Metric label'] = ''
        row['Group ID'] = ''
        row['Grouping choice'] = 'separate'
        row.pop('Ungrouped labels', None)


def reset_suggestions(rows):
    for row in rows:
        row['Dismissed groups'] = []
        if row.get('Grouping choice') == 'separate':
            row['Grouping choice'] = ''


def remember_edit(model, changed, action):
    if changed == model['rows']:
        return False
    history = model.setdefault('history', [])
    history.append({'rows':deepcopy(model['rows']), 'action':action})
    del history[:-20]
    model['redo'] = []
    model['rows'] = changed
    model['revision'] += 1
    model['notice'] = action
    return True


def undo_edit(model):
    if not model.get('history'):
        return False
    previous = model['history'].pop()
    model.setdefault('redo', []).append({'rows':deepcopy(model['rows']), 'action':previous['action']})
    model['rows'] = previous['rows']
    model['revision'] += 1
    model['notice'] = 'Annulé : ' + previous['action']
    return True


def redo_edit(model):
    if not model.get('redo'):
        return False
    following = model['redo'].pop()
    model.setdefault('history', []).append({'rows':deepcopy(model['rows']), 'action':following['action']})
    del model['history'][:-20]
    model['rows'] = following['rows']
    model['revision'] += 1
    model['notice'] = 'Rétabli : ' + following['action']
    return True
