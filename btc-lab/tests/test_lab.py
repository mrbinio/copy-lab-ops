import base64
import concurrent.futures
import hashlib
import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch, AsyncMock
from pathlib import Path
from http.server import ThreadingHTTPServer
from lab.core import Store, LedgerError, simulate_fill, units
from lab.strategy import choose, features
from lab.worker import Worker, normalize_market, normalize_book, get_json, error_detail, reference_subscription
from lab.server import handler
from lab.research import train

def fill():
    return simulate_fill([['.90','100']],'5','.90','.07','5','.01')

class ExecutionTests(unittest.TestCase):
    def test_fee_and_payout_arithmetic(self):
        f=fill()
        self.assertEqual(f['shares'],5555555)
        self.assertEqual(f['cost'],5000000)
        self.assertEqual(f['fee'],35000)
        self.assertEqual((f['shares']-f['cost']-f['fee'])/1e6,.520555)

    def test_no_partial_or_limit_chasing(self):
        self.assertIsNone(simulate_fill([['.9','4'],['.92','100']],'5','.91','.07','5','.01'))

    def test_minimum_size_and_tick(self):
        self.assertIsNone(simulate_fill([['.9','100']],'1','.90','.07','5','.01'))
        self.assertIsNone(simulate_fill([['.91','100']],'5','.909','.07','5','.01'))
        with self.assertRaises(ValueError):simulate_fill([['.905','100']],'5','.91','.07','5','.01')

    def test_depth_haircut(self):
        self.assertIsNone(simulate_fill([['.9','8']],'5','.9','.07','5','.01'))
        self.assertIsNotNone(simulate_fill([['.9','8']],'5','.9','.07','5','.01',depth_fraction='1'))

    def test_invalid_numbers(self):
        for bad in ('NaN','Infinity','-1'):
            with self.assertRaises(ValueError):simulate_fill([[bad,'100']],'5','.9','.07','5','.01')

class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.temp.name)/'test.db')
    def tearDown(self):self.temp.cleanup()
    def enter(self,market='m',ts=1000):return self.store.open('value-v1',market,'Up',fill(),{},ts)
    def test_duplicate_concurrent_entry(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            results=list(pool.map(lambda _:self.enter(),range(5)))
        self.assertEqual(results.count('FILLED'),1)
        self.store.audit()
        self.assertEqual(self.store.snapshot()['accounts'][0]['cash'],494.965)

    def test_resolution_not_cash_and_idempotent_redemption(self):
        self.enter()
        e={'source':'clob_official_winner','closed':True}
        self.store.resolve('m','Up',e,1100)
        self.store.resolve('m','Up',e,1200)
        a=self.store.snapshot()['accounts'][0]
        self.assertEqual(a['cash'],494.965)
        self.assertEqual(a['pending'],5.555555)
        self.store.redeem(1399)
        self.assertEqual(self.store.snapshot()['accounts'][0]['cash'],494.965)
        self.store.redeem(1400)
        self.store.redeem(1400)
        self.assertAlmostEqual(self.store.snapshot()['accounts'][0]['cash'],500.520555)
        self.store.audit()
        with self.assertRaises(LedgerError):self.store.resolve('m','Down',e,1500)

    def test_no_provisional_resolution(self):
        self.enter()
        with self.assertRaises(ValueError):self.store.resolve('m','Up',{'source':'binance','closed':True},1100)
        self.assertEqual(self.store.snapshot()['trades'][0]['status'],'OPEN')

    def test_restart_and_atomic_failure(self):
        with self.store.connect() as db:
            db.execute("CREATE TRIGGER fail_entry BEFORE INSERT ON ledger BEGIN SELECT RAISE(ABORT, 'simulated crash'); END")
        with self.assertRaises(Exception):self.enter()
        reopened=Store(self.store.path)
        self.assertEqual(reopened.snapshot()['accounts'][0]['cash'],500)
        self.assertEqual(reopened.snapshot()['trades'],[])

    def test_worst_case_budget_before_entry(self):
        e={'source':'clob_official_winner','closed':True}
        for i in range(2):
            self.assertEqual(self.enter(str(i),1000+i*1000),'FILLED')
            self.store.resolve(str(i),'Down',e,1100+i*1000)
            self.store.redeem(1400+i*1000)
        self.assertEqual(self.enter('third',4000),'RISK_LIMIT')

    def test_cash_corruption_detected(self):
        with self.store.connect() as db:db.execute("UPDATE accounts SET cash=cash+1 WHERE strategy='value-v1'")
        with self.assertRaises(LedgerError):self.store.audit()

    def test_research_cannot_claim_ready_without_labels(self):
        self.assertEqual(train(self.store)['status'],'COLLECTING')

class DataTests(unittest.TestCase):
    def test_rtds_filters_match_required_compact_wire_format(self):
        for subscription in reference_subscription()['subscriptions']:
            self.assertEqual(subscription['filters'],'{"symbol":"btc/usd"}')

    def test_twap_market_never_uses_spot_strategy(self):
        raw={'slug':'btc-updown-15m-900','conditionId':'c','outcomes':['Up','Down'],'clobTokenIds':['u','d'],
             'description':'Bitcoin Chainlink TWAP at the end greater than or equal to beginning.'}
        market=normalize_market(raw,900)
        self.assertFalse(market['rule_supported'])
        self.assertEqual(market['rule_kind'],'UNKNOWN')

    def test_network_error_keeps_endpoint_and_reason(self):
        with patch('lab.worker.urllib.request.urlopen',side_effect=urllib.error.URLError('CERTIFICATE_VERIFY_FAILED')):
            with self.assertRaisesRegex(RuntimeError,'gamma-api.polymarket.com/markets: URLError: CERTIFICATE_VERIFY_FAILED'):
                get_json('https://gamma-api.polymarket.com/markets?private=hidden')
        self.assertNotIn('secret',error_detail(ValueError('https://user:secret@proxy.example/')))

    def test_token_mapping_uses_labels(self):
        raw={'slug':'btc-updown-15m-900','conditionId':'c','outcomes':'["Down","Up"]','clobTokenIds':'["d","u"]'}
        m=normalize_market(raw,900)
        self.assertEqual(m['tokens'],{'Down':'d','Up':'u'})
        self.assertFalse(m['rule_supported'])
        self.assertFalse(m['fee_verified'])

    def test_future_and_wrong_book_rejected(self):
        for raw in ({'asset_id':'wrong'},{'asset_id':'u','timestamp':'101000'}):
            with self.assertRaises(ValueError):normalize_book(raw,'u',100)

    def test_no_signal_on_stale_reference(self):
        m={'end':1100,'opening':70000,'rule_supported':True,'accepting':True,'fee_verified':True}
        signal,reason=choose('late-v1',m,{'price':70100,'source_ts':990},{},1000)
        self.assertIsNone(signal)
        self.assertEqual(reason,'REFERENCE_STALE')

    def test_missing_history_not_zero_volatility(self):
        self.assertIsNone(features(70100,70000,[],.9,120))

class AuthTests(unittest.TestCase):
    def test_http_auth_and_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'db')
            digest=hashlib.sha256(b'test-password').hexdigest()
            server=ThreadingHTTPServer(('127.0.0.1',0),handler(store,Path(tmp),digest))
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            url=f'http://127.0.0.1:{server.server_port}'
            try:
                with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(url+'/api/state')
                self.assertEqual(e.exception.code,401)
                auth='Basic '+base64.b64encode(b'damian:test-password').decode()
                req=urllib.request.Request(url+'/api/state',headers={'Authorization':auth})
                with urllib.request.urlopen(req) as r:
                    s=json.load(r)
                    self.assertFalse(s['live_enabled'])
                    self.assertEqual(s['mode'],'PAPER')
                    self.assertEqual(r.headers['Cache-Control'],'no-store')
                with self.assertRaises(urllib.error.HTTPError) as e:
                    urllib.request.urlopen(urllib.request.Request(url+'/api/trade',data=b'{}',headers={'Authorization':auth}))
                self.assertEqual(e.exception.code,501)
            finally:server.shutdown();server.server_close();thread.join()

class CycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_settlement_survives_collection_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            worker=Worker(Store(Path(tmp)/'db'),tmp)
            worker.last_research=time.time()
            worker.cycle=AsyncMock(side_effect=TimeoutError('market unavailable'))
            worker.reconcile=AsyncMock()
            await worker.iteration()
            worker.reconcile.assert_awaited_once()
            self.assertEqual(worker.store.get('worker')['errors'][0]['stage'],'collection')

    async def test_reconciliation_failure_blocks_new_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            worker=Worker(Store(Path(tmp)/'db'),tmp)
            worker.last_research=time.time()
            worker.cycle=AsyncMock()
            worker.reconcile=AsyncMock(side_effect=LedgerError('conflict'))
            await worker.iteration()
            worker.cycle.assert_awaited_once_with(entries_allowed=False)
            self.assertTrue((Path(tmp)/'PAUSE').exists())

    async def test_delayed_book_used_and_official_settlement(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'db')
            worker=Worker(store,tmp)
            now=9800.;start=9000
            worker.reference={'price':70100,'source_ts':now,'received_at':now,'source':'fixture'}
            worker.history.append((start,70000))
            raw={'slug':'btc-updown-15m-9000','conditionId':'c','outcomes':'["Up","Down"]','clobTokenIds':'["u","d"]',
                 'active':True,'closed':False,'acceptingOrders':True,'feesEnabled':True,'feeSchedule':{'rate':.07,'exponent':1},
                 'description':'Bitcoin at the end is greater than or equal to the beginning. Source: Chainlink.'}
            phase={'book_calls':0,'arrival':'.90','closed':False}
            def fetch(url):
                if '/markets/slug/' in url:return raw
                if '/markets/c' in url:return {'condition_id':'c','closed':phase['closed'],'tokens':[{'outcome':'Up','token_id':'u','winner':True}]}
                token=url.split('token_id=')[1]
                phase['book_calls']+=1
                price=('.90' if phase['book_calls']<=2 else phase['arrival']) if token=='u' else '.12'
                return {'asset_id':token,'timestamp':str(int(now*1000)),'asks':[{'price':price,'size':'100'}],
                        'bids':[{'price':'.10','size':'100'}],'min_order_size':'5','tick_size':'.01'}
            with patch('lab.worker.get_json',side_effect=fetch),patch('lab.worker.time.time',side_effect=lambda:now),patch('lab.worker.asyncio.sleep',new_callable=AsyncMock):
                phase['arrival']='.93'
                await worker.cycle()
                self.assertEqual(store.snapshot()['trades'],[])  # decision .90, arrival .93 > .91 limit
                phase['book_calls']=0;phase['arrival']='.90'
                await worker.cycle()
                self.assertEqual(len(store.snapshot()['trades']),1)
                now=10000.;phase['closed']=True
                await worker.reconcile()
                self.assertEqual(store.snapshot()['trades'][0]['status'],'RESOLVED')
                now=10301.
                await worker.reconcile()
                self.assertEqual(store.snapshot()['trades'][0]['status'],'REDEEMED')
                store.audit()

if __name__=='__main__': unittest.main()
