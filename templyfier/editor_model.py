"""Pure editor operations. Question IDs remain stable across all UI changes."""
from copy import deepcopy
import hashlib
import re

from .smart import STANDARD_METRICS, _metric_key, default_metric_selection

QUESTION_TYPES = ('Standard', 'Strength', 'CATA', 'Listing', 'Bipolaire', 'Preference', 'Autres')


def prepare_rows(rows, proposals, stage_names=()):
    by_id = {p.question_id: p for p in proposals}
    result = deepcopy(rows)
    for row in result:
        # DataFrame conversion inserts NaN for new questions not in a saved profile.
        if not isinstance(row.get('Group ID'), str):
            row.pop('Group ID', None)
        if not isinstance(row.get('Dismissed groups'), list):
            row['Dismissed groups'] = []
        if not isinstance(row.get('Grouping choice'), str):
            row['Grouping choice'] = ''
    # Some exports omit 'Color' entirely: Q-6-1-A1, Q-6-2-A2, etc.
    # Suggest a group only for a whole coded battery, never an isolated A1 label.
    coded_families = {}
    for row in result:
        if re.fullmatch(r'[A-Z]\d{1,2}', str(row.get('Display label',''))):
            family = re.match(r'^(Q[-_ ]*\d+[A-Za-z]?)[-_ ]', row['Question ID'], re.I)
            if family:
                family_key = (row['Section'], family.group(1).casefold())
                coded_families.setdefault(family_key, []).append(row)
    for (section, family), members in coded_families.items():
        if len({r['Display label'] for r in members}) >= 3:
            gid = hashlib.sha1((str(section)+'\0Color\0'+family).encode()).hexdigest()[:12]
            for row in members:
                if 'Group ID' not in row and row.get('Grouping choice') != 'separate':
                    row['Metric label'] = row['Display label']
                    row['Display label'] = 'Color'
                    row['Group ID'] = gid
    for row in result:
        available = list(by_id[row['Question ID']].metrics)
        old_type = row['Type']
        row['Type'] = {'Attribute': 'CATA', 'Libre': 'Autres', 'Delete': 'Autres'}.get(old_type, old_type)
        if not isinstance(row.get('Selected metrics'), list):
            custom = str(row.get('Custom metrics', '')).strip()
            if custom:
                chosen = re.split(r'[;\n|]+', custom)
                wanted = {_metric_key(v.strip()) for v in chosen if v.strip()}
                selected = [m for m in available if _metric_key(m) in wanted]
            elif old_type == 'Standard' and any(m in row for m in STANDARD_METRICS):
                wanted = {_metric_key(m) for m in STANDARD_METRICS if row.get(m)}
                selected = [m for m in available if _metric_key(m) in wanted]
            elif old_type == 'Libre':
                selected = available[:]
            else:
                selected = default_metric_selection(row['Type'], available)
            row['Selected metrics'] = selected
        row['Metric labels'] = row.get('Metric labels') if isinstance(row.get('Metric labels'), dict) else {}
        row['Selection type'] = row['Type']
        if 'Group ID' not in row:
            from .grouping import question_family, stage_for
            stage = stage_for(row, stage_names)
            family = question_family(row['Question ID']) if row['Display label'] != 'Color' else ''
            row['Group ID'] = (hashlib.sha1((str(row['Section']) + '\0' + str(row['Display label'])+'\0'+stage+'\0'+family+'\0'+row['Type']).encode()).hexdigest()[:12]
                               if row.get('Metric label') else '')
        row['Available metric list'] = available
        row['Metric availability'] = {metric:list(files) for metric,files in by_id[row['Question ID']].metric_availability}
        row['Result export count'] = len({filename for files in row['Metric availability'].values() for filename in files})
    return sorted(result, key=lambda r: (int(r['Order']), r['Question ID']))


def change_type(row, new_type):
    if new_type not in QUESTION_TYPES:
        raise ValueError('Type de question inconnu.')
    if row['Type'] != new_type:
        row['Type'] = new_type
        row['Selection type'] = new_type
        row['Selected metrics'] = default_metric_selection(new_type, row['Available metric list'])
        row['Custom metrics'] = ''


def set_metric_selection(row, selected, labels=None):
    allowed = set(row['Available metric list'])
    if not set(selected).issubset(allowed):
        raise ValueError('Une métrique sélectionnée est absente de cette question.')
    row['Selected metrics'] = list(dict.fromkeys(selected))
    if labels is not None:
        row['Metric labels'] = {k: str(v).strip() for k, v in labels.items() if k in allowed and str(v).strip()}
    for metric in STANDARD_METRICS:
        row[metric] = _metric_key(metric) in {_metric_key(m) for m in selected}


def matching_selection(selected, available):
    """Match exact metrics/aggregate names, or numbered codes across a battery."""
    wanted = {_metric_key(m) for m in selected}
    codes = {match.group(1) for m in selected if (match := re.match(r'^\s*(\d+)\s*[-_.: ]', m))}
    return [m for m in available if _metric_key(m) in wanted
            or ((match := re.match(r'^\s*(\d+)\s*[-_.: ]', m)) and match.group(1) in codes)]


def reorder_rows(rows, ordered_ids):
    expected = [r['Question ID'] for r in rows]
    if len(ordered_ids) != len(expected) or set(ordered_ids) != set(expected):
        raise ValueError('Ordre incomplet ou identifiants de questions en double.')
    by_id = {r['Question ID']: r for r in deepcopy(rows)}
    result = []
    for order, qid in enumerate(ordered_ids, 1):
        row = by_id[qid]
        row['Order'] = order
        result.append(row)
    return result


def rename_group(rows, group_id, label):
    if not str(label).strip():
        raise ValueError('Le libellé du groupe ne peut pas être vide.')
    for row in rows:
        if row.get('Group ID') == group_id:
            row['Display label'] = str(label).strip()


def group_rows(rows):
    groups = {}
    for row in rows:
        gid = row.get('Group ID')
        if gid:
            group = groups.setdefault(gid, {'id': gid, 'label': row['Display label'], 'members': []})
            group['members'].append(row['Question ID'])
    return list(groups.values())


def export_rows(rows):
    internal={'Available metric list','Metric availability','Result export count'}
    return [{k: deepcopy(v) for k, v in row.items() if k not in internal} for row in rows]
