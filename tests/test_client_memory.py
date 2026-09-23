"""Memory must transfer explicit choices without equating unrelated responses."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from templyfier.client_memory import (SCOPES, apply_suggestions, delete_rules,
    ensure_client, load_memories, memory_suggestions, teach, teaching_candidates)
from templyfier.editor_model import set_metric_selection
from templyfier.grouping import accept_suggestion, dismiss_suggestion, separate_group, suggest_groups


METRICS = ['1-Very poor','2-Poor','3-Neutral','4-Good','5-Very good',
           'Mean','Top Box','Top 2 Boxes','Top 3 Boxes','Bottom 2 Boxes']


def row(qid='Q-1-1-Overall opinion', kind='Standard', metrics=None, selected=None, label='Overall opinion', group=''):
    metrics = list(metrics if metrics is not None else METRICS)
    return {'Question ID':qid, 'Type':kind, 'Section':'Product', 'Order':1, 'Keep':True,
            'Display label':label, 'Metric label':'', 'Group ID':group, 'Grouping choice':'',
            'Dismissed groups':[], 'Available metric list':metrics, 'Metric labels':{},
            'Selected metrics':list(selected if selected is not None else ['Mean','Top Box','Top 2 Boxes','Bottom 2 Boxes']),
            'Selection type':kind}


def battery(number=3, label='Texture', items=('Soft','Smooth','Silky')):
    rows = [row(f'Q-{number}-{i}-{label} - {item}',kind='CATA',metrics=['1-No',f'2-{item}'],
                selected=[f'2-{item}'],label=f'{label} - {item}') for i,item in enumerate(items,1)]
    for i,r in enumerate(rows,1):r['Order']=i
    return rows


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.path = Path(tempfile.gettempdir())/f'memory_test_{uuid4().hex}.json'
        self.cid = ensure_client('Client A',self.path)

    def tearDown(self):
        # Only our single generated file is removed; no recursive cleanup.
        if self.path.exists():self.path.unlink()

    def learn(self, baseline, changed, scope=SCOPES[0], kind='metrics', project='project-1'):
        candidates = [c for c in teaching_candidates(baseline,changed) if c['kind']==kind]
        for c in candidates:c['scope']=scope
        teach(self.cid,candidates,project,self.path)
        return load_memories(self.path)['clients'][self.cid]['rules']

    def test_defaults_are_not_teaching_candidates(self):
        original=[row()]
        self.assertEqual(teaching_candidates(original,deepcopy(original)),[])

    def test_changed_ids_reuse_wording_and_show_source_before_apply(self):
        original=[row()]; changed=deepcopy(original)
        set_metric_selection(changed[0],['Top 2 Boxes','Top 3 Boxes'],{'Top 3 Boxes':'T3B'})
        rules=self.learn(original,changed)
        new=[row('Q-89-7-Overall opinion')]; before=deepcopy(new)
        proposals,omissions,ignored=memory_suggestions(new,new,rules)
        self.assertEqual(new,before)
        self.assertEqual(len(proposals),1)
        self.assertIn('T3B',proposals[0]['after'])
        self.assertIn('Choix enseigné',proposals[0]['why'])
        result=apply_suggestions(new,proposals,[proposals[0]['id']])
        self.assertEqual(result[0]['Selected metrics'],['Top 2 Boxes','Top 3 Boxes'])
        self.assertEqual(result[0]['Metric labels']['Top 3 Boxes'],'T3B')
        self.assertEqual(result[0]['Question ID'],'Q-89-7-Overall opinion')

    def test_clients_are_isolated_and_names_are_normalized(self):
        other=ensure_client('Client B',self.path)
        self.assertEqual(ensure_client(' client   A ',self.path),self.cid)
        original=[row()]; changed=deepcopy(original); changed[0]['Selected metrics']=['Mean']
        self.learn(original,changed)
        self.assertEqual(load_memories(self.path)['clients'][other]['rules'],[])

    def test_type_recipe_transfers_only_matching_scale_and_stage(self):
        original=[row()]; changed=deepcopy(original); changed[0]['Selected metrics']=['Top 3 Boxes']
        rules=self.learn(original,changed,SCOPES[1])
        targets=[row('Q-9-1-Softness'),row('Q-9-2-Neat opinion'),
                 row('Q-9-3-Enjoyment',metrics=['1-Dislike','2-Like','Mean','Top 3 Boxes']),
                 row('Q-9-4-Choice',kind='Listing')]
        proposals,_,_=memory_suggestions(targets,targets,rules)
        self.assertEqual([p['members'][0] for p in proposals],['Q-9-1-Softness'])

    def test_missing_metric_keeps_entire_existing_recipe(self):
        original=[row()]; changed=deepcopy(original); changed[0]['Selected metrics']=['Top 2 Boxes','Top 3 Boxes']
        rules=self.learn(original,changed,SCOPES[1])
        target=[row('Q-8-1-Softness',metrics=[m for m in METRICS if m!='Top 3 Boxes'])]
        before=deepcopy(target)
        proposals,omissions,_=memory_suggestions(target,target,rules)
        self.assertEqual(proposals,[]); self.assertEqual(target,before)
        self.assertIn('Top 3 Boxes',omissions[0]['Motif'])

    def test_duplicate_wording_is_not_guessed(self):
        original=[row()]; changed=deepcopy(original); changed[0]['Selected metrics']=['Mean']
        rules=self.learn(original,changed)
        targets=[row('Q-2-1-Overall opinion'),row('Q-3-1-Overall opinion')]
        proposals,omissions,_=memory_suggestions(targets,targets,rules)
        self.assertEqual(proposals,[]); self.assertIn('Plusieurs',omissions[0]['Motif'])

    def test_specific_identical_or_missing_recipe_blocks_broad_override(self):
        original=[row()]; changed=deepcopy(original); changed[0]['Selected metrics']=['Mean']
        self.learn(original,changed)
        broad=deepcopy(original); broad[0]['Selected metrics']=['Top 3 Boxes']
        rules=self.learn(original,broad,SCOPES[1])
        target=[row('Q-8-1-Overall opinion',selected=['Mean'])]
        self.assertEqual(memory_suggestions(target,target,rules)[0],[])
        target=[row('Q-8-1-Overall opinion',metrics=[m for m in METRICS if m!='Mean'],selected=['Top Box'])]
        self.assertEqual(memory_suggestions(target,target,rules)[0],[])

    def test_loaded_profile_is_prioritary(self):
        original=[row()]; changed=deepcopy(original); changed[0]['Selected metrics']=['Mean']
        rules=self.learn(original,changed)
        self.assertEqual(memory_suggestions(original,original,rules,[original[0]['Question ID']])[0],[])

    def test_cata_recipe_matches_codes_without_copying_positive_label(self):
        original=[row(kind='CATA',metrics=['1-No','2-Soft'],selected=['2-Soft'])]
        changed=deepcopy(original); set_metric_selection(changed[0],['1-No'],{'1-No':'Not selected'})
        rules=self.learn(original,changed,SCOPES[1])
        target=[row('Q-8-1-Fresh',kind='CATA',metrics=['1-No','2-Fresh'],selected=['2-Fresh'])]
        proposals,_,_=memory_suggestions(target,target,rules)
        result=apply_suggestions(target,proposals,[p['id'] for p in proposals])
        self.assertEqual(result[0]['Selected metrics'],['1-No'])
        self.assertEqual(result[0]['Metric labels'],{})

    def test_unusual_numbered_answers_cannot_be_generalized(self):
        original=[row(kind='Autres',metrics=['1-Tested','2-Usual'],selected=['1-Tested','2-Usual'])]
        changed=deepcopy(original); changed[0]['Selected metrics']=['2-Usual']
        candidate=teaching_candidates(original,changed)[0]
        self.assertFalse(candidate['can_widen'])
        candidate['scope']=SCOPES[1]
        with self.assertRaises(ValueError):teach(self.cid,[candidate],'x',self.path)
        self.assertEqual(load_memories(self.path)['clients'][self.cid]['rules'],[])

    def test_comparison_reversed_labels_are_not_equated(self):
        original=[row('Q-1-Preferred product',kind='Autres',metrics=['1-Tested','2-Usual'],selected=['1-Tested','2-Usual'])]
        changed=deepcopy(original); changed[0]['Selected metrics']=['1-Tested']
        rules=self.learn(original,changed)
        target=[row('Q-8-Preferred product',kind='Autres',metrics=['1-Usual','2-Tested'],selected=['1-Usual','2-Tested'])]
        self.assertEqual(memory_suggestions(target,target,rules)[0],[])

    def test_group_learning_preserves_items_metrics_and_source_ids(self):
        original=battery(); changed=deepcopy(original)
        accept_suggestion(changed,suggest_groups(original)[0],'Skin feel')
        rules=self.learn(original,changed,kind='group')
        target=battery(number=77); before=deepcopy(target)
        proposals,_,_=memory_suggestions(target,target,rules)
        self.assertEqual(len(proposals),1)
        result=apply_suggestions(target,proposals,[proposals[0]['id']])
        self.assertEqual({r['Display label'] for r in result},{'Skin feel'})
        self.assertEqual([r['Metric label'] for r in result],['Soft','Smooth','Silky'])
        self.assertEqual([r['Question ID'] for r in result],[r['Question ID'] for r in before])
        self.assertEqual([r['Selected metrics'] for r in result],[r['Selected metrics'] for r in before])

    def test_vocabulary_rename_can_cover_different_items_without_joining_groups(self):
        original=battery(label='Texture'); accept_suggestion(original,suggest_groups(original)[0])
        changed=deepcopy(original)
        for r in changed:r['Display label']='Skin feel'
        rules=self.learn(original,changed,kind='group')
        target=battery(number=88,label='Texture',items=('Velvet','Creamy','Rich'))
        accept_suggestion(target,suggest_groups(target)[0])
        proposals,_,_=memory_suggestions(target,target,rules)
        result=apply_suggestions(target,proposals,[p['id'] for p in proposals])
        self.assertEqual({r['Display label'] for r in result},{'Skin feel'})
        self.assertEqual([r['Metric label'] for r in result],['Velvet','Creamy','Rich'])

    def test_refusal_follows_changed_ids_but_not_unrelated_items(self):
        original=battery(); changed=deepcopy(original); dismiss_suggestion(changed,suggest_groups(original)[0])
        rules=self.learn(original,changed,kind='group')
        target=battery(number=8); before=deepcopy(target)
        proposals,_,ignored=memory_suggestions(target,target,rules)
        self.assertEqual(proposals,[]); self.assertEqual(ignored,{suggest_groups(target)[0]['id']})
        self.assertEqual(target,before)
        target=battery(number=8,items=('Velvet','Creamy','Rich'))
        self.assertEqual(memory_suggestions(target,target,rules)[2],set())

    def test_separated_automatic_group_can_be_proposed_for_separation(self):
        original=battery(); accept_suggestion(original,suggest_groups(original)[0])
        changed=deepcopy(original); separate_group(changed,changed[0]['Group ID'])
        rules=self.learn(original,changed,kind='group')
        proposals,_,_=memory_suggestions(original,original,rules)
        result=apply_suggestions(original,proposals,[p['id'] for p in proposals])
        self.assertTrue(all(not r['Group ID'] for r in result))
        self.assertEqual([r['Selected metrics'] for r in result],[r['Selected metrics'] for r in original])

    def test_type_keep_and_label_do_not_erase_metrics_or_group_item(self):
        original=[row()]; changed=deepcopy(original)
        changed[0].update({'Type':'Listing','Keep':False,'Display label':'Client wording'})
        rules=self.learn(original,changed,kind='question')
        target=[row('Q-8-Overall opinion')]
        proposals,_,_=memory_suggestions(target,target,rules)
        result=apply_suggestions(target,proposals,[p['id'] for p in proposals])
        self.assertEqual(result[0]['Type'],'Listing'); self.assertFalse(result[0]['Keep'])
        self.assertEqual(result[0]['Display label'],'Client wording')
        self.assertEqual(result[0]['Selected metrics'],target[0]['Selected metrics'])

    def test_teaching_same_project_is_idempotent_and_can_update_or_forget(self):
        original=[row()]; changed=deepcopy(original); changed[0]['Selected metrics']=['Mean']
        self.learn(original,changed); rules=self.learn(original,changed)
        self.assertEqual(len(rules),1); self.assertEqual(len(rules[0]['evidence']),1)
        rules=self.learn(original,changed,project='project-2')
        self.assertEqual(len(rules[0]['evidence']),2)
        changed[0]['Selected metrics']=['Top 3 Boxes']
        rules=self.learn(original,changed)
        self.assertEqual(len(rules),1); self.assertEqual(rules[0]['value']['selected'],['Top 3 Boxes'])
        delete_rules(self.cid,[rules[0]['id']],self.path)
        self.assertEqual(load_memories(self.path)['clients'][self.cid]['rules'],[])
        delete_rules(self.cid,path=self.path)
        self.assertNotIn(self.cid,load_memories(self.path)['clients'])

    def test_conflicting_broad_recipes_do_not_partially_save(self):
        original=[row(),row('Q-2-Softness')]; changed=deepcopy(original)
        changed[0]['Selected metrics']=['Mean']; changed[1]['Selected metrics']=['Top Box']
        candidates=teaching_candidates(original,changed)
        for c in candidates:c['scope']=SCOPES[1]
        before=self.path.read_bytes()
        with self.assertRaises(ValueError):teach(self.cid,candidates,'x',self.path)
        self.assertEqual(self.path.read_bytes(),before)

    def test_corrupt_memory_is_never_silently_overwritten(self):
        self.path.write_text('{bad JSON',encoding='utf-8'); before=self.path.read_bytes()
        with self.assertRaises(ValueError):ensure_client('Client C',self.path)
        self.assertEqual(self.path.read_bytes(),before)

    def test_storage_excludes_survey_values_and_unknown_fields(self):
        original=[row()]; changed=deepcopy(original); changed[0]['Selected metrics']=['Mean']
        candidate=teaching_candidates(original,changed)[0]
        candidate['consumer_values']=[99,12,23]
        teach(self.cid,[candidate],'x',self.path)
        text=self.path.read_text(encoding='utf-8')
        self.assertNotIn('consumer_values',text); self.assertNotIn('Available metric list',text)

    def test_identical_wide_recipes_with_extra_aggregates_are_deduplicated(self):
        original=[row(),row('Q-2-Softness',metrics=METRICS+['Bottom Box'])]
        changed=deepcopy(original)
        for r in changed:r['Selected metrics']=['Mean']
        candidates=teaching_candidates(original,changed)
        for c in candidates:c['scope']=SCOPES[1]
        self.assertEqual(teach(self.cid,candidates,'x',self.path),1)

    def test_same_vocabulary_from_different_batteries_is_one_habit(self):
        for number,items in [(2,('Soft','Smooth','Silky')),(3,('Velvet','Creamy','Rich'))]:
            original=battery(number=number,items=items); accept_suggestion(original,suggest_groups(original)[0])
            changed=deepcopy(original)
            for r in changed:r['Display label']='Skin feel'
            rules=self.learn(original,changed,kind='group',project=str(number))
        self.assertEqual(len(rules),1); self.assertEqual(len(rules[0]['evidence']),2)
        target=battery(number=9,items=('A','B','C')); accept_suggestion(target,suggest_groups(target)[0])
        self.assertEqual(len(memory_suggestions(target,target,rules)[0]),1)

    def test_item_rename_and_group_application_preserve_both_decisions(self):
        original=battery(); changed=deepcopy(original)
        accept_suggestion(changed,suggest_groups(original)[0],'Skin feel')
        changed[0]['Metric label']='Client soft label'
        candidates=teaching_candidates(original,changed)
        teach(self.cid,candidates,'x',self.path)
        rules=load_memories(self.path)['clients'][self.cid]['rules']
        target=battery(number=88)
        proposals,_,_=memory_suggestions(target,target,rules)
        self.assertEqual(len(proposals),2)
        result=apply_suggestions(target,proposals,[p['id'] for p in proposals])
        self.assertEqual(result[0]['Metric label'],'Client soft label')
        self.assertEqual(result[0]['Display label'],'Skin feel')

    def test_keep_choice_on_group_item_is_not_written_into_its_label(self):
        original=battery(); accept_suggestion(original,suggest_groups(original)[0])
        changed=deepcopy(original); changed[0]['Keep']=False
        rules=self.learn(original,changed,kind='question')
        proposals,_,_=memory_suggestions(original,original,rules)
        result=apply_suggestions(original,proposals,[p['id'] for p in proposals])
        self.assertFalse(result[0]['Keep']); self.assertEqual(result[0]['Metric label'],'Soft')

    def test_unselected_metric_renaming_is_explained(self):
        original=[row(selected=['Top 2 Boxes'])]; changed=deepcopy(original)
        changed[0]['Metric labels']={'Mean':'Average'}
        rules=self.learn(original,changed)
        proposals,_,_=memory_suggestions(original,original,rules)
        self.assertEqual(proposals[0]['renamings'],{'Mean':'Average'})

    def test_memory_refusal_does_not_hide_profile_protected_group(self):
        original=battery(); changed=deepcopy(original); dismiss_suggestion(changed,suggest_groups(original)[0])
        rules=self.learn(original,changed,kind='group')
        self.assertEqual(memory_suggestions(original,original,rules,[original[0]['Question ID']])[2],set())

    def test_failed_atomic_replace_preserves_original_memory(self):
        before=self.path.read_bytes()
        with patch('templyfier.client_memory.os.replace',side_effect=PermissionError('read only')):
            with self.assertRaises(PermissionError):ensure_client('Client C',self.path)
        self.assertEqual(self.path.read_bytes(),before)

    def test_reserved_client_names_are_rejected(self):
        for name in ('sans mémoire client',' NOUVEAU CLIENT… ',''):
            with self.assertRaises(ValueError):ensure_client(name,self.path)

    def test_invalid_selection_cannot_apply_unreviewed_suggestions(self):
        for ids in ([],['unknown']):
            with self.assertRaises(ValueError):apply_suggestions([row()],[],ids)

    def test_scale_recipe_does_not_override_current_cmi_type_change(self):
        original=[row()]; changed=deepcopy(original); changed[0]['Selected metrics']=['Mean']
        rules=self.learn(original,changed,SCOPES[1])
        current=deepcopy(original); current[0]['Type']='Listing'
        self.assertEqual(memory_suggestions(original,current,rules)[0],[])

    def test_structural_refusal_respects_section_while_vocabulary_can_cross_it(self):
        original=battery(); changed=deepcopy(original); dismiss_suggestion(changed,suggest_groups(original)[0])
        rules=self.learn(original,changed,kind='group')
        target=battery(number=88)
        for r in target:r['Section']='A different moment'
        self.assertEqual(memory_suggestions(target,target,rules)[2],set())
        original=battery(); accept_suggestion(original,suggest_groups(original)[0])
        changed=deepcopy(original)
        for r in changed:r['Display label']='Skin feel'
        rules=self.learn(original,changed,kind='group')
        accept_suggestion(target,suggest_groups(target)[0])
        self.assertEqual(len(memory_suggestions(target,target,rules)[0]),1)

    def test_group_with_different_scales_keeps_each_items_metrics(self):
        original=battery()
        original[0].update({'Type':'Standard','Available metric list':METRICS,'Selected metrics':['Mean']})
        for r in original[1:]:
            r.update({'Type':'Standard','Available metric list':['1-Never','2-Rarely','3-Sometimes','4-Often','5-Always','Mean','Top Box'],'Selected metrics':['Top Box']})
        changed=deepcopy(original); accept_suggestion(changed,suggest_groups(original)[0],'Skin feel')
        rules=self.learn(original,changed,kind='group')
        proposals,_,_=memory_suggestions(original,original,rules)
        result=apply_suggestions(original,proposals,[p['id'] for p in proposals])
        self.assertEqual([r['Selected metrics'] for r in result],[['Mean'],['Top Box'],['Top Box']])

    def test_concordant_overlapping_batteries_offer_one_group_suggestion(self):
        for number,items in [(3,('Soft','Smooth','Silky','Velvet')),(7,('Soft','Smooth','Silky','Velvet','Rich'))]:
            original=battery(number=number,items=items); changed=deepcopy(original)
            accept_suggestion(changed,suggest_groups(original)[0],'Skin feel')
            rules=self.learn(original,changed,kind='group',project=str(number))
        target=battery(number=99,items=('Soft','Smooth','Silky','Velvet','Rich'))
        proposals,omissions,_=memory_suggestions(target,target,rules)
        self.assertEqual(len(proposals),1); self.assertEqual(omissions,[])

    def test_conflicting_overlapping_battery_names_require_review(self):
        for number,items,name in [(3,('Soft','Smooth','Silky','Velvet'),'Skin feel'),(7,('Soft','Smooth','Silky','Velvet','Rich'),'Texture feel')]:
            original=battery(number=number,items=items); changed=deepcopy(original)
            accept_suggestion(changed,suggest_groups(original)[0],name)
            rules=self.learn(original,changed,kind='group',project=str(number))
        target=battery(number=99,items=('Soft','Smooth','Silky','Velvet','Rich'))
        proposals,omissions,_=memory_suggestions(target,target,rules)
        self.assertEqual(proposals,[]); self.assertTrue(omissions)


if __name__=='__main__':unittest.main()
