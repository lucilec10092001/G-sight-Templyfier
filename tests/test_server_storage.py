from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from copy import deepcopy
import json
import multiprocessing
import os
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch
from uuid import uuid4

from templyfier import server_storage as storage
from templyfier.client_memory import (client_token, delete_rules, ensure_client,
    load_memories, teach, teaching_candidates, import_client_memory)
from templyfier.preferences import (delete_cmi_profile, mark_onboarding_seen,
    read_preferences, save_cmi_profile, saved_cmi_profiles)
from templyfier.configuration_report import configuration_report
from .test_client_memory import row
from backup_server_memory import backup_database


def process_writer(db, identity, prefix):
    with patch.dict(os.environ, {'TEMPLYFIER_MODE':'server'}), patch.object(storage, 'database_path', return_value=Path(db)):
        storage.bind_identity(storage.Identity(identity))
        for i in range(6):
            ensure_client(f'{prefix} {i}')


class ServerStorageTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(__file__).resolve().parents[2]
        self.db = self.folder / f'qa_server_{uuid4().hex}.sqlite3'
        self.environ = patch.dict(os.environ, {'TEMPLYFIER_MODE':'server', 'TEMPLYFIER_DATA_DIR':str(self.folder),
            'TEMPLYFIER_OIDC_ISSUER':'https://internal.example/tenant', 'TEMPLYFIER_ALLOWED_USERS':'', 'TEMPLYFIER_ADMINS':''})
        self.environ.start()
        self.path_patch = patch.object(storage, 'database_path', return_value=self.db)
        self.path_patch.start()
        storage.bind_identity(storage.Identity('cmia'))

    def tearDown(self):
        storage.bind_identity(None)
        self.path_patch.stop()
        self.environ.stop()
        for suffix in ('', '-journal'):
            target = Path(str(self.db)+suffix)
            if target.exists():
                target.unlink()

    def candidates(self):
        baseline = [row()]
        changed = deepcopy(baseline)
        changed[0]['Selected metrics'] = ['Top 3 Boxes']
        return teaching_candidates(baseline,changed)

    def test_personal_memories_and_profiles_are_isolated(self):
        ensure_client('Alpha')
        save_cmi_profile('Vague A', {'questions':[]})
        storage.bind_identity(storage.Identity('cmib'))
        self.assertEqual(load_memories()['clients'], {})
        self.assertEqual(saved_cmi_profiles(), {})
        ensure_client('Beta')
        storage.bind_identity(storage.Identity('cmia'))
        self.assertEqual(set(load_memories()['clients']), {'alpha'})
        self.assertEqual(set(saved_cmi_profiles()), {'Vague A'})

    def test_anonymous_access_fails_before_database_creation(self):
        storage.bind_identity(None)
        for operation in (load_memories, lambda:ensure_client('Alpha'), read_preferences):
            with self.assertRaises(ValueError): operation()
        self.assertFalse(self.db.exists())

    def test_team_read_is_shared_and_writes_are_admin_only(self):
        storage.bind_identity(storage.Identity('ref',True))
        storage.select_library('team')
        cid = ensure_client('Alpha')
        token = client_token(load_memories()['clients'][cid])
        teach(cid,self.candidates(),'project',expected=token)
        storage.bind_identity(storage.Identity('cmia'))
        storage.select_library('team')
        self.assertEqual(len(load_memories()['clients'][cid]['rules']),1)
        expected = client_token(load_memories()['clients'][cid])
        for operation in (lambda:ensure_client('Beta'), lambda:teach(cid,self.candidates(),'other',expected=expected), lambda:delete_rules(cid,expected=expected)):
            with self.assertRaises(ValueError): operation()
        self.assertEqual(len(load_memories()['clients'][cid]['rules']),1)

    def test_personal_profiles_do_not_become_team_profiles(self):
        storage.select_library('team')
        save_cmi_profile('Personal',{'settings':{}})
        storage.select_library('personal')
        self.assertIn('Personal',saved_cmi_profiles())
        storage.bind_identity(storage.Identity('other'))
        storage.select_library('team')
        self.assertEqual(saved_cmi_profiles(),{})

    def test_memory_survives_connections_and_identity_rebinding(self):
        cid=ensure_client('Alpha')
        teach(cid,self.candidates(),'project',expected=client_token(load_memories()['clients'][cid]))
        storage.bind_identity(None)
        storage.bind_identity(storage.Identity('cmia'))
        self.assertEqual(load_memories()['clients'][cid]['rules'][0]['value']['selected'],['Top 3 Boxes'])

    def test_stale_teach_and_delete_never_overwrite(self):
        cid=ensure_client('Alpha')
        stale=client_token(load_memories()['clients'][cid])
        teach(cid,self.candidates(),'project',expected=stale)
        before=load_memories()
        for operation in (lambda:teach(cid,self.candidates(),'second',expected=stale),lambda:delete_rules(cid,expected=stale)):
            with self.assertRaisesRegex(ValueError,'changé'): operation()
        self.assertEqual(load_memories(),before)

    def test_server_mutations_require_read_version(self):
        cid=ensure_client('Alpha')
        for operation in (lambda:teach(cid,self.candidates(),'project'),lambda:delete_rules(cid)):
            with self.assertRaises(ValueError): operation()
        self.assertEqual(load_memories()['clients'][cid]['rules'],[])

    def test_reviewed_import_preserves_other_clients_and_requires_current_version(self):
        cid=ensure_client('Alpha')
        teach(cid,self.candidates(),'project',expected=client_token(load_memories()['clients'][cid]))
        exported=load_memories()
        storage.bind_identity(storage.Identity('cmib'))
        ensure_client('Beta')
        import_client_memory(exported,cid,'absent')
        self.assertEqual(set(load_memories()['clients']),{'alpha','beta'})
        before=load_memories()
        with self.assertRaises(ValueError): import_client_memory(exported,cid,'absent')
        self.assertEqual(load_memories(),before)

    def test_import_into_team_is_blocked_for_regular_cmi(self):
        cid=ensure_client('Alpha')
        exported=load_memories()
        storage.select_library('team')
        with self.assertRaises(ValueError): import_client_memory(exported,cid,'absent')
        self.assertEqual(load_memories()['clients'],{})

    def test_invalid_import_does_not_change_existing_memory(self):
        cid=ensure_client('Alpha')
        before=load_memories()
        with self.assertRaises(ValueError): import_client_memory({'version':99,'clients':{}},cid,'absent')
        self.assertEqual(load_memories(),before)

    def test_other_client_update_does_not_conflict(self):
        cid=ensure_client('Alpha')
        token=client_token(load_memories()['clients'][cid])
        ensure_client('Beta')
        teach(cid,self.candidates(),'project',expected=token)
        self.assertEqual(set(load_memories()['clients']),{'alpha','beta'})

    def test_concurrent_threads_preserve_all_profiles(self):
        def writer(index):
            storage.bind_identity(storage.Identity('cmia'))
            return save_cmi_profile(f'Profile {index}',{'settings':{'index':index}})
        with ThreadPoolExecutor(max_workers=8) as executor:
            self.assertTrue(all(executor.map(writer,range(24))))
        self.assertEqual(len(saved_cmi_profiles()),24)

    def test_multiple_processes_preserve_all_clients(self):
        ensure_client('Initial')
        context=multiprocessing.get_context('spawn')
        workers=[context.Process(target=process_writer,args=(str(self.db),'cmia',prefix)) for prefix in ('A','B')]
        for process in workers: process.start()
        for process in workers:
            process.join(30)
            if process.is_alive():
                process.terminate(); process.join()
                self.fail('Writer process timed out')
            self.assertEqual(process.exitcode,0)
        self.assertEqual(len(load_memories()['clients']),13)

    def test_corrupt_payload_is_preserved(self):
        ensure_client('Alpha')
        with closing(sqlite3.connect(self.db)) as connection:
            connection.execute("UPDATE documents SET payload='invalid' WHERE name='memory'")
            connection.commit()
        for operation in (load_memories,lambda:ensure_client('Beta')):
            with self.assertRaises(ValueError): operation()
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(connection.execute("SELECT payload FROM documents WHERE name='memory'").fetchone()[0],'invalid')

    def test_unknown_database_version_is_not_reset(self):
        ensure_client('Alpha')
        with closing(sqlite3.connect(self.db)) as connection:
            connection.execute('PRAGMA user_version=99')
            connection.commit()
        with self.assertRaises(ValueError): ensure_client('Beta')
        with closing(sqlite3.connect(self.db)) as connection: self.assertEqual(connection.execute('PRAGMA user_version').fetchone()[0],99)

    def test_audit_is_metadata_only_and_admin_only(self):
        ensure_client('SensitiveClient')
        with self.assertRaises(ValueError): storage.audit_events()
        storage.bind_identity(storage.Identity('ref',True))
        events=storage.audit_events()
        self.assertEqual(events[0]['Action'],'memory:create-client')
        self.assertNotIn('SensitiveClient',json.dumps(events))
        self.assertNotIn('Question',json.dumps(events))

    def test_missing_or_wrong_oidc_access_configuration_fails_closed(self):
        claims={'iss':'https://internal.example/tenant','sub':'subject'}
        with self.assertRaises(ValueError): storage.verified_identity(claims)
        key=storage.identity_key(claims['iss'],claims['sub'])
        with patch.dict(os.environ,{'TEMPLYFIER_ALLOWED_USERS':key,'TEMPLYFIER_ADMINS':key}):
            self.assertTrue(storage.verified_identity(claims).admin)
            for wrong in ({'iss':'wrong','sub':'subject'},{'iss':claims['iss'],'sub':'other'}):
                with self.assertRaises(ValueError): storage.verified_identity(wrong)
        with patch.dict(os.environ,{'TEMPLYFIER_ALLOWED_USERS':key,'TEMPLYFIER_ADMINS':'unknown'}):
            with self.assertRaises(ValueError): storage.verified_identity(claims)

    def test_server_path_never_falls_back_or_accepts_code_or_unc(self):
        self.path_patch.stop()
        try:
            code=Path(__file__).resolve().parents[1]
            for raw in ('','relative',str(code),str(code/'templyfier'),r'\\server\share'):
                with patch.dict(os.environ,{'TEMPLYFIER_DATA_DIR':raw}):
                    with self.assertRaises(ValueError): storage.database_path()
            self.assertEqual(storage.database_path(),self.folder/'templyfier.sqlite3')
        finally: self.path_patch.start()

    def test_custom_file_paths_cannot_bypass_server_identity_or_permissions(self):
        storage.bind_identity(None)
        for operation in (lambda:load_memories(self.db),lambda:ensure_client('Alpha',self.db),lambda:save_cmi_profile('P',{},self.db)):
            with self.assertRaises(ValueError): operation()
        self.assertFalse(self.db.exists())

    def test_preference_transactions_support_delete_and_onboarding(self):
        self.assertTrue(mark_onboarding_seen())
        self.assertTrue(read_preferences()['onboarding_seen'])
        save_cmi_profile('P',{'questions':[]})
        self.assertTrue(delete_cmi_profile('P'))
        self.assertFalse(delete_cmi_profile('P'))
        self.assertTrue(read_preferences()['onboarding_seen'])

    def test_it_backup_is_consistent_and_never_overwrites(self):
        ensure_client('Alpha')
        save_cmi_profile('P',{'settings':{}})
        target=self.db.with_name(self.db.stem+'_backup.sqlite3')
        try:
            backup_database(self.db,target)
            with closing(sqlite3.connect(target)) as connection:
                self.assertEqual(connection.execute('PRAGMA integrity_check').fetchone()[0],'ok')
                self.assertEqual(connection.execute('SELECT count(*) FROM documents').fetchone()[0],2)
            with self.assertRaises(FileExistsError): backup_database(self.db,target)
            with self.assertRaises(ValueError): backup_database(self.db,self.db)
            with patch.object(storage,'database_path',return_value=target):
                self.assertEqual(set(load_memories()['clients']),{'alpha'})
                self.assertIn('P',saved_cmi_profiles())
        finally:
            if target.exists(): target.unlink()

    def test_configuration_report_records_choices_without_result_data(self):
        data=json.dumps({'settings':{'test_type':'Monadic'},'questions':[row(label='Colour | appearance',selected=['Top 3 Boxes'])]}).encode()
        report=configuration_report(data,'abc',{'name':'Alpha','expected':'v'},True).decode()
        self.assertIn('Colour \\| appearance',report)
        self.assertIn('Top 3 Boxes',report)
        self.assertIn('internal server',report)
        self.assertNotIn('Available metric list',report)


if __name__ == '__main__': unittest.main()
