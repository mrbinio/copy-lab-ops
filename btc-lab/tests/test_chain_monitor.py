import asyncio, hashlib, json, tempfile, unittest
from pathlib import Path
from lab.core import Store
from lab.wallet_chain_monitor import (
    parse_transfer_single, classify_transfer, ChainMonitor, ChainBridge, _row_key,
    TRANSFER_SINGLE_TOPIC, CTF_TOKEN, EXCHANGE_OPERATORS, ZERO_ADDRESS,
)
from lab.wallet_observer import WALLETS

WALLET_A = WALLETS[0]
CTF_EXCHANGE = list(EXCHANGE_OPERATORS)[0]

def make_log(op, frm, to, token_id=12345, value=5000000, block=100, tx='0xabc', log_index=0, removed=False):
    return {'address':CTF_TOKEN.lower(),'topics':[TRANSFER_SINGLE_TOPIC,'0x'+op.replace('0x','').zfill(64),
            '0x'+frm.replace('0x','').zfill(64),'0x'+to.replace('0x','').zfill(64)],
            'data':'0x'+hex(token_id)[2:].zfill(64)+hex(value)[2:].zfill(64),
            'blockNumber':hex(block),'transactionHash':tx,'logIndex':hex(log_index),'removed':removed}

class ParseTests(unittest.TestCase):
    def test_valid(self):
        e=parse_transfer_single(make_log(CTF_EXCHANGE,'0xs',WALLET_A));self.assertEqual(e['to'],WALLET_A)
    def test_wrong_topic(self):
        l=make_log(CTF_EXCHANGE,'0xa','0xb');l['topics'][0]='0x'+'ff'*32;self.assertIsNone(parse_transfer_single(l))
    def test_short_data(self):
        l=make_log(CTF_EXCHANGE,'0xa','0xb');l['data']='0x12';self.assertIsNone(parse_transfer_single(l))
    def test_removed(self):
        self.assertTrue(parse_transfer_single(make_log(CTF_EXCHANGE,'0xa','0xb',removed=True))['removed'])

class ClassifyTests(unittest.TestCase):
    def _e(self,op,f,t):return parse_transfer_single(make_log(op,f,t))
    def test_buy(self):self.assertEqual(classify_transfer(self._e(CTF_EXCHANGE,'0xs',WALLET_A),{WALLET_A}),(WALLET_A,'BUY'))
    def test_sell(self):self.assertEqual(classify_transfer(self._e(CTF_EXCHANGE,WALLET_A,'0xb'),{WALLET_A}),(WALLET_A,'SELL'))
    def test_rotating_operator_still_matches(self):
        """Relayer addresses rotate; gating on them dropped every seed fill."""
        unlisted='0xe111180000d2663c0091e4f400237545b87b996b'
        self.assertNotIn(unlisted.lower(),{o.lower() for o in EXCHANGE_OPERATORS}-{unlisted})
        self.assertEqual(classify_transfer(self._e('0xdeadbeef','0xs',WALLET_A),{WALLET_A}),(WALLET_A,'BUY'))
    def test_no_match(self):self.assertIsNone(classify_transfer(self._e(CTF_EXCHANGE,'0xa','0xb'),{WALLET_A})[0])

