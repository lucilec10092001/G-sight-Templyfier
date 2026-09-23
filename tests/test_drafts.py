from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4
from templyfier import drafts, server_storage as storage
from purge_expired_drafts import purge_expired


def bundle():
    return drafts.make_bundle({'version':1,'settings':{'include_deltas':False},'questions':[{'Question ID':'Q-1','Keep':True,'Order':1,'Selected metrics':['Moyenne'],'Metric labels':{'Moyenne':'Mean'}}]},drafts.fingerprints([('test.xlsx',b'raw-not-stored')]),{'test.xlsx':'TOTAL'})


class DraftTests(unittest.TestCase):
    def setUp(self):
        self.db=Path(__file__).resolve().parents[2]/f'draft_test_{uuid4().hex}.sqlite3'
        self.env=patch.dict(os.environ,{'TEMPLYFIER_MODE':'server','TEMPLYFIER_DRAFT_RETENTION_DAYS':'30'});self.env.start()
        self.path=patch.object(storage,'database_path',return_value=self.db);self.path.start()
        storage.bind_identity(storage.Identity('alice'));storage.select_library('personal')
    def tearDown(self):
        storage.bind_identity(None);self.path.stop();self.env.stop()
        for suffix in ('','-journal'):
            p=Path(str(self.db)+suffix)
            if p.exists():p.unlink()
    def expire(self):
        def change(document):
            for item in document['drafts'].values():item['expires']=(datetime.now(timezone.utc)-timedelta(days=1)).isoformat()
            return document,None
        storage.mutate_document('drafts',drafts.DEFAULT,'qa_expire',change)
    def test_fingerprints_match_exact_bytes_and_reordered_sources(self):
        a=drafts.fingerprints([('b',b'2'),('a',b'1')],('cmr',b'3'))
        b=drafts.make_bundle(bundle()['profile'],a,{})
        self.assertTrue(drafts.matches(b,drafts.fingerprints([('a',b'1'),('b',b'2')],('cmr',b'3'))))
        self.assertFalse(drafts.matches(b,drafts.fingerprints([('a',b'changed'),('b',b'2')],('cmr',b'3'))))
        self.assertFalse(drafts.matches(b,drafts.fingerprints([('a',b'1'),('b',b'2')])))
    def test_settings_roundtrip_no_raw_bytes(self):
        identifier,record=drafts.save_draft('Project',bundle())
        self.assertEqual(drafts.list_drafts()[identifier],record)
        self.assertNotIn('raw-not-stored',json.dumps(storage.read_document('drafts',drafts.DEFAULT)))
    def test_extra_payload_and_scores_rejected(self):
        for target in ('root','profile','settings','row'):
            b=bundle();holder={'root':b,'profile':b['profile'],'settings':b['profile']['settings'],'row':b['profile']['questions'][0]}[target]
            holder['scores']=[99]
            with self.assertRaises(ValueError):drafts.save_draft('Unsafe',b)
        b=bundle();b['profile']['settings']['benchmark_labels']=[{'score':99}]
        with self.assertRaises(ValueError):drafts.validate_bundle(b)
        b=bundle();b['profile']['questions'][0]['Metric labels']['Moyenne']=99
        with self.assertRaises(ValueError):drafts.validate_bundle(b)
        b=bundle();b['profile']['questions'][0]['Top Box']=.99
        with self.assertRaises(ValueError):drafts.validate_bundle(b)
        for key,value in [('mean_decimals',99),('test_type','Unknown'),('benchmark_keys',['A','A'])]:
            b=bundle();b['profile']['settings'][key]=value
            with self.assertRaises(ValueError):drafts.validate_bundle(b)
    def test_personal_isolation_even_team_library(self):
        identifier,_=drafts.save_draft('Private',bundle());storage.select_library('team')
        self.assertIn(identifier,drafts.list_drafts())
        storage.bind_identity(storage.Identity('bob'));self.assertEqual(drafts.list_drafts(),{})
        storage.bind_identity(storage.Identity('alice'));self.assertIn(identifier,drafts.list_drafts())
    def test_unauthenticated_rejected(self):
        storage.bind_identity(None)
        with self.assertRaises(ValueError):drafts.save_draft('Private',bundle())
        self.assertFalse(self.db.exists())
    def test_retention_disabled_invalid_and_bounds(self):
        for value in ('','0','366','abc'):
            with patch.dict(os.environ,{'TEMPLYFIER_DRAFT_RETENTION_DAYS':value}):
                with self.assertRaises(ValueError):drafts.save_draft('Private',bundle())
        for value in ('1','365'):
            with patch.dict(os.environ,{'TEMPLYFIER_DRAFT_RETENTION_DAYS':value}):self.assertEqual(drafts.retention_days(),int(value))
    def test_stale_update_and_delete_do_not_overwrite(self):
        identifier,record=drafts.save_draft('First',bundle())
        _,updated=drafts.save_draft('Updated',bundle(),identifier,record['token'])
        with self.assertRaises(ValueError):drafts.save_draft('Stale',bundle(),identifier,record['token'])
        with self.assertRaises(ValueError):drafts.delete_draft(identifier,record['token'])
        self.assertEqual(drafts.list_drafts()[identifier]['name'],'Updated')
        drafts.delete_draft(identifier,updated['token']);self.assertEqual(drafts.list_drafts(),{})
    def test_expiry_removes_records_on_read(self):
        drafts.save_draft('Expired',bundle());self.expire()
        self.assertEqual(drafts.list_drafts(),{})
        self.assertEqual(storage.read_document('drafts',drafts.DEFAULT)['drafts'],{})
    def test_it_purge_removes_other_users_expired_drafts_only(self):
        drafts.save_draft('Expired',bundle());self.expire()
        storage.bind_identity(storage.Identity('bob'));identifier,_=drafts.save_draft('Active',bundle())
        self.assertEqual(purge_expired(),1);self.assertIn(identifier,drafts.list_drafts())
        storage.bind_identity(storage.Identity('alice'));self.assertEqual(drafts.list_drafts(),{})
    def test_corrupt_dates_fail_without_overwrite(self):
        drafts.save_draft('Original',bundle())
        def corrupt(document):
            next(iter(document['drafts'].values()))['expires']='2026-01-01'
            return document,None
        storage.mutate_document('drafts',drafts.DEFAULT,'qa_corrupt',corrupt)
        original=storage.read_document('drafts',drafts.DEFAULT)
        with self.assertRaises(ValueError):drafts.save_draft('New',bundle())
        with self.assertRaises(ValueError):purge_expired()
        self.assertEqual(storage.read_document('drafts',drafts.DEFAULT),original)
    def test_twenty_draft_limit_and_name_validation(self):
        for n in range(20):drafts.save_draft(str(n),bundle())
        with self.assertRaises(ValueError):drafts.save_draft('21',bundle())
        for name in (' ','a'*101):
            with self.assertRaises(ValueError):drafts.save_draft(name,bundle())
