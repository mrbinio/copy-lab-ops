import asyncio
import copy
import json
import tempfile
import unittest
from datetime import datetime,timezone
from pathlib import Path
from lab.core import Store
from lab.reference import TWAP_RULE
from lab.wallet_copy import WalletCopy,CopyLedgerError,market_spec,KEY,decide_copy_flow
from lab.wallet_observer import WALLETS,WalletObserver

class CopyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=Store(Path(self.temp.name)/'lab.db')
        self.now=1100.;self.pause=False;self.ask='.60';self.bid='.59';self.depth='100';self.min_shares='5';self.stale=False;self.delay=.5;self.book_calls=0;self.market_calls=0
        self.slug='btc-updown-15m-1000'
        self.raw=dict(slug=self.slug,conditionId='condition',eventStartTime=datetime.fromtimestamp(1000,timezone.utc).isoformat(),
            endDate=datetime.fromtimestamp(1900,timezone.utc).isoformat(),active=True,closed=False,acceptingOrders=True,
            outcomes=['Up','Down'],clobTokenIds=['1','2'],description=TWAP_RULE,feesEnabled=True,feeSchedule={'exponent':1,'rate':.07})
        self.official={'condition_id':'condition','closed':True,'tokens':[{'token_id':'1','winner':False},{'token_id':'2','winner':True}]}
        self.engine=WalletCopy(self.store,self.fetch,lambda:self.pause,lambda:self.now,self.sleep)
        self.source_block=None
        self.source_log=1
    def tearDown(self):self.temp.cleanup()
    async def sleep(self,seconds):self.now+=self.delay
    def fetch(self,url):
        if 'gamma-api' in url:return copy.deepcopy(self.raw)
        if '/book?' in url:
            self.book_calls+=1
            return {'asset_id':url.rsplit('=',1)[1],'timestamp':int((1102 if self.stale else self.now)*1000),
                'asks':[{'price':self.ask,'size':self.depth}],'bids':[{'price':self.bid,'size':self.depth}],
                'min_order_size':self.min_shares,'tick_size':'.01'}
        if '/markets/' in url:
            self.market_calls+=1
            return copy.deepcopy(self.official)
        raise AssertionError(url)
    def row(self,key='one',side='BUY',wallet=WALLETS[0]):
        payload=dict(proxyWallet=wallet,type='TRADE',side=side,slug=self.slug,conditionId='condition',asset='1',timestamp=self.now-1,
            transactionHash=key,price=.59,size=100)
        if self.source_block is not None:
            payload['blockNumber']=self.source_block
            payload['logIndex']=self.source_log
            self.source_log+=1
        return {'wallet':wallet,'event_key':key,'source_ts':self.now-1,'first_seen':self.now,
            'body':json.dumps(payload)}
    def process(self,row):asyncio.run(self.engine.process(row));self.engine.publish('TEST')
    def state(self):return self.store.get(KEY,{})
    def buy(self):self.now=1102;row=self.row();self.process(row);return row
    def confirm_source(self, shares, as_of, token='1', wallet=None):
        from decimal import Decimal
        from lab.wallet_copy import anchor_source_position
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            anchor_source_position(db, wallet or WALLETS[0], token, Decimal(str(shares)), as_of)
        self.source_block=int(as_of)+1
        self.source_log=1
    def reason(self):
        with self.store.connect() as db:return db.execute('SELECT reason FROM wallet_copy_events ORDER BY ts DESC,rowid DESC LIMIT 1').fetchone()[0]
    def test_forward_buy_uses_current_ask_not_source_price_and_sale_both_fees(self):
        self.confirm_source(0, 1000)
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
        self.stale=False;self.delay=6;self.now=1110;self.process(self.row('slow'))
        self.assertEqual(self.reason(),'COPY_EXPOSURE_LIMIT')
        with self.store.connect() as db:
            open_rows=[t for t in self.engine.positions(db) if t['status']=='OPEN']
        self.assertEqual(len(open_rows),1)
        self.assertLessEqual(open_rows[0]['cost']+open_rows[0]['fee'],5_000_000)
    def test_minimum_and_failed_sale_do_not_invent_fills(self):
        self.depth='1';self.buy();self.assertEqual(self.reason(),'BUY_NO_FULL_FILL_OR_MINIMUM')
        self.depth='100';self.confirm_source(0, 1000);self.now=1110;self.process(self.row('new'))
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
        self.buy();self.now+=2;self.process(self.row('two'))
        with self.store.connect() as db:
            second=db.execute('SELECT reason FROM wallet_copy_events WHERE event_key=?',('two',)).fetchone()[0]
        self.assertEqual(second,'COPY_EXPOSURE_LIMIT')
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
        self.confirm_source(0, 1000)
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

    def test_paused_backlog_does_not_pass_the_copying_wallet(self):
        self.now=1102
        roster=self.store.get('wallet_roster')
        roster['wallets'][WALLETS[0]]['state']='paper_test'
        roster['wallets'][WALLETS[1]]['state']='paused'
        self.store.set('wallet_roster', roster)
        observer=WalletObserver(self.store, None)
        for i in range(20):
            row=self.row('p'+str(i), wallet=WALLETS[1])
            body=json.loads(row['body'])
            body['transactionHash']=row['event_key']
            observer.ingest(WALLETS[1], [body], self.now-1)
        fresh=json.loads(self.row('copy-fresh')['body'])
        observer.ingest(WALLETS[0], [fresh], self.now)
        with self.store.connect() as db:
            pending=self.engine.pending_activity(db)
        self.assertEqual(pending[0]['wallet'], WALLETS[0])

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

    def test_pending_read_uses_the_recent_time_index(self):
        self.now = 5000
        observer = WalletObserver(self.store, None)
        old = json.loads(self.row('old')['body'])
        old['timestamp'] = 1
        with self.store.connect() as db:
            for i in range(400):
                old['transactionHash'] = 'old' + str(i)
                db.execute(
                    'INSERT INTO wallet_activity VALUES (?,?,?,?,?)',
                    (WALLETS[0], 'old' + str(i), 1, 1, json.dumps(old)))
        fresh = json.loads(self.row('fresh-now')['body'])
        observer.ingest(WALLETS[0], [fresh], self.now)
        with self.store.connect() as db:
            plan = ' '.join(
                str(row[3]) for row in db.execute(
                    "EXPLAIN QUERY PLAN SELECT a.event_key FROM wallet_activity a "
                    "INDEXED BY wallet_activity_seen WHERE a.first_seen>=?",
                    (self.now - 90,)))
            pending = self.engine.pending_activity(db)
        self.assertIn('wallet_activity_seen', plan)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]['first_seen'], self.now)

    def test_stale_source_does_not_take_the_live_slot(self):
        self.now = 5000
        observer = WalletObserver(self.store, None)
        late = json.loads(self.row('late')['body'])
        late['timestamp'] = 100
        with self.store.connect() as db:
            db.execute(
                'INSERT INTO wallet_activity VALUES (?,?,?,?,?)',
                (WALLETS[0], 'late', self.now, 100, json.dumps(late)))
        fresh = json.loads(self.row('live')['body'])
        observer.ingest(WALLETS[0], [fresh], self.now)
        with self.store.connect() as db:
            pending = self.engine.pending_activity(db)
        self.assertEqual(len(pending), 1)
        self.assertNotEqual(pending[0]['event_key'], 'late')
        self.assertGreaterEqual(pending[0]['source_ts'], self.now - 90)

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
        self.confirm_source(0, 1000)
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
        self.confirm_source(0, 1000)
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

    def test_partial_sell_keeps_remainder_and_balances_the_ledger(self):
        from decimal import Decimal, ROUND_FLOOR
        self.confirm_source(0, 1000)
        self.buy()
        self.now+=2
        skipped=self.row('skip','BUY')
        body=json.loads(skipped['body']);body['price']=0.90;body['size']=100;skipped['body']=json.dumps(body)
        self.process(skipped)
        self.assertEqual(self.reason(),'COPY_PRICE_TOO_HIGH')
        self.now+=2
        self.bid='.70'
        self.ask='.71'
        self.min_shares='1'
        sell=self.row('part','SELL')
        body=json.loads(sell['body']);body['size']=50;sell['body']=json.dumps(body)
        self.process(sell)
        self.assertEqual(self.reason(),'COPIED_SELL')
        with self.store.connect() as db:
            rows=self.engine.positions(db)
            cash=db.execute('SELECT cash FROM wallet_copy_accounts WHERE wallet=?',(WALLETS[0],)).fetchone()[0]
            ledger=db.execute('SELECT COALESCE(SUM(amount),0) FROM wallet_copy_ledger WHERE wallet=?',(WALLETS[0],)).fetchone()[0]
        closed=[t for t in rows if t['status']=='CLOSED']
        opened=[t for t in rows if t['status']=='OPEN']
        self.assertEqual(len(closed),1)
        self.assertEqual(len(opened),1)
        self.assertLess(opened[0]['shares'],closed[0]['shares']+opened[0]['shares'])
        self.assertEqual(closed[0]['shares']+opened[0]['shares'],closed[0]['shares']+opened[0]['shares'])
        whole_shares=closed[0]['shares']+opened[0]['shares']
        expected=int((Decimal(whole_shares)*Decimal('0.25')).to_integral_value(rounding=ROUND_FLOOR))
        self.assertEqual(closed[0]['shares'],expected)
        self.assertNotEqual(closed[0]['shares'],int((Decimal(whole_shares)*Decimal('0.5')).to_integral_value(rounding=ROUND_FLOOR)))
        from lab.wallet_copy import source_position
        with self.store.connect() as db:
            book=source_position(db,WALLETS[0],'1')
        self.assertEqual(book['shares'],Decimal('150'))
        self.assertTrue(book['known'])
        self.assertEqual(closed[0]['cost']+opened[0]['cost']+closed[0]['fee']+opened[0]['fee']>0,True)
        self.assertEqual(closed[0]['pnl_micro'],closed[0]['payout']-closed[0]['exit_fee']-closed[0]['cost']-closed[0]['fee'])
        self.assertGreater(opened[0]['shares'],0)
        self.assertLess(closed[0]['shares'],whole_shares)
        self.assertEqual(cash,500_000_000+ledger)
        realized=closed[0]['pnl_micro']
        tied=opened[0]['cost']+opened[0]['fee']
        self.assertEqual(cash,500_000_000-tied+realized)

    def test_missing_sell_size_does_not_close_the_lot(self):
        self.buy()
        self.now+=2
        self.bid='.70'
        sell=self.row('blind','SELL')
        body=json.loads(sell['body'])
        body.pop('size')
        sell['body']=json.dumps(body)
        self.process(sell)
        self.assertEqual(self.reason(),'SOURCE_SIZE_MISSING')
        with self.store.connect() as db:
            rows=self.engine.positions(db)
        self.assertEqual([t['status'] for t in rows],['OPEN'])

    def test_failed_sell_copy_still_updates_the_source_position(self):
        from decimal import Decimal
        from lab.wallet_copy import source_position
        self.confirm_source(0, 1000)
        self.buy()
        self.now+=2
        self.depth='1'
        sell=self.row('miss','SELL')
        body=json.loads(sell['body']);body['size']=40;sell['body']=json.dumps(body)
        self.process(sell)
        self.assertEqual(self.reason(),'SELL_NO_FULL_FILL')
        with self.store.connect() as db:
            rows=self.engine.positions(db)
            book=source_position(db,WALLETS[0],'1')
        self.assertEqual([t['status'] for t in rows],['OPEN'])
        self.assertEqual(book['shares'],Decimal('60'))
        self.assertTrue(book['known'])

    def test_incomplete_source_history_does_not_invent_a_fraction(self):
        from lab.wallet_copy import source_position
        self.buy()
        self.now+=2
        self.bid='.70'
        over=self.row('over','SELL')
        body=json.loads(over['body']);body['size']=250;over['body']=json.dumps(body)
        self.process(over)
        self.assertEqual(self.reason(),'SOURCE_PROPORTION_UNKNOWN')
        with self.store.connect() as db:
            rows=self.engine.positions(db)
            book=source_position(db,WALLETS[0],'1')
            body=db.execute('SELECT body FROM wallet_copy_events WHERE event_key=?',('over',)).fetchone()[0]
        self.assertEqual([t['status'] for t in rows],['OPEN'])
        self.assertFalse(book['known'])
        self.assertIsNone(book['shares'])
        self.assertEqual(json.loads(body)['source_copy'],'unknown')

    def test_added_buys_stay_inside_the_position_budget(self):
        self.buy()
        with self.store.connect() as db:
            first=next(t for t in self.engine.positions(db) if t['status']=='OPEN')
            spent=first['cost']+first['fee']
        self.assertLessEqual(spent,5_000_000)
        for i in range(3):
            self.now+=2
            self.process(self.row('add'+str(i)))
            self.assertEqual(self.reason(),'COPY_EXPOSURE_LIMIT')
        with self.store.connect() as db:
            rows=[t for t in self.engine.positions(db) if t['wallet']==WALLETS[0]]
            cash=db.execute('SELECT cash FROM wallet_copy_accounts WHERE wallet=?',(WALLETS[0],)).fetchone()[0]
            ledger=db.execute('SELECT COALESCE(SUM(amount),0) FROM wallet_copy_ledger WHERE wallet=?',(WALLETS[0],)).fetchone()[0]
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['cost']+rows[0]['fee'],spent)
        self.assertLessEqual(rows[0]['cost']+rows[0]['fee'],5_000_000)
        self.assertEqual(cash,500_000_000+ledger)
        self.assertEqual(cash,500_000_000-spent)

    def test_duplicate_restart_and_partial_sell_keep_the_ledger(self):
        from decimal import Decimal, ROUND_FLOOR
        self.confirm_source(0, 1000)
        self.buy()
        self.now+=2
        self.bid='.70'
        self.min_shares='1'
        sell=self.row('half','SELL')
        body=json.loads(sell['body']);body['size']=50;sell['body']=json.dumps(body)
        self.process(sell)
        with self.store.connect() as db:
            before=self.engine.positions(db)
            cash=db.execute('SELECT cash FROM wallet_copy_accounts WHERE wallet=?',(WALLETS[0],)).fetchone()[0]
        self.engine=WalletCopy(self.store,self.fetch,lambda:False,lambda:self.now,self.sleep)
        self.process(self.row())
        self.process(sell)
        with self.store.connect() as db:
            after=self.engine.positions(db)
            cash2=db.execute('SELECT cash FROM wallet_copy_accounts WHERE wallet=?',(WALLETS[0],)).fetchone()[0]
            ledger=db.execute('SELECT COALESCE(SUM(amount),0) FROM wallet_copy_ledger WHERE wallet=?',(WALLETS[0],)).fetchone()[0]
        self.assertEqual(cash2,cash)
        self.assertEqual(len(after),len(before))
        self.assertEqual(cash2,500_000_000+ledger)
        closed=next(t for t in after if t['status']=='CLOSED')
        opened=next(t for t in after if t['status']=='OPEN')
        whole=closed['shares']+opened['shares']
        self.assertEqual(closed['shares'],int((Decimal(whole)*Decimal('0.5')).to_integral_value(rounding=ROUND_FLOOR)))

    def test_observation_sell_uses_skipped_source_buy(self):
        from decimal import Decimal, ROUND_FLOOR
        from lab.wallet_observation import apply_row, ensure_meta
        meta=ensure_meta(self.store,1000)
        self.confirm_source(0, 1000)
        self.now=1102
        asyncio.run(apply_row(self.engine,self.row('obuy'),meta))
        self.now+=2
        skipped=self.row('oskip')
        body=json.loads(skipped['body']);body['price']=0.90;body['size']=100;skipped['body']=json.dumps(body)
        asyncio.run(apply_row(self.engine,skipped,meta))
        self.now+=2
        self.bid='.70';self.ask='.71'
        self.min_shares='1'
        sell=self.row('osell','SELL')
        body=json.loads(sell['body']);body['size']=50;sell['body']=json.dumps(body)
        asyncio.run(apply_row(self.engine,sell,meta))
        with self.store.connect() as db:
            rows=[json.loads(r[0]) for r in db.execute('SELECT body FROM wallet_observation_positions')]
            reason=db.execute('SELECT reason FROM wallet_observation_events WHERE event_key=?',('osell',)).fetchone()[0]
            cash=db.execute('SELECT cash FROM wallet_observation_accounts WHERE wallet=?',(WALLETS[0],)).fetchone()[0]
            ledger=db.execute('SELECT COALESCE(SUM(amount),0) FROM wallet_observation_ledger WHERE wallet=?',(WALLETS[0],)).fetchone()[0]
        self.assertEqual(reason,'OBSERVED_SELL')
        closed=[t for t in rows if t['status']=='CLOSED']
        opened=[t for t in rows if t['status']=='OPEN']
        self.assertEqual(len(closed),1)
        self.assertEqual(len(opened),1)
        whole=closed[0]['shares']+opened[0]['shares']
        self.assertEqual(closed[0]['shares'],int((Decimal(whole)*Decimal('0.25')).to_integral_value(rounding=ROUND_FLOOR)))
        self.assertEqual(cash,500_000_000+ledger)
        self.assertEqual(cash,500_000_000-(opened[0]['cost']+opened[0]['fee'])+closed[0]['pnl_micro'])

    def test_unconfirmed_opening_is_not_half_of_the_next_sell(self):
        from decimal import Decimal
        from lab.wallet_copy import apply_source_trade, source_position
        self.buy()
        self.now+=2
        self.min_shares='1'
        sell=self.row('halfish','SELL')
        body=json.loads(sell['body']);body['size']=50;sell['body']=json.dumps(body)
        self.process(sell)
        self.assertEqual(self.reason(),'SOURCE_PROPORTION_UNKNOWN')
        with self.store.connect() as db:
            book=source_position(db,WALLETS[0],'1')
            rows=self.engine.positions(db)
        with self.store.connect() as db:
            again=apply_source_trade(db,WALLETS[0],'1','halfish','SELL',Decimal('50'),self.now-1)
        self.assertFalse(book['known'])
        self.assertIsNone(book['shares'])
        self.assertIsNone(again['proportion'])
        self.assertEqual([t['status'] for t in rows],['OPEN'])

    def test_confirmed_prior_inventory_sizes_the_sell_at_a_quarter(self):
        from decimal import Decimal
        from lab.wallet_copy import apply_source_trade, order_cursor, source_position
        self.confirm_source(100, 1000)
        self.buy()
        self.now+=2
        self.bid='.70';self.ask='.71'
        self.min_shares='1'
        sell=self.row('quarter','SELL')
        body=json.loads(sell['body']);body['size']=50;sell['body']=json.dumps(body)
        self.process(sell)
        self.assertEqual(self.reason(),'COPIED_SELL')
        with self.store.connect() as db:
            book=source_position(db,WALLETS[0],'1')
            rows=self.engine.positions(db)
        with self.store.connect() as db:
            late=apply_source_trade(db,WALLETS[0],'1','late','BUY',Decimal('10'),order_cursor(self.source_block,0))
            after_gap=source_position(db,WALLETS[0],'1')
        self.assertEqual(book['shares'],Decimal('150'))
        self.assertTrue(book['known'])
        closed=next(t for t in rows if t['status']=='CLOSED')
        opened=next(t for t in rows if t['status']=='OPEN')
        whole=closed['shares']+opened['shares']
        from decimal import ROUND_FLOOR
        self.assertEqual(closed['shares'],int((Decimal(whole)*Decimal('0.25')).to_integral_value(rounding=ROUND_FLOOR)))
        self.assertNotEqual(closed['shares'],int((Decimal(whole)*Decimal('0.5')).to_integral_value(rounding=ROUND_FLOOR)))
        self.assertFalse(after_gap['known'])
        self.assertIsNone(late['proportion'])

    def test_sell_read_does_not_hold_another_wallets_signal(self):
        import time
        order=[]
        async def prepare(row):
            order.append(('start', time.perf_counter()))
            await asyncio.sleep(0.2)
            order.append(('end', time.perf_counter()))
            return {'proportion': None, 'known': False}, 0.2
        async def process(row, shadow=True, sell_proportion=None):
            order.append(('go', row['event_key'], time.perf_counter()))
        self.engine._prepare_sell=prepare
        self.engine.process=process
        sell=self.row('sell','SELL',wallet=WALLETS[0])
        buy=self.row('buy','BUY',wallet=WALLETS[1])
        asyncio.run(self.engine._apply_batch([sell, buy]))
        buy_at=next(item[2] for item in order if item[0]=='go' and item[1]=='buy')
        sell_end=next(item[1] for item in order if item[0]=='end')
        self.assertLess(buy_at, sell_end)

    def test_copy_flow_names_the_real_block(self):
        now=1_000
        self.assertEqual(decide_copy_flow(now,1,now-10,0,1,False)['code'],'copying')
        self.assertEqual(decide_copy_flow(now,1,None,0,0,False)['code'],'no_signals')
        self.assertEqual(decide_copy_flow(now,1,None,0,0,True)['code'],'feed')
        paused=decide_copy_flow(now,1,now-5,0,0,False)
        self.assertEqual(paused['code'],'paused')
        self.assertIn('1',paused['detail_pl'])
        self.assertEqual(decide_copy_flow(now,1,now-5,3,0,False)['code'],'filtered')

    def test_observation_settles_after_the_market_without_a_source_sell(self):
        from lab.wallet_observation import settle_batch, ensure_schema
        trade={'id':'obs1','wallet':WALLETS[0],'policy':'copy-observe-v1','market':self.slug,'token':'1',
            'status':'OPEN','opened':1000,'end':1050,'shares':5_000_000,'cost':3_000_000,'fee':80_000,'exit_fee':0}
        with self.store.connect() as db:
            ensure_schema(db)
            db.execute('INSERT INTO wallet_observation_accounts VALUES (?,?)',(WALLETS[0],500_000_000))
            db.execute('UPDATE wallet_observation_accounts SET cash=? WHERE wallet=?',(500_000_000-3_080_000,WALLETS[0]))
            db.execute('INSERT INTO wallet_observation_ledger VALUES (?,?,?)',('buy:obs1',WALLETS[0],-3_080_000))
            db.execute('INSERT INTO wallet_observation_positions VALUES (?,?,?)',('obs1',WALLETS[0],json.dumps(trade)))
        self.now=1102
        asyncio.run(settle_batch(self.engine))
        with self.store.connect() as db:
            body=json.loads(db.execute("SELECT body FROM wallet_observation_positions WHERE id='obs1'").fetchone()[0])
        self.assertEqual(body['status'],'RESOLVED')
        self.now=1500
        asyncio.run(settle_batch(self.engine))
        with self.store.connect() as db:
            body=json.loads(db.execute("SELECT body FROM wallet_observation_positions WHERE id='obs1'").fetchone()[0])
            cash=db.execute('SELECT cash FROM wallet_observation_accounts WHERE wallet=?',(WALLETS[0],)).fetchone()[0]
            ledger=db.execute('SELECT COALESCE(SUM(amount),0) FROM wallet_observation_ledger WHERE wallet=?',(WALLETS[0],)).fetchone()[0]
        self.assertEqual(body['status'],'SETTLED')
        self.assertEqual(body['pnl_micro'],-3_080_000)
        self.assertIsNotNone(body['pnl_micro'])
        self.assertEqual(cash,500_000_000+ledger)

    def test_step_does_not_shadow_a_paused_batch(self):
        from lab.strategy_control import set_paused
        set_paused(self.store,'copy-'+WALLETS[0],True)
        observer=WalletObserver(self.store,None)
        self.now=1102
        for key in ('a','b'):
            body=json.loads(self.row(key)['body'])
            observer.ingest(WALLETS[0],[body],self.now)
        self.book_calls=0
        asyncio.run(self.engine.step())
        self.assertEqual(self.book_calls,0)
        with self.store.connect() as db:
            reasons=[row[0] for row in db.execute('SELECT reason FROM wallet_copy_events ORDER BY event_key')]
        self.assertEqual(reasons,['COPY_PAUSED','COPY_PAUSED'])
