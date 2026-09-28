import copy
import tempfile
import unittest
from pathlib import Path
from lab.core import Store
from lab.complete_set import CompleteSetObserver

def market(t=100,price='.45'):
    return {'slug':'btc-updown-15m-0','start':0,'end':900,'rule_supported':True,'fee_verified':True,'fee_rate':.07,'books':{s:{'asks':[[price,'20']],'bids':[['.44','20']],'tick':'.01','min_shares':'5','source_ts':t,'received_at':t} for s in ('Up','Down')}}

class ObserverTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'lab.sqlite');self.o=CompleteSetObserver(self.store)
    def tearDown(self):self.tmp.cleanup()
    def current(self):return self.store.get('complete_set_observer')['current']
    def test_quote_is_not_trade_and_delayed_books_required(self):
        self.o.step(market(),100);self.assertEqual(self.current()['positive_samples'],1)
        self.o.step(market(),100.3);self.assertEqual(self.current()['delayed_checks'],0)
        self.o.step(market(101),101);self.assertEqual(self.current()['both_available'],1)
        with self.store.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM positions').fetchone()[0],0)
    def test_orphan_and_fixed_caps(self):
        self.o.step(market(),100);m=market(101);m['books']['Down']['asks']=[['.46','20']]
        self.o.step(m,101);self.assertEqual(self.current()['one_leg_only'],1);self.assertIn('full_loss_usd',self.current()['last_orphan'])
    def test_stale_skew_rules_and_depth(self):
        for change in ('stale','skew','rule','depth'):
            m=market()
            if change=='stale':m['books']['Up']['source_ts']=98
            if change=='skew':m['books']['Down']['source_ts']=99.5
            if change=='rule':m['rule_supported']=False
            if change=='depth':m['books']['Up']['asks']=[['.45','9']]
            self.o.step(m,100);self.assertNotEqual(self.current()['status'],'POSITIVE_QUOTE_NOT_A_FILL')
    def test_fees_remove_apparent_edge(self):
        self.o.step(market(price='.49'),100);self.assertEqual(self.current()['status'],'NO_NET_EDGE')
    def test_exports_and_eth_isolation(self):
        from lab.daily_report import build_report
        import importlib.util
        root=Path(self.tmp.name)
        eth=Store(root/'data/eth/lab.sqlite',asset='ETH')
        m=market();m['slug']='eth-updown-15m-0'
        CompleteSetObserver(eth).step(m,100)
        self.assertEqual(build_report(eth,'2026-09-27',1790575416)['complete_set_observer']['asset'],'ETH')
        spec=importlib.util.spec_from_file_location('publisher',Path(__file__).parents[1]/'deploy/publish_report_macos.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        self.assertEqual(module.snapshot(root,'ETH')['complete_set_observer']['spec'],'complete-set-observer-v1')
        self.assertFalse(self.store.get('complete_set_observer'))

    def test_restart_preserves_window_not_pending(self):
        self.o.step(market(),100);self.o=CompleteSetObserver(self.store);self.o.step(market(101),101)
        self.assertEqual(self.current()['samples'],2);self.assertEqual(self.current()['delayed_checks'],0)

if __name__=='__main__':unittest.main()
