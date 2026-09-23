"""CMI checks and safe metric changes, with no dependency on the interface."""
from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json
import re

from .editor_model import QUESTION_TYPES, set_metric_selection
from .smart import (STANDARD_METRICS, _metric_key, _normal, _question_applies_to_split,
                    clean_metric_label, default_metric_selection, grouped_metric_label)


def available_metrics(row, by_id=None):
    if by_id is not None:
        return list(by_id.get(row['Question ID'], []))
    return list(row.get('Available metric list', []))


def audit_questions(rows, available_by_id=None, split_names=None, metric_availability_by_id=None, result_export_count=None):
    """Only objective omissions block export; editorial suggestions are warnings."""
    issues = []
    kept = [r for r in rows if r.get('Keep')]
    def add(row, code, message, remedy, blocking=False):
        issues.append({'Question ID':row.get('Question ID',''),
            'Question':row.get('Metric label') or row.get('Display label',''),
            'Niveau':'À corriger' if blocking else 'À vérifier', 'Code':code,
            'Point à traiter':message, 'Action conseillée':remedy})
    ids=Counter(str(r.get('Question ID','')).casefold() for r in rows)
    group_items=defaultdict(list)
    for row in kept:
        qid=row.get('Question ID','')
        available=available_metrics(row,available_by_id)
        selected=row.get('Selected metrics', [])
        selected=selected if isinstance(selected,list) else []
        if ids[str(qid).casefold()]>1:
            add(row,'duplicate_id','Identifiant G-Sight répété.','Corriger le profil ou le fichier source.',True)
        if row.get('Type') not in QUESTION_TYPES:
            add(row,'unknown_type','Type de question non reconnu.','Choisir un type dans le tableau.',True)
        if not str(row.get('Display label') or '').strip() or (row.get('Group ID') and not str(row.get('Metric label') or '').strip()):
            add(row,'empty_label','Libellé de variable ou d’item vide.','Renseigner un libellé clean.',True)
        if not selected:
            add(row,'no_metrics','Aucune métrique retenue.','Choisir des métriques ou retirer la question.',True)
        known={_metric_key(m) for m in available}
        missing=[m for m in selected if _metric_key(m) not in known]
        if missing:
            add(row,'missing_metrics','Métriques absentes du DataViz : '+', '.join(missing),
                'Adapter le choix dans l’éditeur de métriques ; ne pas inventer les valeurs.',True)
        presence=(metric_availability_by_id or {}).get(qid,row.get('Metric availability',{}))
        total=result_export_count or row.get('Result export count',0)
        partial=[]
        if total:
            for metric in selected:
                files=next((v for k,v in presence.items() if _metric_key(k)==_metric_key(metric)),[])
                if 0 < len(files) < total:
                    partial.append(f'{metric} ({len(files)}/{total})')
        if partial:
            add(row,'partial_metrics','Métriques présentes dans une partie des exports : '+', '.join(partial),
                'Vérifier si cette différence entre splits/vagues est attendue. Les autres métriques continueront à être exportées.')
        if split_names is not None and split_names and not any(_question_applies_to_split(row,s) for s in split_names):
            add(row,'excluded_everywhere','Le filtre de splits exclut cette question de tous les onglets prévus.',
                'Corriger « Splits inclus » ou retirer cette question.',True)
        if str(row.get('Confidence','')).casefold()=='faible' or (row.get('Confidence')=='Moyenne' and row.get('Type') in {'Autres','Bipolaire'}):
            add(row,'uncertain_type','Le type détecté est incertain.','Vérifier le type et ses métriques avec le questionnaire.')
        if 'confirmer' in str(row.get('CMI note','')).casefold():
            add(row,'purpose',str(row['CMI note']),'Confirmer que cette question sert l’objectif du projet.')
        if row.get('Type') in {'CATA','Listing','Preference'} and any(_metric_key(m)=='mean' for m in selected):
            add(row,'mean_on_codes','Mean est retenu pour une liste ou une question CATA.',
                'Vérifier que la moyenne des codes est bien voulue ; les modalités sont généralement plus lisibles.')
        if row.get('KPI Summary') and not str(row.get('Summary label') or '').strip():
            add(row,'summary_label','Le libellé court du KPI est vide.','Donner un nom court à ce KPI.')
        gid=row.get('Group ID')
        if gid:
            group_items[(gid,_normal(str(row.get('Metric label',''))))].append(row)
    for members in group_items.values():
        if len(members)>1:
            for row in members:
                add(row,'duplicate_item','Cet item porte le même nom qu’un autre item du groupe.',
                    'Comparer les identifiants source avant de renommer ; aucune fusion automatique.')
    blockers=[i for i in issues if i['Niveau']=='À corriger']
    return {'issues':issues,'blockers':blockers,'ready':bool(kept) and not blockers,
            'kept':len(kept),'attention_ids':{i['Question ID'] for i in issues}}