class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'lab.db')
        self.now=5000.0
        with self.store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS wallet_activity(wallet TEXT,event_key TEXT,first_seen REAL,source_ts REAL,body TEXT,PRIMARY KEY(wallet,event_key))')
        self.store.wallet_activity_ready=None
    def tearDown(self):self.tmp.cleanup()
    def _event(self,tx='0xtx1'):
        return {'wallet':WALLET_A,'side':'BUY','tx_hash':tx,'token_id':111,'value':5000000,
                'block_number':500,'detected_at':self.now,'operator':CTF_EXCHANGE,'from':'0xs','to':WALLET_A}
    def _api_row(self,tx='0xtx1',price=0.59,asset='111',side='BUY',idx=0):
        return {'transactionHash':tx,'type':'TRADE','side':side,'proxyWallet':WALLET_A,
                'timestamp':self.now-1,'slug':'btc-updown-15m-4000','conditionId':'c',
                'asset':asset,'price':price,'size':5.0,'usdcSize':2.95,'outcomeIndex':idx}

    def _fetch(self,activity,book=None,seen=None):
        """Gamma answers the open 15m window; an empty book forces the poll path."""
        def fetch(url):
            if 'gamma-api' in url:
                if 'btc-updown-15m-4500' in url:
                    return {'slug':'btc-updown-15m-4500','conditionId':'c','clobTokenIds':['111','222']}
                return {'slug':'other','conditionId':'z','clobTokenIds':['999']}
            if '/book?' in url:return book or {}
            if seen is not None:seen.append(url)
            return activity() if callable(activity) else activity
        return fetch

    def test_inserts_with_confirmed_api_price(self):
        row=self._api_row(price=0.59)
        bridge=ChainBridge(self.store,self._fetch([row]),lambda:self.now,asyncio.sleep)
        asyncio.run(bridge.on_event(self._event()))
        with self.store.connect() as db:
            rows=db.execute('SELECT * FROM wallet_activity').fetchall()
        self.assertEqual(len(rows),1)
        body=json.loads(rows[0]['body'])
        self.assertEqual(body['price'],0.59)
        self.assertEqual(body['_source'],'chain_accelerated')
        self.assertEqual(bridge.bridged,1)

    def test_same_key_as_rest(self):
        row=self._api_row()
        bridge=ChainBridge(self.store,self._fetch([row]),lambda:self.now,asyncio.sleep)
        asyncio.run(bridge.on_event(self._event()))
        with self.store.connect() as db:
            actual=db.execute('SELECT event_key FROM wallet_activity').fetchone()[0]
        self.assertEqual(actual,_row_key(row))

    def test_rest_already_has_same_key_skipped(self):
        """REST inserted this exact row → chain INSERT OR IGNORE = 0."""
        row=self._api_row(tx='0xsame')
        key=_row_key(row)
        with self.store.connect() as db:
            db.execute('INSERT INTO wallet_activity VALUES(?,?,?,?,?)',
                       (WALLET_A,key,self.now,self.now,json.dumps(row)))
        bridge=ChainBridge(self.store,self._fetch([row]),lambda:self.now,asyncio.sleep)
        asyncio.run(bridge.on_event(self._event(tx='0xsame')))
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM wallet_activity').fetchone()[0],1)

    def test_chain_first_rest_deduped(self):
        """Chain inserts → REST tries same key → INSERT OR IGNORE."""
        row=self._api_row(tx='0xfirst')
        bridge=ChainBridge(self.store,self._fetch([row]),lambda:self.now,asyncio.sleep)
        asyncio.run(bridge.on_event(self._event(tx='0xfirst')))
        key=_row_key(row)
        with self.store.connect() as db:
            cur=db.execute('INSERT OR IGNORE INTO wallet_activity VALUES(?,?,?,?,?)',
                           (WALLET_A,key,self.now,self.now,json.dumps(row)))
            self.assertEqual(cur.rowcount,0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM wallet_activity').fetchone()[0],1)

    def test_multi_fill_same_tx(self):
        """Two fills in one tx → both inserted."""
        fill1=self._api_row(tx='0xm',price=0.55,asset='111',idx=0)
        fill2=self._api_row(tx='0xm',price=0.45,asset='222',side='SELL',idx=1)
        bridge=ChainBridge(self.store,self._fetch([fill1,fill2]),lambda:self.now,asyncio.sleep)
        asyncio.run(bridge.on_event(self._event(tx='0xm')))
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM wallet_activity').fetchone()[0],2)
        self.assertEqual(bridge.bridged,2)

    def test_one_fill_already_exists_second_still_inserted(self):
        """First fill already in DB → bridge still inserts second fill."""
        fill1=self._api_row(tx='0xp',price=0.55,asset='111',idx=0)
        fill2=self._api_row(tx='0xp',price=0.45,asset='222',side='SELL',idx=1)
        # Pre-insert fill1 (as if REST got it first)
        with self.store.connect() as db:
            db.execute('INSERT INTO wallet_activity VALUES(?,?,?,?,?)',
                       (WALLET_A,_row_key(fill1),self.now,self.now,json.dumps(fill1)))
        bridge=ChainBridge(self.store,self._fetch([fill1,fill2]),lambda:self.now,asyncio.sleep)
        asyncio.run(bridge.on_event(self._event(tx='0xp')))
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM wallet_activity').fetchone()[0],2)
        self.assertEqual(bridge.bridged,1)  # only fill2 was new

    def test_timeout(self):
        times=[self.now]
        async def fast_sleep(s):times[0]+=s
        bridge=ChainBridge(self.store,self._fetch([]),lambda:times[0],fast_sleep)
        asyncio.run(bridge.on_event(self._event()))
        self.assertEqual(bridge.timeouts,1)
        self.assertEqual(bridge.bridged,0)

    def test_polls_until_found(self):
        n=[0]
        row=self._api_row()
        times=[self.now]
        def activity():
            n[0]+=1
            return [row] if n[0]>=3 else []
        async def fast_sleep(s):times[0]+=s
        bridge=ChainBridge(self.store,self._fetch(activity),lambda:times[0],fast_sleep)
        asyncio.run(bridge.on_event(self._event()))
        self.assertEqual(bridge.bridged,1)
        self.assertGreaterEqual(n[0],3)

    def test_fast_insert_skips_public_list(self):
        self.now=4500.5
        def fetch(url):
            if 'gamma-api' in url:
                if 'btc-updown-15m-4500' in url:
                    return {'slug':'btc-updown-15m-4500','conditionId':'c','clobTokenIds':['111','222']}
                return {'slug':'other','conditionId':'z','clobTokenIds':['9']}
            if '/book?' in url:
                return {'asks':[{'price':'0.61','size':'20'}]}
            raise AssertionError(url)
        bridge=ChainBridge(self.store,fetch,lambda:self.now,asyncio.sleep)
        asyncio.run(bridge.on_event(self._event()))
        with self.store.connect() as db:
            rows=db.execute('SELECT body FROM wallet_activity').fetchall()
        self.assertEqual(len(rows),1)
        body=json.loads(rows[0][0])
        self.assertEqual(body['_source'],'chain_fast')
        self.assertEqual(body['price'],0.61)
        self.assertEqual(body['slug'],'btc-updown-15m-4500')
        self.assertEqual(bridge.bridged,1)

    def test_off_market_token_is_dropped_without_polling(self):
        """Hourly markets cannot be copied; they must not occupy the poll queue."""
        seen=[]
        bridge=ChainBridge(self.store,self._fetch([self._api_row()],seen=seen),lambda:self.now,asyncio.sleep)
        asyncio.run(bridge.on_event(dict(self._event(),token_id=777)))
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM wallet_activity').fetchone()[0],0)
        self.assertEqual(bridge.off_market,1)
        self.assertEqual(bridge.bridged,0)
        self.assertEqual(seen,[])

    def test_window_set_survives_gamma_failure(self):
        calls=[0]
        def fetch(url):
            if 'gamma-api' in url:
                calls[0]+=1
                if calls[0]>4:raise RuntimeError('gamma down')
                if 'btc-updown-15m-4500' in url:
                    return {'slug':'btc-updown-15m-4500','conditionId':'c','clobTokenIds':['111','222']}
                return {'slug':'other','conditionId':'z','clobTokenIds':['999']}
            if '/book?' in url:return {'asks':[{'price':'0.61','size':'20'}]}
            raise AssertionError(url)
        bridge=ChainBridge(self.store,fetch,lambda:self.now,asyncio.sleep)
        self.assertIsNotNone(bridge._window_for('111'))
        bridge._windows_at=0  # force a refresh that now fails
        self.assertIsNotNone(bridge._window_for('111'))

    def test_status(self):
        s=ChainBridge(self.store,lambda u:[],lambda:self.now).status()
        self.assertIn('bridged',s);self.assertIn('timeouts',s);self.assertIn('off_market',s)

    def test_an_order_filled_receipt_replaces_a_book_quote(self):
        bridge=ChainBridge(self.store,lambda u:[],lambda:self.now,asyncio.sleep)
        quote={'transactionHash':'0xfill','type':'TRADE','side':'BUY','asset':'111',
               'price':0.99,'size':5,'_source':'chain_fast','timestamp':self.now}
        paid=dict(quote, price=0.42, usdcSize=2.1, _source='order_filled')
        self.assertTrue(bridge._insert(WALLET_A, quote, self.now, 'chain-fast'))
        self.assertTrue(bridge._insert(WALLET_A, paid, self.now, 'order-filled'))
        with self.store.connect() as db:
            body=json.loads(db.execute('SELECT body FROM wallet_activity').fetchone()[0])
        self.assertEqual(body['_source'],'order_filled')
        self.assertEqual(body['price'],0.42)
        self.assertFalse(bridge._insert(WALLET_A, quote, self.now, 'chain-fast'))

class MonitorTests(unittest.IsolatedAsyncioTestCase):
    async def test_non_blocking_dispatch(self):
        calls=[]
        async def handler(e):calls.append(e['tx_hash']);await asyncio.sleep(0.05)
        m=ChainMonitor('wss://fake',[WALLET_A],handler)
        e1={'wallet':WALLET_A,'side':'BUY','tx_hash':'0x1','token_id':1,'value':1,'block_number':1,'detected_at':1000}
        e2=dict(e1,tx_hash='0x2')
        t1=asyncio.create_task(m._safe_handle(e1));t2=asyncio.create_task(m._safe_handle(e2))
        await asyncio.sleep(0.01)
        self.assertEqual(len(calls),2)
        await asyncio.gather(t1,t2)

    async def test_bounded_queue(self):
        m=ChainMonitor('wss://fake',[WALLET_A],lambda e:asyncio.sleep(100))
        for i in range(12):
            m._tasks.add(asyncio.create_task(asyncio.sleep(100)))
        self.assertGreaterEqual(len(m._tasks),10)
        self.assertEqual(m.status()['pending_tasks'],12)

    def test_status_defaults(self):
        s=ChainMonitor('wss://fake',[WALLET_A],lambda e:None).status()
        self.assertEqual(s['mode'],'CHAIN_FAST')
        self.assertFalse(s['connected'])

if __name__=='__main__':unittest.main()


class PrintFilterTests(unittest.TestCase):
    def test_only_trade_prints_pass_the_cheap_filter(self):
        import inspect
        from lab import wallet_chain_monitor
        source = inspect.getsource(wallet_chain_monitor.run_market_prints)
        self.assertIn('"event_type":"last_trade_price"', source)
        book = '[{"event_type":"book","last_trade_price":"0.49","bids":[]}]'
        trade = '[{"event_type":"last_trade_price","price":"0.5","transaction_hash":"0xab"}]'
        check = lambda raw: '"event_type":"last_trade_price"' in raw or '"event_type": "last_trade_price"' in raw
        self.assertFalse(check(book))
        self.assertTrue(check(trade))
