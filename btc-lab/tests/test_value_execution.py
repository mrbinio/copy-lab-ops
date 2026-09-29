import tempfile
import unittest
from pathlib import Path
from lab.core import Store
from lab.value_execution import ValueExecution,KEY

class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/'lab.sqlite');self.e=ValueExecution(self.store)
        self.m=dict(slug='btc-updown-15m-1000',start=1000,end=1900,rule_hash='r',reference_topic='twap',rule_supported=True,fee_verified=True,accepting=True,fee_rate=.07)
        self.tick(1180)
        self.research(1180)
    def tick(self,now,bid='.59',ask='.60',depth='100',minimum=1):
        self.now=now;self.ref=dict(source_ts=now,topic='twap')
        self.m['books']={side:dict(source_ts=now,received_at=now,bids=[[bid,depth]],asks=[[ask,depth]],tick='.01',min_shares=minimum) for side in ['Up','Down']}
    def research(self,now,high=.9):
        self.store.set('opportunity_research',dict(status='ESTIMATED_UNVALIDATED',market=self.m['slug'],rule_hash='r',updated_at=now,model_id='frozen',training_cutoff=1000,candidates={'Up':dict(reason='RESEARCH_BUY_CANDIDATE',conservative_edge_per_share=.15,max_price=.61,all_in_budget_usd=1,probability_high=high)}))
    def step(self,allowed=True):self.e.step(self.m,self.ref,self.now,allowed)
    def state(self):return self.store.get(KEY)
    def buy(self):
        self.step();self.tick(1182);self.step()
        self.assertEqual(self.state()['status'],'BOUGHT_PAPER')
    def test_delayed_entry_restart_sell_both_fees(self):
        baseline=self.store.snapshot()['accounts']
        self.step();self.assertEqual(self.state()['trades'],0)
        self.e=ValueExecution(self.store);self.tick(1182);self.step()
        self.assertEqual(self.state()['trades'],1)
        t=self.state()['recent_trades'][0];self.assertLessEqual(t['cost']+t['fee'],1_000_000)
        self.tick(1184,bid='.96',ask='.97');self.research(1184,high=.85);self.step()
        self.assertEqual(self.state()['status'],'SELL_PENDING')
        self.tick(1186,bid='.96',ask='.97');self.step()
        s=self.state();t=s['recent_trades'][0]
        self.assertEqual(t['status'],'CLOSED');self.assertGreater(t['exit_fee'],0)
        self.assertEqual(t['pnl_micro'],t['payout']-t['cost']-t['fee']-t['exit_fee'])
        self.assertAlmostEqual(s['cash_usd'],100+s['net_pnl_usd'])
        self.assertEqual(self.store.snapshot()['accounts'][:4],baseline)
        self.assertEqual(self.store.snapshot()['accounts'][-1]['initial'],100)
    def test_minimum_not_rounded_up(self):
        self.step();self.tick(1182,minimum=5);self.step()
        self.assertEqual(self.state()['trades'],0)
        self.assertEqual(self.state()['cash_usd'],100)
    def test_same_source_and_expired_quotes_rejected(self):
        self.step();self.tick(1182);self.m['books']['Up']['source_ts']=1180;self.step()
        self.assertEqual(self.state()['status'],'ARRIVAL_REJECTED')
        self.research(1182);self.step();self.tick(1190);self.step()
        self.assertEqual(self.state()['trades'],0)
    def test_no_sale_depth_holds_then_official_loss_once(self):
        self.buy();self.tick(1184,bid='.96',ask='.97');self.research(1184,high=.85);self.step()
        self.tick(1186,bid='.96',ask='.97',depth='.1');self.step()
        self.assertEqual(self.state()['status'],'SELL_NO_FULL_FILL')
        with self.store.connect() as db:db.execute('INSERT INTO labels VALUES (?,?,?,?)',(self.m['slug'],'Down',1901,'{}'))
        self.e.settle(1902);s=self.state();self.assertEqual(s['closed'],1);self.assertLess(s['net_pnl_usd'],0)
        self.e.settle(1910);self.assertEqual(self.state()['cash_usd'],s['cash_usd'])
    def test_pause_and_duplicate(self):
        self.step(False);self.assertIsNone(self.state()['pending'])
        self.buy();self.research(1182);self.step();self.assertEqual(self.state()['trades'],1)
    def test_rule_change_rejected(self):
        self.step();self.tick(1182);self.m['rule_hash']='changed';self.step()
        self.assertEqual(self.state()['trades'],0)
    def test_limits_enforced(self):
        self.assertFalse(self.e._risk({'cash_micro':100_000_000},[],1_000_001,1180))
        losses=[{'status':'CLOSED','pnl_micro':-2_500_000,'closed_at':1170}]
        self.assertFalse(self.e._risk({'cash_micro':97_500_000},losses,975_000,1180))
    def test_daily_export_separates_lifetime_and_period(self):
        from lab.daily_report import build_report
        self.buy()
        with self.store.connect() as db:db.execute('INSERT INTO labels VALUES (?,?,?,?)',(self.m['slug'],'Up',1901,'{}'))
        self.e.settle(1902)
        today=build_report(self.store,day='1970-01-01',now=1800000000)
        later=build_report(self.store,day='1970-01-02',now=1800000000)
        self.assertEqual(today['value_surface_daily']['closed'],1)
        self.assertEqual(later['value_surface_daily']['closed'],0)
        self.assertEqual(today['value_surface_execution_cumulative']['closed'],1)
        self.assertEqual(later['value_surface_execution_cumulative']['closed'],1)
