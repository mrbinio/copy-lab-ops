import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from lab.core import Store
from lab.research import train


class ModelFreezeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'lab.sqlite'
        self.store=Store(self.path)
        self.store.set('market',{'feature_schema':'twap60-v1'})

    def seed(self):
        with self.store.connect() as db:
            for i in range(201):
                db.execute('INSERT INTO examples VALUES (?,?,?)',(str(i),i,json.dumps({
                    'features':[1,0,0,120/900],'feature_schema':'twap60-v1','book_probability':.5})))
                if i:
                    db.execute('INSERT INTO labels VALUES (?,?,?,?)',(str(i),'Up',300,'{}'))

    def test_late_label_does_not_retrain_after_restart_or_schema_switch(self):
        self.seed()
        with patch('lab.research.fit',return_value=[1,0,0,0]):
            initial=train(self.store)
        self.assertEqual(initial['status'],'PAPER_CANDIDATE')
        self.assertEqual(initial['training_membership'][0]['market'],'1')
        with self.store.connect() as db:
            db.execute('INSERT INTO labels VALUES (?,?,?,?)',('0','Down',400,'{}'))
        restarted=Store(self.path)
        with patch('lab.research.fit',side_effect=AssertionError('Unexpected retraining')):
            self.assertEqual(train(restarted),initial)
            restarted.set('market',{'feature_schema':'spot-v1'})
            self.assertEqual(train(restarted)['status'],'COLLECTING')
            restarted.set('market',{'feature_schema':'twap60-v1'})
            self.assertEqual(train(restarted),initial)

    def test_failed_validation_also_stays_frozen(self):
        self.seed()
        with patch('lab.research.fit',return_value=[-1,0,0,0]):
            initial=train(self.store)
        self.assertEqual(initial['status'],'VALIDATION_FAILED')
        with patch('lab.research.fit',side_effect=AssertionError('Unexpected retry')):
            self.assertEqual(train(self.store),initial)

    def test_legacy_model_preserved_without_fabricating_membership(self):
        legacy={'status':'PAPER_CANDIDATE','feature_schema':'twap60-v1','weights':[1,0,0,0],
                'model_id':'legacy','trained_at':123,'samples':200}
        self.store.set('model',legacy)
        with patch('lab.research.fit',side_effect=AssertionError('Unexpected migration training')):
            result=train(self.store)
        for key,value in legacy.items():self.assertEqual(result[key],value)
        self.assertNotIn('training_membership',result)
        self.assertIn('unavailable',result['freeze_provenance'])

    def test_insufficient_data_remains_collecting(self):
        result=train(self.store)
        self.assertEqual(result['status'],'COLLECTING')
        self.assertIsNone(self.store.get('frozen_model:twap60-v1'))