def metric_presets(row):
    available=available_metrics(row)
    aggregate_keys={_metric_key(m) for m in STANDARD_METRICS}
    numbered=[m for m in available if re.match(r'^\s*\d+\s*[-_.: ]',m) and _metric_key(m) not in aggregate_keys]
    presets={'Choix actuels':list(row.get('Selected metrics',[])),
             'Proposition du type':default_metric_selection(row['Type'],available)}
    if numbered:
        presets['Toutes les modalités']=numbered
    else:
        individual=[m for m in available if _metric_key(m) not in aggregate_keys]
        if individual:presets['Toutes les modalités']=individual
    if row['Type']=='CATA':
        for name,code in [('CATA : réponses 2-','2'),('CATA : réponses 1-No','1')]:
            chosen=[m for m in numbered if re.match(r'^\s*'+code+r'\s*[-_.: ]',m)]
            if chosen:presets[name]=chosen
        both=[m for m in numbered if re.match(r'^\s*[12]\s*[-_.: ]',m)]
        if both:presets['CATA : les deux réponses']=both
    boxes=[m for m in available if _metric_key(m) in aggregate_keys and _metric_key(m)!='mean']
    if boxes:presets['Boxes disponibles, sans Mean']=boxes
    mean=[m for m in available if _metric_key(m)=='mean']
    if mean:presets['Mean uniquement']=mean
    presets['Toutes les métriques disponibles']=available
    return presets


def _code(metric):
    if _metric_key(metric) in {_metric_key(m) for m in STANDARD_METRICS}:return None
    match=re.match(r'^\s*(\d+)\s*[-_.: ]',metric)
    return match.group(1) if match else None


def _cata_yes_no(row):
    available=available_metrics(row)
    codes={_code(m) for m in available if _code(m)}
    negative=[m for m in available if _code(m)=='1']
    return row['Type']=='CATA' and codes=={'1','2'} and bool(negative) and all(
        re.match(r'^\s*1\s*[-_.: ]+\s*(?:no|non)\s*$',m,re.I) for m in negative)


def safe_metric_match(source, target, chosen):
    """Do not equate two numbered answers just because they share a code."""
    available=available_metrics(target)
    cata_codes=_cata_yes_no(source) and _cata_yes_no(target)
    matched,missing=[],[]
    for wanted in chosen:
        matches=[m for m in available if _metric_key(m)==_metric_key(wanted)]
        if not matches and cata_codes and _code(wanted):
            matches=[m for m in available if _code(m)==_code(wanted)]
        if len(matches)==1:
            if matches[0] not in matched:matched.append(matches[0])
        else:
            missing.append(wanted)
    return matched,missing


def plan_metric_change(rows, source_id, chosen, labels, scope):
    if scope not in {'Cette question','Tout le groupe','Toutes les questions de ce type'}:
        raise ValueError('Portée de modification inconnue.')
    source=next((r for r in rows if r['Question ID']==source_id),None)
    if source is None:raise ValueError('Question source introuvable.')
    if not set(chosen).issubset(set(available_metrics(source))):
        raise ValueError('Une métrique choisie n’existe pas dans la question source.')
    if scope!='Cette question' and not chosen:
        raise ValueError('Une sélection vide ne peut pas être appliquée en masse. Retire les questions avec « Garder » si nécessaire.')
    changed=deepcopy(rows)
    preview=[]
    for row in changed:
        same=row['Question ID']==source_id
        affected=same or (row.get('Keep') and (
            (scope=='Tout le groupe' and source.get('Group ID') and row.get('Group ID')==source['Group ID'])
            or (scope=='Toutes les questions de ce type' and row['Type']==source['Type'])))
        if not affected:continue
        before=list(row['Selected metrics'])
        matched,missing=(list(chosen),[]) if same else safe_metric_match(source,row,chosen)
        # Preserve the WHOLE target recipe when one requested metric has no safe match.
        # A partial intersection would silently throw away an intentional choice.
        if missing:
            status='Inchangée : correspondance incomplète'
        else:
            set_metric_selection(row,matched,labels if same else None)
            status='Appliquée' if before!=row['Selected metrics'] or same else 'Déjà identique'
        preview.append({'Question ID':row['Question ID'],
            'Question':row.get('Metric label') or row['Display label'],
            'Avant':' · '.join(before),'Après':' · '.join(row['Selected metrics']),
            'Résultat':status,'Sans correspondance sûre':' · '.join(missing)})
    return changed,preview


