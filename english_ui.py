"""English presentation, with backwards-compatible internal profile/memory keys.

Only tool-owned metadata is translated in tables. Source identifiers, questionnaire
wording, product names and user clean labels remain untouched.
"""
from functools import wraps
import re
import pandas as pd
import streamlit as st
from templyfier.english_catalog import TEXT

_PIECES=sorted(((a,b) for a,b in TEXT.items() if a!=b and len(a)>=5), key=lambda p:len(p[0]),reverse=True)
_CATEGORICAL={'Type','Type de question','Scope','Portée','Décision','Sens favorable','Confidence','Confiance CMR',
    'Statut','Résultat','Rôle','CMI role','Élargissement possible','Utilité proposée','Grouping choice'}
_PROTECTED={'Question ID','Question G-Sight','Question','Questions','Question clean','Display label','Metric label',
    'Avant','Après','Choix importé','Choix actuel','Libellés proposés','Nom du groupe','Variable clean','Variable / item','Item clean','Libellé clean','Item / métrique','Métrique G-Sight',
    'Métrique source','Source metric','Nom source','Nom affiché','Benchmark','Code stable','Nom court pour l’onglet',
    'Ligne complémentaire / formule','Fichier','Nom de l’onglet','Exemples','Current label','Libellé actuel',
    'Groupe proposé','Item proposé','Label KPI court','Section','Variable','Item','Metric','Source','Code'}


def text(value):
    if not isinstance(value,str):return value
    if value in TEXT:return TEXT[value]
    for original,translated in _PIECES:
        if original in value:
            prefix=r'(?<!\w)' if original[0].isalnum() or original[0]=='_' else ''
            suffix=r'(?!\w)' if original[-1].isalnum() or original[-1]=='_' else ''
            value=re.sub(prefix+re.escape(original)+suffix,lambda match:translated,value)
    return value


def choice(value):
    return TEXT.get(value,value) if isinstance(value,str) else value


def _arguments(args,kwargs):
    args=list(args);kwargs=dict(kwargs)
    if args and isinstance(args[0],str):args[0]=text(args[0])
    for key in ('label','body','help','placeholder','title','text'):
        if isinstance(kwargs.get(key),str):kwargs[key]=text(kwargs[key])
    return args,kwargs


def _table(original,args,kwargs):
    args=list(args);kwargs=dict(kwargs)
    frame=args[0] if args else kwargs.get('data')
    if isinstance(frame,(list,dict)):
        frame=pd.DataFrame(frame)
    if not isinstance(frame,pd.DataFrame):return original(*args,**kwargs)
    displayed=frame.copy();names={col:choice(col) for col in frame.columns}
    if len(set(names.values()))!=len(names):raise ValueError('English column names are ambiguous.')
    inverse={v:k for k,v in names.items()}
    for column in displayed.columns:
        if column not in _PROTECTED:
            displayed[column]=displayed[column].map(lambda v:text(v) if isinstance(v,str) else v)
    displayed=displayed.rename(columns=names)
    if args:args[0]=displayed
    else:kwargs['data']=displayed
    if isinstance(kwargs.get('disabled'),list):kwargs['disabled']=[names.get(c,c) for c in kwargs['disabled']]
    if isinstance(kwargs.get('column_order'),list):kwargs['column_order']=[names.get(c,c) for c in kwargs['column_order']]
    if kwargs.get('column_config'):
        kwargs['column_config']={names.get(c,c):configuration for c,configuration in kwargs['column_config'].items()}
    # Old saved widget edits and QA scripts can still contain legacy column names.
    key=kwargs.get('key')
    if key and key in st.session_state and isinstance(st.session_state[key],dict):
        state=st.session_state[key]
        edits=state.get('edited_rows',{})
        rewritten={i:{names.get(c,c):choice(v) if inverse.get(c,c) in _CATEGORICAL else v for c,v in edit.items()} for i,edit in edits.items()}
        if rewritten!=edits:state['edited_rows']=rewritten
    result=original(*args,**kwargs)
    if isinstance(result,pd.DataFrame):
        result=result.rename(columns=inverse)
        for column in result.columns:
            if column not in _PROTECTED:
                originals={text(v):v for v in frame[column] if isinstance(v,str)}
                if column in _CATEGORICAL:
                    for legacy,english in TEXT.items():originals.setdefault(english,legacy)
                result[column]=result[column].map(lambda v:originals.get(v,v) if isinstance(v,str) else v)
    return result


def _call(name,original,args,kwargs):
    args,kwargs=_arguments(args,kwargs)
    if name=='tabs' and args:args[0]=[text(v) for v in args[0]]
    if name in {'dataframe','data_editor'}:return _table(original,args,kwargs)
    if name in {'selectbox','multiselect','radio','select_slider','segmented_control','pills'}:
        # Translate displayed option labels only; return original values to callbacks.
        formatter=kwargs.get('format_func',lambda value:value)
        kwargs['format_func']=lambda value:choice(formatter(value))
    result=original(*args,**kwargs)
    if name=='status':
        update=result.update
        @wraps(update)
        def translated_update(*a,**k):
            a,k=_arguments(a,k);return update(*a,**k)
        result.update=translated_update
    return result


def install():
    if getattr(st,'_templyfier_english',False):return
    names=('title','header','subheader','markdown','caption','text','info','warning','error','success',
        'button','checkbox','toggle','radio','selectbox','multiselect','select_slider','segmented_control','pills',
        'text_input','text_area','file_uploader','download_button','form_submit_button','expander','dialog',
        'progress','status','metric','dataframe','data_editor','number_input','slider','tabs','write')
    generator=type(st.sidebar)
    for name in names:
        root=getattr(st,name,None);method=getattr(generator,name,None)
        if method:
            def translated_method(self,*args,_name=name,_original=method,**kwargs):
                return _call(_name,lambda *a,**k:_original(self,*a,**k),args,kwargs)
            setattr(generator,name,translated_method)
        if root:
            def translated_root(*args,_name=name,_original=root,**kwargs):
                return _call(_name,_original,args,kwargs)
            setattr(st,name,translated_root)
    for name in ('TextColumn','CheckboxColumn','SelectboxColumn','NumberColumn','ListColumn'):
        original=getattr(st.column_config,name)
        def translated_column(*args,_original=original,**kwargs):
            args,kwargs=_arguments(args,kwargs)
            if 'options' in kwargs:kwargs['options']=[choice(v) for v in kwargs['options']]
            return _original(*args,**kwargs)
        setattr(st.column_config,name,translated_column)
    st._templyfier_english=True
