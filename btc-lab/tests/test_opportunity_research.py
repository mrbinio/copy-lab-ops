import tempfile
import unittest
from pathlib import Path
from lab.core import Store
from lab.opportunity_research import OpportunityResearch,value_decision,wilson
from lab.wallet_observer import WalletObserver,WALLETS

class ValueTests(unittest.TestCase):
    def test_costs_and_minimum(self):
        self.assertEqual(value_decision(.7,.8,.7,.69,.07,5)['reason'],'NO_NET_EDGE')
        self.assertEqual(value_decision(.9,.95,.6,.59,.07,5)['reason'],'MINIMUM_EXCEEDS_BUDGET')
        r=value_decision(.9,.95,.6,.59,.07,1)
        self.assertLessEqual(r['all_in_budget_usd'],1)
        self.assertFalse(r['executable'])
    def test_exit_requires_upper_bound(self):
        self.assertEqual(value_decision(.4,.5,.7,.69,.07,1)['exit_assessment'],'SELL_VALUE_EXCEEDS_HOLD')
    def test_uncertainty(self):
        self.assertEqual(wilson(0,0),(0,1))
        self.assertLess(wilson(8,10)[0],.8)
    def test_no_future_labels(self):
        with tempfile.TemporaryDirectory() as d:
            st=Store(Path(d)/'lab.sqlite');o=OpportunityResearch(st)
            with st.connect() as db:
                for i in range(50):
                    db.execute('INSERT INTO opportunity_samples VALUES (?,?,?,?,?)',(str(i),3,1,500,'{"rule_hash":"rule"}'))
                    db.execute('INSERT INTO labels VALUES (?,?,?,?)',(str(i),'Up',2000,'{}'))
            b=dict(asks=[['.60','100']],bids=[['.59','100']],source_ts=1180,received_at=1180,min_shares=5)
            m=dict(slug='current',rule_hash='rule',start=1000,rule_supported=True,fee_verified=True,accepting=True,features=[1,1.5],books={'Up':b,'Down':b},reference_topic='x',fee_rate=.07)
            o.step(m,{'source_ts':1180,'topic':'x'},1180)
            self.assertEqual(st.get('opportunity_research')['training_windows'],0)
            o.step(m,{'source_ts':1180,'topic':'x'},1181)
            with st.connect() as db:self.assertEqual(db.execute("SELECT COUNT(*) FROM opportunity_samples WHERE market='current'").fetchone()[0],1)

    def test_prior_labels_and_rule_isolation(self):
        with tempfile.TemporaryDirectory() as d:
            st=Store(Path(d)/'lab.sqlite');o=OpportunityResearch(st)
            with st.connect() as db:
                for i in range(50):
                    db.execute('INSERT INTO opportunity_samples VALUES (?,?,?,?,?)',(str(i),3,1,500,'{"rule_hash":"rule"}'))
                    db.execute('INSERT INTO labels VALUES (?,?,?,?)',(str(i),'Up',900,'{}'))
            b=dict(asks=[['.60','100']],bids=[['.59','100']],source_ts=1180,received_at=1180,min_shares=1)
            m=dict(slug='current',rule_hash='rule',start=1000,rule_supported=True,fee_verified=True,accepting=True,features=[1,1.5],books={'Up':b,'Down':b},reference_topic='x',fee_rate=.07)
            o.step(m,{'source_ts':1180,'topic':'x'},1180)
            self.assertEqual(st.get('opportunity_research')['training_windows'],50)
            self.assertIn('Up',st.get('opportunity_research')['candidates'])
            m['slug']='different';m['rule_hash']='changed'
            o.step(m,{'source_ts':1180,'topic':'x'},1180)
            self.assertEqual(st.get('opportunity_research')['training_windows'],0)

class WalletTests(unittest.IsolatedAsyncioTestCase):
    async def test_poll_empty_keeps_running_and_error_not_empty(self):
        with tempfile.TemporaryDirectory() as d:
            st=Store(Path(d)/'lab.sqlite');o=WalletObserver(st,lambda url:[])
            await o.poll(WALLETS[0]);self.assertEqual(st.get('wallet_observer:'+WALLETS[0])['status'],'POLL_OK')
            def fail(url):raise RuntimeError('403')
            o.fetch=fail
            await o.poll(WALLETS[0]);self.assertEqual(st.get('wallet_observer:'+WALLETS[0])['status'],'ERROR')
    async def test_dedup_restart_and_wallet_validation(self):
        with tempfile.TemporaryDirectory() as d:
            st=Store(Path(d)/'lab.sqlite');o=WalletObserver(st,lambda url:[])
            r=dict(proxyWallet=WALLETS[0],timestamp=100,transactionHash='abc',type='TRADE',side='BUY',size=3)
            self.assertEqual(o.ingest(WALLETS[0],[r],110),1)
            self.assertEqual(WalletObserver(st,None).ingest(WALLETS[0],[r],120),0)
            with self.assertRaises(ValueError):o.ingest(WALLETS[1],[r],120)
            with st.connect() as db:self.assertEqual(db.execute('SELECT first_seen FROM wallet_activity').fetchone()[0],110)

    async def test_page_limit_never_claims_complete(self):
        with tempfile.TemporaryDirectory() as d:
            st=Store(Path(d)/'lab.sqlite')
            import time
            r=dict(proxyWallet=WALLETS[0],timestamp=int(time.time())-2,transactionHash='abc',type='TRADE')
            o=WalletObserver(st,lambda url:{'data':[r]*500,'pagination':{'has_more':True,'next_cursor':'more'}})
            await o.poll(WALLETS[0])
            self.assertEqual(st.get('wallet_observer:'+WALLETS[0])['status'],'INCOMPLETE_PAGE_LIMIT')
            self.assertFalse(st.get('wallet_observer:'+WALLETS[0])['history_complete'])
