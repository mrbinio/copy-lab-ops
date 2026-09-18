import json
import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock,patch
from lab.reference import TWAP_RULE, SPOT, TWAP60, TWAP30, observation
from lab.worker import Worker, normalize_market
from lab.core import Store
from lab.strategy import choose
from lab.research import train

def market(start=9000):
    iso=lambda ts:datetime.fromtimestamp(ts,timezone.utc).isoformat()
    return {'slug':f'btc-updown-15m-{start}','conditionId':'c','outcomes':['Up','Down'],'clobTokenIds':['u','d'],
            'description':TWAP_RULE,'eventStartTime':iso(start),'endDate':iso(start+900),
            'active':True,'closed':False,'acceptingOrders':True,'feesEnabled':True,'feeSchedule':{'rate':.07,'exponent':1}}

def event(ts,price='70000',topic=TWAP60):
    p={'symbol':'btc/usd','timestamp':int(ts*1000),'value':float(price)}
    if topic!=SPOT:p.update(window_s=60 if topic==TWAP60 else 30,full_accuracy_value=str(int(Decimal(price)*10**18)))
    return {'topic':topic,'type':'update','payload':p}

class TwapTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'db');self.worker=Worker(self.store,self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def test_exact_rule_and_market_times(self):
        raw=market();m=normalize_market(raw,9000)
        self.assertTrue(m['rule_supported']);self.assertEqual(m['reference_topic'],TWAP60)
        for field,value in [('description',TWAP_RULE+' Additional exception.'),('description',TWAP_RULE.replace('60s','30s')),('eventStartTime',raw['endDate']),('endDate','bad')]:
            self.assertFalse(normalize_market({**raw,field:value},9000)['rule_supported'])
    def test_decimal_not_display_price_and_window_validation(self):
        e=event(9000,'70000.123456789123456789');e['payload']['value']=1
        self.assertEqual(observation(e,9000.1)['price_decimal'],'70000.123456789123456789')
        for field,value in [('window_s',30),('full_accuracy_value',None),('full_accuracy_value','NaN'),('timestamp',9001000)]:
            with self.assertRaises(ValueError):observation({**e,'payload':{**e['payload'],field:value}},9000.1)
    def test_opening_requires_exact_twap60_never_spot_or_nearest(self):
        m=normalize_market(market(),9000)
        for e in (event(9000,'90000',SPOT),event(9000,'80000',TWAP30),event(9000.001,'70000')):
            self.worker.accept_reference(e,9000.1)
        self.worker.capture_opening(m);self.assertIsNone(m['opening'])
        w=Worker(self.store,self.tmp.name);w.accept_reference(event(9000,'70000.123456789123456789'),9000.1)
        w.capture_opening(m);self.assertEqual(m['opening_decimal'],'70000.123456789123456789')
        self.assertEqual(m['opening_evidence']['topic'],TWAP60)
    def test_duplicate_and_gap_do_not_fabricate_history(self):
        w=self.worker;w.accept_reference(event(9000),9000.1);w.accept_reference(event(9000,'70100'),9000.2)
        self.assertEqual(len(w.twap_history),1);self.assertEqual(w.references[TWAP60]['price'],70000)
        w.accept_reference(event(9020),9020.1);self.assertEqual(len(w.twap_history),1)
        m=normalize_market(market(),9000);w.capture_opening(m);self.assertIsNone(m['opening'])
    def test_model_does_not_mix_spot_and_twap(self):
        self.store.set('market',{'feature_schema':'twap60-v1'})
        with self.store.connect() as db:
            for i,schema in enumerate(('spot-v1','twap60-v1')):
                db.execute('INSERT INTO examples VALUES (?,?,?)',(str(i),i,json.dumps({'feature_schema':schema,'features':[1,0,0,0],'book_probability':.5})))
                db.execute('INSERT INTO labels VALUES (?,?,?,?)',(str(i),'Up',i,'{}'))
        model=train(self.store);self.assertEqual(model['samples'],1);self.assertEqual(model['feature_schema'],'twap60-v1')
    def test_wrong_stream_and_wrong_model_are_rejected(self):
        m=normalize_market(market(),9000);m.update(opening=70000,opening_decimal='70000',features=[1,0,0,0],books={'Up':{'asks':[['.9','100']],'source_ts':9780}})
        r=observation(event(9780,'70100',SPOT),9780)
        self.assertEqual(choose('late-v1',m,r,{},9780)[1],'REFERENCE_SOURCE_MISMATCH')
        r=observation(event(9780,'70100'),9780)
        self.assertEqual(choose('value-v1',m,r,{'status':'PAPER_CANDIDATE','feature_schema':'spot-v1','weights':[1,1,1,1]},9780)[1],'MODEL_SCHEMA_MISMATCH')
    def test_absent_opening_and_stale_twap_block_entries(self):
        m=normalize_market(market(),9000);r=observation(event(9800,'70100'),9800)
        self.assertEqual(choose('late-v1',m,r,{},9800)[1],'OPENING_REFERENCE_MISSING')
        m['opening']=70000
        self.assertEqual(choose('late-v1',m,r,{},9806)[1],'REFERENCE_STALE')

class TwapCycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_twap_signal_delayed_fill_and_official_settlement(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'db');w=Worker(store,tmp);raw=market();now=9800.
            w.market=normalize_market(raw,9000)
            w.accept_reference(event(9000),9000.1);w.capture_opening(w.market)
            w.accept_reference(event(now,'70100'),now)
            w.accept_reference(event(now,'69900',SPOT),now)
            phase={'closed':False}
            def fetch(url):
                if '/markets/slug/' in url:return raw
                if '/markets/c' in url:return {'condition_id':'c','closed':phase['closed'],'tokens':[{'outcome':'Down','token_id':'d','winner':True}]}
                token=url.split('token_id=')[1]
                return {'asset_id':token,'timestamp':str(int(now*1000)),'asks':[{'price':'.90' if token=='u' else '.12','size':'100'}],
                        'bids':[{'price':'.10','size':'100'}],'min_order_size':'5','tick_size':'.01'}
            with patch('lab.worker.get_json',side_effect=fetch),patch('lab.worker.time.time',side_effect=lambda:now),patch('lab.worker.asyncio.sleep',new_callable=AsyncMock):
                await w.cycle()
                trade=store.snapshot()['trades'][0];self.assertEqual(trade['side'],'Up')
                with store.connect() as db:evidence=json.loads(db.execute('SELECT evidence FROM positions').fetchone()[0])
                self.assertEqual(evidence['reference']['topic'],TWAP60)
                self.assertEqual(Decimal(evidence['opening_evidence']['price_decimal']),Decimal('70000'))
                self.assertEqual(store.get('reference')['topic'],TWAP60)
                now=10000.;phase['closed']=True;await w.reconcile()
                self.assertEqual(store.snapshot()['trades'][0]['payout'],0)
                now=10301.;await w.reconcile();store.audit()
                self.assertEqual(store.snapshot()['trades'][0]['status'],'REDEEMED')
