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
        self.now=1100.;self.pause=False;self.ask='.60';self.bid='.59';self.depth='100';self.stale=False;self.delay=.5;self.book_calls=0;self.market_calls=0
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
        if '/markets/' in url:
            self.market_calls+=1
            return copy.deepcopy(self.official)
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
        self.assertLessEqual(t['cost']+t['fee'],5_000_000)
        self.assertAlmostEqual(t['entry_fill']['shares']/1e6,5)
        self.assertGreaterEqual(t['copy_delay'],1)
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
    def test_copy_publish_includes_clock_skew(self):
        self.engine.publish('TEST')
        skew=self.state().get('clock_skew')
        self.assertEqual(skew['book'],0)
        self.assertEqual(skew['samples'],0)

    def test_per_wallet_copy_pause(self):
        from lab.strategy_control import set_paused
        set_paused(self.store,'copy-'+WALLETS[0],True)
        self.now=1102;self.process(self.row());self.assertEqual(self.reason(),'COPY_PAUSED')
        self.assertEqual(self.state()['accounts'][0]['trades'],0)
        self.assertGreaterEqual(self.book_calls,1)
    def test_token_fee_pause_and_unsupported_rejected(self):
        self.now=1102;self.pause=True;self.process(self.row());self.assertEqual(self.reason(),'PAUSED')
        self.pause=False;row=self.row('wrong');body=json.loads(row['body']);body['asset']='9';row['body']=json.dumps(body);self.process(row);self.assertEqual(self.reason(),'ERROR')
        self.raw['feeSchedule']={};self.process(self.row('fee'));self.assertEqual(self.reason(),'ERROR');self.assertEqual(self.book_calls,0)
    def test_separate_wallets_and_no_additional_position(self):
        from lab.strategy_control import set_paused
        set_paused(self.store,'copy-'+WALLETS[1],False)
        self.buy();self.now+=2;self.process(self.row('two'));self.assertEqual(self.reason(),'COPY_POSITION_ALREADY_OPEN')
        self.process(self.row('other',wallet=WALLETS[1]));self.assertEqual([a['trades'] for a in self.state()['accounts']][:4],[1,1,0,0])
    def test_settlement_runs_beside_copy_not_inside_it(self):
        """A fresh copy must not wait for ended windows to settle."""
        self.buy();self.now=2202;before=self.market_calls
        asyncio.run(self.engine.step())
        self.assertEqual(self.market_calls,before)
        self.assertEqual(self.state()['recent_trades'][0]['status'],'OPEN')
        async def nothing():pass
        async def stop(seconds):raise asyncio.CancelledError
        self.engine.review_skips=nothing;self.engine.sleep=stop
        with self.assertRaises(asyncio.CancelledError):asyncio.run(self.engine.upkeep())
        self.engine.publish('TEST')
        self.assertEqual(self.state()['recent_trades'][0]['status'],'RESOLVED')
        self.assertGreater(self.market_calls,before)
        self.assertEqual(self.store.get('wallet_copy_settlement_error',{}),{})

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

    def test_inactive_backlog_does_not_starve_seed(self):
        self.now=1102
        observer=WalletObserver(self.store,None)
        other='0x'+'ab'*20
        stale=json.loads(self.row(wallet=other)['body']);stale['proxyWallet']=other;stale['timestamp']=1101
        for i in range(120):
            stale['transactionHash']=f'old{i}'
            observer.ingest(other,[dict(stale)],self.now)
        fresh=json.loads(self.row('fresh')['body'])
        observer.ingest(WALLETS[0],[fresh],self.now)
        asyncio.run(self.engine.step())
        with self.store.connect() as db:
            inactive=db.execute("SELECT COUNT(*) FROM wallet_copy_events WHERE wallet=?",(other,)).fetchone()[0]
            seed=db.execute("SELECT reason FROM wallet_copy_events WHERE wallet=?",(WALLETS[0],)).fetchone()[0]
        # Inactive history is not scanned into the queue, so it cannot block the seed.
        self.assertEqual(inactive,0)
        self.assertEqual(seed,'COPIED_BUY')
        self.assertGreaterEqual(self.book_calls,1)

    def test_observed_queue_does_not_take_the_seed_slot(self):
        self.now = 1102
        observed = '0x' + 'cd' * 20
        roster = self.store.get('wallet_roster')
        roster['wallets'][observed] = {'wallet': observed, 'state': 'observed', 'since': 1}
        self.store.set('wallet_roster', roster)
        observer = WalletObserver(self.store, None)
        for i in range(20):
            row = self.row('obs' + str(i), wallet=observed)
            body = json.loads(row['body'])
            body['transactionHash'] = row['event_key']
            observer.ingest(observed, [body], self.now - 1 + i * 0.01)
        fresh = json.loads(self.row('seed-fresh')['body'])
        observer.ingest(WALLETS[0], [fresh], self.now)
        with self.store.connect() as db:
            pending = self.engine.pending_activity(db)
        self.assertEqual(pending[0]['wallet'], WALLETS[0])
        self.assertLessEqual(sum(1 for row in pending if row['wallet'] == observed), 19)

    def test_source_identity_and_daily_loss_cap(self):
        self.now=1102;row=self.row('wrong-identity');body=json.loads(row['body']);body['proxyWallet']=WALLETS[1];row['body']=json.dumps(body)
        self.process(row);self.assertEqual(self.reason(),'SOURCE_IDENTITY_MISMATCH')
        for i in range(3):
            self.now+=2;self.process(self.row('loss'+str(i)))
            with self.store.connect() as db:trade=next(t for t in self.engine.positions(db) if t['status']=='OPEN')
            self.engine.close(trade,0,0,self.now,'SETTLED',{})
        self.now+=2;self.process(self.row('blocked'))
        self.assertEqual(self.reason(),'COPIED_BUY')

    def test_cheap_and_expensive_source_prices_are_skipped(self):
        """A $5 ticket on a 10-cent side died almost every time (−$157 on 40 trades)."""
        self.now=1102
        cheap=self.row('cheap');body=json.loads(cheap['body']);body['price']=0.10;cheap['body']=json.dumps(body)
        self.process(cheap);self.assertEqual(self.reason(),'COPY_PRICE_TOO_LOW')
        rich=self.row('rich');body=json.loads(rich['body']);body['price']=0.82;rich['body']=json.dumps(body)
        self.process(rich);self.assertEqual(self.reason(),'COPY_PRICE_TOO_HIGH')
        self.assertEqual(self.state()['accounts'][0]['trades'],0)

    def test_source_price_band_and_age_reject_before_buy(self):
        self.now=1120;row=self.row('moved');e=json.loads(row['body']);e['price']=.46;row['body']=json.dumps(e)
        self.process(row);self.assertEqual(self.reason(),'SOURCE_PRICE_MOVED')
        self.assertEqual(self.state()['accounts'][0]['trades'],0)
        self.now=1220;row=self.row('late');row['source_ts']=1105;e=json.loads(row['body']);e['timestamp']=1105;row['body']=json.dumps(e)
        self.process(row);self.assertEqual(self.reason(),'SOURCE_TOO_OLD')
        self.assertEqual(self.state()['accounts'][0]['trades'],0)
    def test_arrival_source_band_rechecked(self):
        async def jump(seconds):self.now+=.5;self.ask='.45'
        self.engine.sleep=jump;self.buy()
        self.assertEqual(self.reason(),'SOURCE_PRICE_MOVED');self.assertEqual(self.state()['accounts'][0]['trades'],0)

    def test_pause_lets_sell_close_and_blocks_the_next_buy(self):
        from lab.strategy_control import set_paused
        self.buy()
        set_paused(self.store,'copy-'+WALLETS[0],True)
        self.now+=2;self.bid='.70';self.process(self.row('sell','SELL'))
        trade=self.state()['recent_trades'][0]
        self.assertEqual(trade['status'],'CLOSED')
        self.assertGreater(trade['exit_fee'],0)
        self.now+=2;self.process(self.row('again'))
        self.assertEqual(self.reason(),'COPY_PAUSED')
        self.assertEqual(self.state()['accounts'][0]['trades'],1)

    def test_pause_does_not_block_official_settlement(self):
        from lab.strategy_control import set_paused
        self.buy()
        set_paused(self.store,'copy-'+WALLETS[0],True)
        self.now=2202
        asyncio.run(self.engine.settle())
        self.now=2502
        asyncio.run(self.engine.settle());self.engine.publish('TEST')
        self.assertEqual(self.state()['recent_trades'][0]['status'],'SETTLED')

    def test_missing_source_price_skips_before_the_book(self):
        self.now=1102
        row=self.row('blank');body=json.loads(row['body']);body.pop('price');row['body']=json.dumps(body)
        before=self.book_calls
        self.process(row)
        self.assertEqual(self.reason(),'SOURCE_PRICE_MISSING')
        self.assertEqual(self.book_calls,before)
        self.assertEqual(self.state()['accounts'][0]['trades'],0)

    def test_same_stream_matches_the_shared_policy(self):
        from decimal import Decimal
        from lab.copy_policy import decide_buy, decide_sell, remember_fill
        self.buy()
        bought=self.state()['recent_trades'][0]
        book={'asks':[['.60','100']],'bids':[['.59','100']],'min_shares':'5','tick':'.01','fee_rate':.07,'token':'1','source_ts':1102}
        consumed={}
        why,fill=decide_buy(Decimal('0.59'),book,consumed)
        self.assertIsNone(why)
        self.assertEqual(fill['shares'],bought['shares'])
        self.assertEqual(fill['cost'],bought['cost'])
        self.assertEqual(fill['fee'],bought['fee'])
        remember_fill(consumed,book,fill)
        self.now+=2;self.bid='.70';self.ask='.71';self.process(self.row('sell','SELL'))
        closed=self.state()['recent_trades'][0]
        sale_book=dict(book,bids=[['.70','100']],asks=[['.71','100']],fee_rate=.07)
        why,sold=decide_sell(sale_book,fill['shares'],{})
        self.assertIsNone(why)
        self.assertEqual(sold['fee'],closed['exit_fee'])
        self.assertEqual(sold['proceeds'],closed['payout'])

    def test_paper_extras_are_visible_before_first_trade(self):
        from lab.wallet_observer import PAPER_EXTRA
        names={a['wallet']:a['name'] for a in self.state()['accounts']}
        self.assertIn('Atomforge', names[PAPER_EXTRA[0]])
        self.assertIn('honey-spot', names[PAPER_EXTRA[1]])
        extras=[a for a in self.state()['accounts'] if a['wallet'] in PAPER_EXTRA]
        self.assertEqual([a['trades'] for a in extras],[0,0])
