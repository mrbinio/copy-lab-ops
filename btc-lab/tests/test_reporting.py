import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from lab.core import Store

spec=importlib.util.spec_from_file_location('reporter',Path(__file__).parents[1]/'deploy/publish_report_macos.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)

class ReportingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);(self.root/'data').mkdir()
        self.store=Store(self.root/'data/lab.sqlite')
        self.store.set('worker',{'heartbeat':100,'status':'RECORDING','secret':'DO_NOT_EXPORT'})
        self.store.record('private',{'secret':'DO_NOT_EXPORT'})

    def test_readonly_and_allowlist_and_stale_heartbeat(self):
        with self.store.connect() as db:before=list(db.iterdump())
        with patch.object(r.time,'time',return_value=200):result=r.snapshot(self.root)
        self.assertEqual(result['heartbeat_age_seconds'],100)
        self.assertNotIn('DO_NOT_EXPORT',json.dumps(result))
        self.assertEqual(len(result['accounts']),3)
        with self.store.connect() as db:self.assertEqual(before,list(db.iterdump()))

    def test_public_destination_rejected_before_reading_db(self):
        with patch.object(r,'api',return_value={'private':False,'full_name':r.REPO}) as call:
            with self.assertRaises(RuntimeError):r.publish(self.root,'secret')
        self.assertEqual(call.call_count,1)

    def test_private_upload_uses_sha_without_token_in_report(self):
        with patch.object(r,'api',side_effect=[{'private':True,'full_name':r.REPO,'default_branch':'main'}, {'sha':'old'},{}]) as call:
            r.publish(self.root,'TOKEN_SECRET')
        body=call.call_args.args[2]
        self.assertEqual(body['sha'],'old')
        self.assertNotIn(b'TOKEN_SECRET',r.base64.b64decode(body['content']))

    def test_auth_error_does_not_attempt_put(self):
        error=r.urllib.error.HTTPError('https://api.github.com',401,'Unauthorized',{},None)
        with patch.object(r,'api',side_effect=error) as call:
            with self.assertRaises(r.urllib.error.HTTPError):r.publish(self.root,'secret')
        self.assertEqual(call.call_count,1)
