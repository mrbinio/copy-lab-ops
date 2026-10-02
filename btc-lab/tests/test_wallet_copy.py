import asyncio
import copy
import json
import tempfile
import unittest
from datetime import datetime,timezone
from pathlib import Path
from lab.core import Store
from lab.reference import TWAP_RULE
from lab.wallet_copy import WalletCopy,CopyLedgerError,market_spec,KEY
from lab.wallet_observer import WALLETS,WalletObserver

class CopyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=Store(Path(self.temp.name)/'lab.db')
        self.now=1100.;self.pause=False;self.ask='.60';self.bid='.59';self.depth='100';self.stale=False;self.delay=.5;self.book_calls=0
        self.slug='btc-updown-15m-1000'
        self.raw=dict(slug=self.slug,conditionId='condition',eventStartTime=datetime.fromtimestamp(1000,timezone.utc).isoformat(),
            endDate=datetime.fromtimestamp(1900,timezone.utc).isoformat(),active=True,closed=False,acceptingOrders=True,
            outcomes=['Up','Down'],clobTokenIds=['1','2'],description=TWAP_RULE,feesEnabled=True,feeSchedule={'exponent':1,'rate':.07})
        self.official={'condition_id':'condition','closed':True,'tokens':[{'token_id':'1','winner':False},{'token_id':'2','winner':True}]}
        self.engine=WalletCopy(self.store,self.fetch,lambda:self.pause,lambda:self.now,self.sleep)
    def tearDown(self):self.temp.cleanup()
    async def sleep(self,seconds):self.now+=self.delay
    def fetch(self,url):
        if 'gamma-api' in url:return copy.deepcopy(self.raw)
        if '/book?' in url:
            self.book_calls+=1
            return {'asset_id':url.rsplit('=',1)[1],'timestamp':int((1102 if self.stale else self.now)*1000),
                'asks':[{'price':self.ask,'size':self.depth}],'bids':[{'price':self.bid,'size':self.depth}],
                'min_order_size':'5','tick_size':'.01'}
        if '/markets/' in url:return copy.deepcopy(self.official)
        raise AssertionError(url)
    def row(self,key='one',side='BUY',wallet=WALLETS[0]):
        return {'wallet':wallet,'event_key':key,'source_ts':self.now-1,'first_seen':self.now,
            'body':json.dumps(dict(proxyWallet=wallet,type='TRADE',side=side,slug=self.slug,conditionId='condition',asset='1',timestamp=self.now-1,
                transactionHash=key,price=.59,size=100))}
    def process(self,row):asyncio.run(self.engine.process(row));self.engine.publish('TEST')
    def state(self):return self.store.get(KEY,{})
    def buy(self):self.now=1102;row=self.row();self.process(row);return row
    def reason(self):
        with self.store.connect() as db:return db.execute('SELECT reason FROM wallet_copy_events ORDER BY ts DESC,rowid DESC LIMIT 1').fetchone()[0]
    def test_forward_buy_uses_current_ask_not_source_price_and_sale_both_fees(self):
        self.buy();t=self.state()['recent_trades'][0]
        self.assertEqual(t['entry_fill']['vwap'],.6);self.assertEqual(t['source_price'],.59)
        self.assertLessEqual(t['cost']+t['fee'],5_000_000);self.assertGreaterEqual(t['copy_delay'],1)
        self.now+=2;self.bid='.70';self.ask='.71';self.process(self.row('sell','SELL'))
        t=self.state()['recent_trades'][0];a=self.state()['accounts'][0]
        self.assertEqual(t['status'],'CLOSED');self.assertGreater(t['exit_fee'],0)
        self.assertAlmostEqual(a['pnl'],(t['payout']-t['cost']-t['fee']-t['exit_fee'])/1e6)
        self.assertAlmostEqual(a['cash'],500+a['pnl'])
        self.assertTrue(all(a['trades']==0 for a in self.store.snapshot()['accounts'] if not a['id'].startswith('copy-')))
    def test_duplicate_restart_does_not_double_buy(self):
        row=self.buy();cash=self.state()['accounts'][0]['cash']
        self.engine=WalletCopy(self.store,self.fetch,lambda:False,lambda:self.now,self.sleep)
        self.process(row);self.assertEqual(self.state()['accounts'][0]['trades'],1);self.assertEqual(self.state()['accounts'][0]['cash'],cash)
    def test_old_and_pre_activation_not_replayed(self):
        self.now=1102;row=self.row();row['source_ts']=1099;self.process(row);self.assertEqual(self.reason(),'PRE_ACTIVATION')
        self.now=1300;row=self.row('old');row['source_ts']=1101;self.process(row);self.assertEqual(self.reason(),'SOURCE_TOO_OLD');self.assertEqual(self.book_calls,0)
    def test_stale_arrival_and_latency_rejected(self):
        self.stale=True;self.buy();self.assertEqual(self.reason(),'COPIED_BUY')
        self.stale=False;self.delay=6;self.now=1110;self.process(self.row('slow'));self.assertEqual(self.reason(),'COPY_POSITION_ALREADY_OPEN')
    def test_minimum_and_failed_sale_do_not_invent_fills(self):
        self.depth='1';self.buy();self.assertEqual(self.reason(),'BUY_NO_FULL_FILL_OR_MINIMUM')
        self.depth='100';self.now=1110;self.process(self.row('new'))
        self.depth='1';self.now+=2;self.process(self.row('sell','SELL'))
        self.assertEqual(self.reason(),'SELL_NO_FULL_FILL');self.assertEqual(self.state()['recent_trades'][0]['status'],'OPEN')
    def test_settlement_loss_after_delay_is_idempotent(self):
        self.buy();self.now=1901;asyncio.run(self.engine.settle());self.engine.publish('TEST')
        self.assertEqual(self.state()['accounts'][0]['settled'],0)
        self.now=2202;asyncio.run(self.engine.settle());self.engine.publish('TEST')
        a=self.state()['accounts'][0];self.assertEqual(a['settled'],1);self.assertLess(a['pnl'],0)
        asyncio.run(self.engine.settle());self.engine.publish('TEST');self.assertEqual(self.state()['accounts'][0]['cash'],a['cash'])
    def test_token_fee_pause_and_unsupported_rejected(self):
        self.now=1102;self.pause=True;self.process(self.row());self.assertEqual(self.reason(),'PAUSED')
        self.pause=False;row=self.row('wrong');body=json.loads(row['body']);body['asset']='9';row['body']=json.dumps(body);self.process(row);self.assertEqual(self.reason(),'ERROR')
        self.raw['feeSchedule']={};self.process(self.row('fee'));self.assertEqual(self.reason(),'ERROR');self.assertEqual(self.book_calls,0)
    def test_separate_wallets_and_no_additional_position(self):
        self.buy();self.now+=2;self.process(self.row('two'));self.assertEqual(self.reason(),'COPY_POSITION_ALREADY_OPEN')
        self.process(self.row('other',wallet=WALLETS[1]));self.assertEqual([a['trades'] for a in self.state()['accounts']],[1,1,0,0])
    def test_cash_corruption_blocks_before_processing(self):
        with self.store.connect() as db:db.execute('UPDATE wallet_copy_accounts SET cash=cash-1 WHERE wallet=?',(WALLETS[0],))
        with self.assertRaises(CopyLedgerError):asyncio.run(self.engine.step())
        self.assertEqual(self.book_calls,0)
    def test_five_minute_metadata_and_daily_export(self):
        self.now=1102;event=json.loads(self.row()['body']);event['slug']='btc-updown-5m-1000'
        raw=copy.deepcopy(self.raw);raw.update(slug=event['slug'],endDate=datetime.fromtimestamp(1300,timezone.utc).isoformat())
        self.assertEqual(market_spec(raw,event,self.now)['end'],1300)
        self.buy();self.now=1105;self.bid='.70';self.process(self.row('sell','SELL'))
        from lab.daily_report import build_report
        report=build_report(self.store,day='1970-01-01',now=1800000000)
        self.assertEqual(report['wallet_copy_daily'][0]['closed'],1)
        self.assertEqual(report['wallet_copy_daily'][0]['net_pnl_usd'],self.state()['accounts'][0]['pnl'])
        self.assertNotIn('entry_evidence',report['wallet_copy_daily'][0]['period_trades'][0])
    def test_observer_backlog_skipped_without_replay(self):
        observer=WalletObserver(self.store,None)
        old=json.loads(self.row()['body']);old['timestamp']=1050
        observer.ingest(WALLETS[0],[old],1102)
        self.now=1103;asyncio.run(self.engine.step());self.assertEqual(self.reason(),'PRE_ACTIVATION');self.assertEqual(self.book_calls,0)

    def test_source_identity_and_daily_loss_cap(self):
        self.now=1102;row=self.row('wrong-identity');body=json.loads(row['body']);body['proxyWallet']=WALLETS[1];row['body']=json.dumps(body)
        self.process(row);self.assertEqual(self.reason(),'SOURCE_IDENTITY_MISMATCH')
        for i in range(3):
            self.now+=2;self.process(self.row('loss'+str(i)))
            with self.store.connect() as db:trade=next(t for t in self.engine.positions(db) if t['status']=='OPEN')
            self.engine.close(trade,0,0,self.now,'SETTLED',{})
        self.now+=2;self.process(self.row('blocked'))
        self.assertEqual(self.reason(),'COPIED_BUY')

    def test_source_price_band_and_age_reject_before_buy(self):
        self.now=1120;row=self.row('moved');e=json.loads(row['body']);e['price']=.46;row['body']=json.dumps(e)
        self.process(row);self.assertEqual(self.reason(),'COPIED_BUY')
        self.now=1170;row=self.row('late');row['source_ts']=1105;e=json.loads(row['body']);e['timestamp']=1105;row['body']=json.dumps(e)
        self.process(row);self.assertEqual(self.reason(),'COPY_POSITION_ALREADY_OPEN')
        self.assertEqual(self.state()['accounts'][0]['trades'],1)
    def test_arrival_source_band_rechecked(self):
        async def jump(seconds):self.now+=.5;self.ask='.45'
        self.engine.sleep=jump;self.buy()
        self.assertEqual(self.reason(),'COPIED_BUY');self.assertEqual(self.state()['accounts'][0]['trades'],1)
