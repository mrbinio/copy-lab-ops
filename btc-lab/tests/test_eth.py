import asyncio
import base64
import hashlib
import json
import tempfile
import threading
import time
import unittest
import urllib.request
import urllib.error
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import patch,AsyncMock
from http.server import ThreadingHTTPServer
from lab.core import Store,simulate_fill
from lab.worker import Worker,normalize_market,reference_subscription
from lab.reference import TWAP_RULE,TWAP60,observation,classify_rule
from lab.server import handler
from lab.daily_report import build_report

ETH_RULE=TWAP_RULE.replace('Bitcoin','Ethereum').replace('BTC/USD','ETH/USD').replace('btc-usd','eth-usd')
def raw_market(start):
    return {'slug':f'eth-updown-15m-{start}','conditionId':'eth-condition','outcomes':['Up','Down'],'clobTokenIds':['eu','ed'],
            'description':ETH_RULE,'eventStartTime':datetime.fromtimestamp(start,timezone.utc).isoformat(),
            'endDate':datetime.fromtimestamp(start+900,timezone.utc).isoformat(),'active':True,'closed':False,
            'acceptingOrders':True,'feesEnabled':True,'feeSchedule':{'exponent':1,'rate':.07}}
def event(ts,symbol='eth/usd',price=2700):
    return {'type':'update','topic':TWAP60,'payload':{'symbol':symbol,'timestamp':int(ts*1000),'window_s':60,
            'full_accuracy_value':str(int(price*10**18))}}

class EthDataTests(unittest.TestCase):
    def test_exact_asset_rule_time_and_fee_contract(self):
        raw=raw_market(900);m=normalize_market(raw,900,'ETH')
        self.assertTrue(m['rule_supported']);self.assertTrue(m['fee_verified'])
        self.assertEqual(m['feature_schema'],'eth-twap60-v1');self.assertEqual(m['fee_rate'],.07)
        self.assertFalse(normalize_market(raw,900)['rule_supported'])
        raw['slug']='btc-updown-15m-900'
        self.assertFalse(normalize_market(raw,900,'ETH')['rule_supported'])
        raw=raw_market(900);raw['endDate']=raw['eventStartTime']
        self.assertFalse(normalize_market(raw,900,'ETH')['rule_supported'])
        self.assertIsNone(classify_rule(ETH_RULE.replace('60s','30s'),'ETH')[1])
    def test_subscription_and_parser_reject_other_asset(self):
        self.assertTrue(all(json.loads(s['filters'])=={'symbol':'eth/usd'} for s in reference_subscription('ETH')['subscriptions']))
        self.assertIsNotNone(observation(event(100),100,'ETH'))
        self.assertIsNone(observation(event(100),100,'BTC'))
        self.assertIsNone(observation(event(100,'btc/usd'),100,'ETH'))
        with self.assertRaises(ValueError):observation(event(90),101,'ETH')
    def test_opening_boundary_and_global_pause(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp)/'eth';w=Worker(Store(data/'lab.sqlite',asset='ETH'),data)
            m=normalize_market(raw_market(900),900,'ETH')
            w.accept_reference(event(901),901);w.capture_opening(m);self.assertIsNone(m['opening'])
            w.references.clear();w.accept_reference(event(900),900);w.capture_opening(m)
            self.assertEqual(m['opening'],2700)
            (Path(tmp)/'PAUSE').touch();self.assertTrue(w.is_paused())
    def test_ledger_and_reports_are_separate_after_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);btc=Store(root/'lab.sqlite');eth=Store(root/'eth/lab.sqlite',asset='ETH')
            f=simulate_fill([['.60','100']],'5','.61','.07','5','.01')
            self.assertEqual(eth.open('eth-mid-window-v1','eth-updown-15m-900','Up',f,{},1100),'FILLED')
            with self.assertRaises(ValueError):eth.open('eth-mid-window-v1','btc-updown-15m-1800','Up',f,{},2000)
            with self.assertRaises(ValueError):btc.open('eth-mid-window-v1','eth-updown-15m-900','Up',f,{},1100)
            eth=Store(root/'eth/lab.sqlite',asset='ETH');eth.audit();btc.audit()
            self.assertEqual(len(eth.snapshot()['accounts']),1);self.assertEqual(len(btc.snapshot()['accounts']),5)
            self.assertFalse(btc.snapshot()['trades'])
            report=build_report(eth,'2026-09-25');self.assertEqual(report['asset'],'ETH')
            self.assertEqual(report['experiment']['id'],'eth-mid-window-v1')
            self.assertEqual(len(report['accounts']),1)
    def test_authenticated_asset_endpoints(self):
        with tempfile.TemporaryDirectory() as tmp:
            btc=Store(Path(tmp)/'btc');eth=Store(Path(tmp)/'eth',asset='ETH')
            srv=ThreadingHTTPServer(('127.0.0.1',0),handler(btc,Path(tmp),hashlib.sha256(b'pw').hexdigest(),eth_store=eth))
            thread=threading.Thread(target=srv.serve_forever,daemon=True);thread.start()
            base=f'http://127.0.0.1:{srv.server_port}'
            auth={'Authorization':'Basic '+base64.b64encode(b'damian:pw').decode()}
            try:
                with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(base+'/api/state?asset=ETH')
                self.assertEqual(e.exception.code,401)
                for route in ('state','report?date=2026-09-25'):
                    url=base+'/api/'+route+('&' if '?' in route else '?')+'asset=ETH'
                    with urllib.request.urlopen(urllib.request.Request(url,headers=auth)) as response:
                        d=json.load(response);self.assertEqual(d['asset'],'ETH');self.assertEqual(len(d['accounts']),1)
                with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(urllib.request.Request(base+'/api/state?asset=OTHER',headers=auth))
                self.assertEqual(e.exception.code,400)
            finally:srv.shutdown();srv.server_close();thread.join()

class EthCycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_signal_delayed_entry_sale_and_no_btc_model_training(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'eth/lab.sqlite',asset='ETH');w=Worker(store,Path(tmp)/'eth')
            start=9000;now=[start+200];raw=raw_market(start)
            w.accept_reference(event(start,price=2700),start)
            w.market=normalize_market(raw,start,'ETH');w.capture_opening(w.market)
            for i in range(100):w.accept_reference(event(now[0]-99+i,price=2705+i*.01),now[0]-99+i)
            phase={'bid':'.59','ask':'.60','closed':False}
            def fetch(url):
                if '/markets/slug/' in url:
                    self.assertIn('eth-updown-15m-',url);return raw
                if '/markets/eth-condition' in url:return {'condition_id':'eth-condition','closed':phase['closed'],'tokens':[{'outcome':'Up','token_id':'eu','winner':True}]}
                token=url.split('token_id=')[1];self.assertIn(token,('eu','ed'))
                return {'asset_id':token,'timestamp':str(int(now[0]*1000)),'asks':[{'price':phase['ask'],'size':'100'}],
                        'bids':[{'price':phase['bid'],'size':'100'}],'min_order_size':'5','tick_size':'.01'}
            async def delay(_):now[0]+=.25
            with patch('lab.worker.get_json',side_effect=fetch),patch('lab.worker.time.time',side_effect=lambda:now[0]),patch('lab.worker.asyncio.sleep',side_effect=delay),patch('lab.worker.train') as train:
                await w.iteration()
                trades=store.snapshot()['trades'];self.assertEqual(len(trades),1)
                self.assertEqual(trades[0]['strategy'],'eth-mid-window-v1');self.assertGreaterEqual(trades[0]['opened'],start+200.25)
                with store.connect() as db:
                    evidence=json.loads(db.execute('SELECT evidence FROM positions').fetchone()[0])
                self.assertEqual(evidence['risk_policy'],'eth-stop10-v1')
                self.assertEqual(evidence['config_version'],'eth-mid-window-v1-stop10-v1')
                self.assertLessEqual(trades[0]['cost']+trades[0]['fee'],5000000)
                phase.update(bid='.75',ask='.76');now[0]=start+300
                await w.paper_exits(w.market,True) # decision snapshot from previous cycle cannot trigger
                await w.cycle()
                self.assertEqual(store.snapshot()['trades'][0]['status'],'OPEN')
                phase['closed']=True;now[0]=start+1000;await w.reconcile()
                self.assertEqual(store.snapshot()['trades'][0]['status'],'RESOLVED');train.assert_not_called();store.audit()