def preview_rows(rows, split_name=None, available_by_id=None, metric_availability_by_id=None, result_export_count=None):
    """Preview the label/metric structure only, not a fabricated value preview."""
    result=[]
    previous=None
    for row in sorted(rows,key=lambda r:(int(r.get('Order',9999)),r['Question ID'])):
        if not row.get('Keep') or (split_name is not None and not _question_applies_to_split(row,split_name)):
            continue
        available=available_metrics(row,available_by_id)
        selected={_metric_key(m) for m in row.get('Selected metrics',[])}
        # The engine writes metrics in source order, regardless of selection order.
        metrics=[m for m in available if _metric_key(m) in selected]
        identity=(row.get('Group ID') or row['Question ID'],row.get('Section'),row['Display label'])
        for index,metric in enumerate(metrics):
            grouped=bool(row.get('Metric label'))
            variable=row['Display label'] if (grouped and identity!=previous) or (not grouped and index==0) else ''
            item=grouped_metric_label(row,metric,len(metrics)) if grouped else clean_metric_label(row,metric)
            if not grouped and row['Type'] in {'CATA','Attribute'}:
                variable=''
                item=row['Display label'] if len(metrics)==1 else f"{row['Display label']} · {clean_metric_label(row,metric)}"
            result.append({'Section':row.get('Section',''),'Variable clean':variable,
                'Item / métrique':item,
                'Question ID':row['Question ID'],'Métrique source':metric,
                'Présence':(f"{len((metric_availability_by_id or {}).get(row['Question ID'],row.get('Metric availability',{})).get(metric,[]))}/{result_export_count or row.get('Result export count',0)} exports"
                            if result_export_count or row.get('Result export count',0) else 'Non détaillée'),
                'Type':row['Type']})
            previous=identity if grouped else None
    return result


def profile_comparison(proposals, profile):
    saved={str(r['Question ID']).casefold():r for r in profile.get('questions',[])}
    current={p.question_id.casefold():p for p in proposals}
    details=[]
    for qid in current.keys()-saved.keys():
        details.append({'Statut':'Nouvelle question','Question ID':current[qid].question_id,'Détail':'Réglages proposés à vérifier.'})
    for qid in saved.keys()-current.keys():
        details.append({'Statut':'Absente des exports','Question ID':saved[qid]['Question ID'],'Détail':'Non reprise dans ce projet.'})
    for qid in current.keys() & saved.keys():
        known={_metric_key(m) for m in current[qid].metrics}
        missing=[m for m in saved[qid].get('Selected metrics',[]) if _metric_key(m) not in known]
        if missing:details.append({'Statut':'Métriques à adapter','Question ID':current[qid].question_id,'Détail':', '.join(missing)})
    return {'matched':len(current.keys() & saved.keys()),'new':len(current.keys()-saved.keys()),
            'absent':len(saved.keys()-current.keys()),'details':sorted(details,key=lambda d:(d['Statut'],d['Question ID']))}


def validate_profile(payload):
    if not isinstance(payload,dict) or payload.get('version')!=1 or not isinstance(payload.get('questions'),list):
        raise ValueError('Profil Templyfier non reconnu : format ou version incorrecte.')
    if not isinstance(payload.get('settings',{}),dict):
        raise ValueError('Le champ settings du profil doit être un objet de réglages.')
    ids=set()
    for position,row in enumerate(payload['questions'],1):
        if not isinstance(row,dict) or not isinstance(row.get('Question ID'),str) or not row['Question ID'].strip():
            raise ValueError(f'Question {position} du profil : identifiant G-Sight manquant.')
        qid=row['Question ID']
        if qid.casefold() in ids:
            raise ValueError(f'Profil ambigu : la question {qid} apparaît plusieurs fois.')
        ids.add(qid.casefold())
        if 'Type' in row and (not isinstance(row['Type'],str) or row['Type'] not in {*QUESTION_TYPES,'Attribute','Libre','Delete'}):
            raise ValueError(f'{qid} : type de question non reconnu dans le profil.')
        for field in ('Keep','KPI Summary'):
            if field in row and not isinstance(row[field],bool):
                raise ValueError(f'{qid} : le champ {field} doit être vrai ou faux.')
        if 'Order' in row:
            value=row['Order']
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not float(value).is_integer() or value<1:
                raise ValueError(f'{qid} : l’ordre doit être un entier positif.')
        for field in ('Display label','Metric label','Section','Included splits','Group ID'):
            if field in row and not isinstance(row[field],str):
                raise ValueError(f'{qid} : le champ {field} doit être du texte.')
        if 'Selected metrics' in row and (not isinstance(row['Selected metrics'],list)
                or any(not isinstance(m,str) or not m.strip() for m in row['Selected metrics'])):
            raise ValueError(f'{qid} : les métriques doivent être une liste de libellés.')
        if 'Metric labels' in row and (not isinstance(row['Metric labels'],dict)
                or any(not isinstance(k,str) or not isinstance(v,str) for k,v in row['Metric labels'].items())):
            raise ValueError(f'{qid} : les renommages de métriques sont mal formés.')
    return payload


def editor_view_key(rows, search, scope):
    return hashlib.sha1(json.dumps([[r['Question ID'] for r in rows],search,scope],ensure_ascii=False).encode()).hexdigest()[:12]
