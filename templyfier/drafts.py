"""Personal configuration drafts. No raw files, scores or generated workbooks."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from uuid import uuid4
from . import server_storage as storage
from .review import validate_profile
from .smart import STANDARD_METRICS

DEFAULT={'version':1,'drafts':{}}

SETTING_FIELDS=set('standard_metrics benchmark_count benchmark_source benchmark_sheet_mode benchmark_labels include_screeners study_format clt_block_design clt_stages clt_stage_order test_type mean_decimals paired_swaps include_sections include_deltas output_sheet_order show_monadic_gaps highlight_benchmarks product_labels product_subtitles cmr_name_mode summary_scope summary_metric_strategy include_summary_details'.split())
ROW_FIELDS={'Keep','Order','Section','Question ID','Display label','Metric label','Type','Confidence','CMI role','CMI note','Available metrics','Availability','Included splits','KPI Summary','Summary label','Sens favorable','Custom metrics','Selected metrics','Metric labels','Selection type','Group ID','Grouping choice','Dismissed groups','Ungrouped labels',*STANDARD_METRICS}
SETTING_FIELDS.add('benchmark_keys')
OPTION_VALUES={'benchmark_source':{'auto','manual'},'benchmark_sheet_mode':{'combined','separate','auto_exports','auto_columns','benchmark_columns'},'clt_block_design':{'Complete block','Incomplete block','unknown'},'test_type':{'Monadic','Paired'},'output_sheet_order':{'benchmark_first','split_first'},'summary_scope':{'total','all','none'},'summary_metric_strategy':{'priority','primary','consensus'}}

def _settings_only(profile):
    profile=validate_profile(profile)
    if set(profile)-{'version','settings','questions'}:raise ValueError('Drafts may contain only question settings, not extra data.')
    if set(profile.get('settings',{}))-SETTING_FIELDS:raise ValueError('Unexpected project setting in draft.')
    if len(profile['questions'])>10000:raise ValueError('Too many questions in draft.')
    for row in profile['questions']:
        if set(row)-ROW_FIELDS:raise ValueError('Unexpected question data in draft; consumer values are not accepted.')
    # Known field names are required at every nested object boundary.
    def bounded(value,depth=0):
        if depth>5:raise ValueError('Draft settings are too deeply nested.')
        if isinstance(value,dict):
            if len(value)>10000 or any(not isinstance(k,str) or len(k)>1000 for k in value):raise ValueError('Invalid draft settings object.')
            for child in value.values():bounded(child,depth+1)
        elif isinstance(value,list):
            if len(value)>10000:raise ValueError('Invalid draft settings list.')
            for child in value:bounded(child,depth+1)
        elif isinstance(value,str):
            if len(value)>30000:raise ValueError('Draft text is too long.')
        elif value is not None and not isinstance(value,(bool,int,float)):raise ValueError('Invalid draft setting value.')
    bounded(profile)
    for key,value in profile.get('settings',{}).items():
        if key in OPTION_VALUES and (not isinstance(value,str) or value not in OPTION_VALUES[key]):raise ValueError('Unrecognised project option in draft.')
        if key=='paired_swaps':
            if not isinstance(value,dict) or any(not isinstance(v,list) or any(type(n)!=int or n<1 for n in v) for v in value.values()):raise ValueError('Invalid paired settings.')
        elif key in {'standard_metrics','benchmark_keys','benchmark_labels','product_labels','product_subtitles','clt_stages','clt_stage_order'}:
            if not isinstance(value,list) or any(not isinstance(v,str) for v in value):raise ValueError('Invalid project label list.')
            if key=='benchmark_keys' and len(value)!=len(set(value)):raise ValueError('Duplicate benchmark codes in draft.')
        elif key in {'benchmark_count','mean_decimals'}:
            if type(value)!=int or not 0<=value<=(2 if key=='mean_decimals' else 500):raise ValueError('Invalid numeric project option.')
        elif key in {'include_screeners','include_sections','include_deltas','show_monadic_gaps','highlight_benchmarks','include_summary_details'}:
            if type(value)!=bool:raise ValueError('Invalid project checkbox setting.')
        elif not isinstance(value,str):raise ValueError('Invalid project option.')
    for row in profile['questions']:
        for key,value in row.items():
            if key in {'Metric labels','Ungrouped labels'}:
                if not isinstance(value,dict) or any(not isinstance(v,str) for v in value.values()):raise ValueError('Invalid label settings.')
            elif isinstance(value,dict):raise ValueError('Unexpected nested question data.')
            elif key in {'Selected metrics','Dismissed groups'}:
                if not isinstance(value,list) or any(not isinstance(v,str) for v in value):raise ValueError('Invalid question settings list.')
            elif key in {'Keep','KPI Summary',*STANDARD_METRICS}:
                if type(value)!=bool:raise ValueError('Invalid question checkbox setting.')
            elif key=='Order':pass
            elif not isinstance(value,str):raise ValueError('Invalid question text setting.')
    return deepcopy(profile)

def retention_days():
    raw=os.environ.get('TEMPLYFIER_DRAFT_RETENTION_DAYS','').strip()
    if not raw:return None
    try:days=int(raw)
    except ValueError:raise ValueError('IT must set draft retention to a whole number of days.')
    if not 1<=days<=365:raise ValueError('Draft retention must be between 1 and 365 days.')
    return days

def fingerprints(files,cmr=None):
    items=[{'role':'DataViz','name':name,'sha256':hashlib.sha256(data).hexdigest()} for name,data in files]
    if cmr:items.append({'role':'CMR','name':cmr[0],'sha256':hashlib.sha256(cmr[1]).hexdigest()})
    return sorted(items,key=lambda item:(item['role'],item['name'],item['sha256']))

def validate_bundle(bundle):
    if not isinstance(bundle,dict) or bundle.get('version')!=1:raise ValueError('Unsupported draft format.')
    if set(bundle)-{'version','profile','sources','split_names'}:raise ValueError('Unexpected draft data.')
    profile=_settings_only(bundle.get('profile'))
    sources=bundle.get('sources')
    splits=bundle.get('split_names')
    if not isinstance(sources,list) or not sources or len(sources)>500:raise ValueError('Invalid draft source list.')
    for source in sources:
        if not isinstance(source,dict) or set(source)!={'role','name','sha256'}:raise ValueError('Invalid draft source descriptor.')
        if source['role'] not in {'DataViz','CMR'} or not isinstance(source['name'],str) or len(source['name'])>300:raise ValueError('Invalid draft source name.')
        if not isinstance(source['sha256'],str) or len(source['sha256'])!=64 or any(c not in '0123456789abcdef' for c in source['sha256']):raise ValueError('Invalid draft source fingerprint.')
    if not isinstance(splits,dict) or any(not isinstance(k,str) or not isinstance(v,str) or len(v)>100 for k,v in splits.items()):raise ValueError('Invalid draft split names.')
    result={'version':1,'profile':profile,'sources':deepcopy(sources),'split_names':deepcopy(splits)}
    if len(json.dumps(result).encode())>5*1024*1024:raise ValueError('Draft settings exceed the 5 MB limit.')
    return result

def matches(bundle,sources):
    return validate_bundle(bundle)['sources']==sources

def make_bundle(profile,sources,split_names):
    return validate_bundle({'version':1,'profile':profile,'sources':sources,'split_names':split_names})

def _enabled():
    if not storage.server_mode():raise ValueError('Persistent drafts require server mode.')
    storage.current_identity()
    days=retention_days()
    if days is None:raise ValueError('Persistent drafts are disabled until IT configures retention.')
    return days

def _validate_store(store):
    if not isinstance(store,dict) or store.get('version')!=1 or not isinstance(store.get('drafts'),dict):raise ValueError('Draft storage is unreadable; no settings were overwritten.')
    for identifier,draft in store['drafts'].items():
        if not isinstance(identifier,str) or not isinstance(draft,dict) or not isinstance(draft.get('name'),str) or not isinstance(draft.get('token'),str):raise ValueError('Invalid stored draft.')
        validate_bundle(draft.get('bundle'))
        for key in ('saved','expires'):
            try:
                stamp=datetime.fromisoformat(draft[key])
                if stamp.tzinfo is None:raise ValueError('Missing time zone.')
            except (KeyError,TypeError,ValueError) as exc:raise ValueError('Invalid stored draft date; no settings were overwritten.') from exc
    return store

def list_drafts():
    _enabled();store=_validate_store(storage.read_document('drafts',DEFAULT))
    now=datetime.now(timezone.utc)
    expired={k for k,v in store['drafts'].items() if datetime.fromisoformat(v['expires'])<=now}
    if expired:
        def clean(latest):
            latest=_validate_store(latest)
            latest['drafts']={k:v for k,v in latest['drafts'].items() if datetime.fromisoformat(v['expires'])>now}
            return latest,deepcopy(latest['drafts'])
        return storage.mutate_document('drafts',DEFAULT,'draft_expiry',clean)
    return deepcopy(store['drafts'])

def save_draft(name,bundle,identifier=None,expected=None):
    days=_enabled();bundle=validate_bundle(bundle)
    if not isinstance(name,str) or not name.strip() or len(name)>100:raise ValueError('Use a draft name of 1–100 characters.')
    identifier=identifier or uuid4().hex
    now=datetime.now(timezone.utc)
    record={'name':name.strip(),'bundle':bundle,'token':uuid4().hex,'saved':now.isoformat(),
            'expires':(now+timedelta(days=days)).isoformat()}
    def change(latest):
        latest=_validate_store(latest)
        latest['drafts']={k:v for k,v in latest['drafts'].items() if datetime.fromisoformat(v['expires'])>now}
        prior=latest['drafts'].get(identifier)
        if (prior['token'] if prior else None)!=expected:raise ValueError('This draft changed or expired. Refresh and review it before saving.')
        if not prior and len(latest['drafts'])>=20:raise ValueError('Keep at most 20 active drafts. Delete an old draft first.')
        latest['drafts'][identifier]=record
        return latest,(identifier,deepcopy(record))
    return storage.mutate_document('drafts',DEFAULT,'draft_save',change)

def delete_draft(identifier,expected):
    _enabled()
    def change(latest):
        latest=_validate_store(latest);prior=latest['drafts'].get(identifier)
        if not prior or prior['token']!=expected:raise ValueError('This draft changed. Refresh before deleting it.')
        del latest['drafts'][identifier]
        return latest,None
    storage.mutate_document('drafts',DEFAULT,'draft_delete',change)
