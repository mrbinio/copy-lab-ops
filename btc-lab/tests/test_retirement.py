import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from lab.core import Store, simulate_fill
from lab.worker import Worker

class RetirementTests(unittest.TestCase):
    def test_btc_retired_before_signal_evaluation(self):
        with tempfile.TemporaryDirectory() as d:
            worker=Worker(Store(Path(d)/'lab.db'),d)
            with patch('lab.worker.choose',side_effect=AssertionError('must not evaluate')):
                self.assertEqual(worker.choose_entry('late-v1',{},None,{},200),(None,'STRATEGY_RETIRED'))

    def test_eth_and_other_baselines_unchanged_and_pause_respected(self):
        with tempfile.TemporaryDirectory() as d:
            for asset,strategy,expected in [('BTC','mid-window-v1','mid-window-v1'),('BTC','early-v1','early-v1'),('ETH','eth-mid-window-v1','mid-window-v1')]:
                worker=Worker(Store(Path(d)/(asset+'.db'),asset=asset),d)
                with patch('lab.worker.choose',return_value=(None,'TEST')) as choose:
                    worker.choose_entry(strategy,{},None,{},200)
                    self.assertEqual(choose.call_args.args[0],expected)
                    choose.reset_mock()
                    self.assertEqual(worker.choose_entry(strategy,{},None,{},200,True),(None,'MANUAL_PAUSE'))
                    choose.assert_not_called()

    def test_retirement_preserves_open_position_and_official_loss(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'lab.db'
            store=Store(path)
            fill=simulate_fill([['.6','100']],'5','.6','.07','5','.01')
            self.assertEqual(store.open('mid-window-v1','m','Up',fill,{},1000),'FILLED')
            worker=Worker(Store(path),d)
            with store.connect() as db:
                self.assertEqual(db.execute('SELECT status FROM positions').fetchone()[0],'OPEN')
            store.resolve('m','Down',{'source':'clob_official_winner','closed':True},1900)
            store.redeem(2201)
            store.audit()
            a=next(a for a in store.snapshot()['accounts'] if a['id']=='mid-window-v1')
            self.assertEqual(a['trades'],1)
            self.assertEqual(a['pnl'],-(fill['cost']+fill['fee'])/1e6)
            self.assertIn('stop 10%',a['name'])
