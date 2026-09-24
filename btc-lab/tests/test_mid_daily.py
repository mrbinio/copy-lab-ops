import datetime as dt
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, AsyncMock
from lab.core import Store, simulate_fill, LedgerError
from lab.mid_window import entry, exit_intent, simulate_sale
from lab.daily_report import build_report, bounds, ZONE
from lab.worker import Worker

class MidTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=Store(Path(self.temp.name)/'db')
        self.start=1800000000
        self.market={'start':self.start,'slug':f'btc-updown-15m-{self.start}',
                     'opening':70000,'features':[1,2,0,.5],'fee_rate':.07,
                     'fee_verified':True,'rule_supported':True,'accepting':True,'books':{}}
    def tearDown(self):self.temp.cleanup()
    def book(self,now,bid='.65',ask='.60',size='100'):
        return {'source_ts':now,'bids':[[bid,size]],'asks':[[ask,size]],'min_shares':'5','tick':'.01'}
    def position(self):
        f=simulate_fill([['.60','100']],'5','.60','.07','5','.01')
        self.assertEqual(self.store.open('mid-window-v1',self.market['slug'],'Up',f,{},self.start+200),'FILLED')
        with self.store.connect() as db:return dict(db.execute('SELECT * FROM positions').fetchone())
    def test_entry_boundaries_and_prices(self):
        for elapsed,allowed in [(179.99,False),(180,True),(420,True),(420.01,False)]:
            now=self.start+elapsed
            for price,price_ok in [('.49',False),('.50',True),('.80',True),('.81',False)]:
                self.market['books']={s:self.book(now,bid=str(float(price)-.01),ask=price) for s in ('Up','Down')}
                history=[(now-35+i,70050+i) for i in range(36)]
                intent,_=entry(self.market,{'price':70085},history,now)
                self.assertEqual(bool(intent),allowed and price_ok)
    def test_noise_and_stale_second_book_block(self):
        now=self.start+200;self.market['books']={s:self.book(now,bid='.59') for s in ('Up','Down')}
        hist=[(now-35+i,70050+i) for i in range(36)]
        self.market['books']['Down']['source_ts']=now-4
        self.assertEqual(entry(self.market,{'price':70085},hist,now)[1],'BOOK_STALE')
        self.market['books']['Down']['source_ts']=now
        self.assertIsNone(entry(self.market,{'price':70085},hist[:10],now)[0])
        self.market['features'][1]=.5
        self.assertEqual(entry(self.market,{'price':70085},hist,now)[1],'NORMALIZED_DISTANCE_SMALL')
    def test_sale_both_fees_no_double_settlement_restart(self):
        p=self.position();fill=simulate_sale(self.book(self.start+300),p['shares'],'.07')
        self.assertEqual(self.store.close_paper(p['id'],fill,{},self.start+300),'SOLD')
        self.assertEqual(self.store.close_paper(p['id'],fill,{},self.start+301),'ALREADY_CLOSED')
        self.store.resolve(self.market['slug'],'Up',{'source':'clob_official_winner','closed':True},self.start+1000)
        self.store.redeem(self.start+2000)
        store=Store(self.store.path);store.audit()
        a=next(a for a in store.snapshot()['accounts'] if a['id']=='mid-window-v1')
        expected=(fill['proceeds']-fill['fee']-p['cost']-p['fee'])/1e6
        self.assertAlmostEqual(a['pnl'],expected);self.assertAlmostEqual(a['cash'],500+expected)
        self.assertAlmostEqual(a['fees'],(p['fee']+fill['fee'])/1e6)
    def test_cutoff_unfilled_exit_keeps_full_exposure(self):
        p=self.position();self.market['books']['Up']=self.book(self.start+600)
        self.assertEqual(exit_intent(p,self.market,self.start+600)[1],'HOLD_TO_OFFICIAL_RESOLUTION')
        fill=simulate_sale(self.book(self.start+599),p['shares'],'.07')
        self.assertEqual(self.store.close_paper(p['id'],fill,{},self.start+600),'EXIT_CUTOFF')
        self.assertIsNone(simulate_sale(self.book(self.start+599,size='5'),p['shares'],'.07'))
        self.assertIsNone(simulate_sale(self.book(self.start+599,bid='.64'),p['shares'],'.07',floor='.65'))
        self.assertEqual(self.store.snapshot()['trades'][0]['status'],'OPEN')
    def test_sale_atomic_failure(self):
        p=self.position();f=simulate_sale(self.book(self.start+300),p['shares'],'.07')
        with self.store.connect() as db:db.execute("CREATE TRIGGER fail_sale BEFORE INSERT ON ledger WHEN NEW.kind='PAPER_SALE' BEGIN SELECT RAISE(ABORT,'test'); END")
        with self.assertRaises(sqlite3.IntegrityError):self.store.close_paper(p['id'],f,{},self.start+300)
        self.assertEqual(self.store.snapshot()['trades'][0]['status'],'OPEN');self.store.audit()
    def test_exit_deadline_profit_stop(self):
        p=self.position()
        for elapsed,bid,reason in [(300,'.75','EXIT_PROFIT'),(300,'.40','EXIT_STOP'),(300,'.61','EXIT_HOLD'),(590,'.61','EXIT_DEADLINE')]:
            self.market['books']['Up']=self.book(self.start+elapsed,bid=bid)
            self.assertEqual(exit_intent(p,self.market,self.start+elapsed)[1],reason)
    def test_migration_keeps_existing_cash_and_trades(self):
        f=simulate_fill([['.60','100']],'5','.60','.07','5','.01')
        self.store.open('early-v1','old','Up',f,{},100)
        old=self.store.snapshot()['accounts'][2]['cash']
        with self.store.connect() as db:
            db.execute("DELETE FROM accounts WHERE strategy='mid-window-v1'")
            db.execute('ALTER TABLE positions DROP COLUMN exit_fee')
        reopened=Store(self.store.path);reopened.audit()
        self.assertEqual(reopened.snapshot()['accounts'][2]['cash'],old)
        self.assertEqual(len(reopened.snapshot()['trades']),1)

class ExitCycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_arrival_after_cutoff_cannot_sell(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'db');worker=Worker(store,tmp);start=1800000000
            m={'slug':f'btc-updown-15m-{start}','start':start,'fee_rate':.07,'fee_verified':True,'rule_supported':True,'accepting':True,
               'books':{'Up':{'source_ts':start+599.9,'bids':[['.60','100']],'tick':'.01','min_shares':'5'}}}
            store.open('mid-window-v1',m['slug'],'Up',simulate_fill([['.60','100']],'5','.60','.07','5','.01'),{},start+200)
            worker.books=AsyncMock(return_value=m['books'])
            with patch('lab.worker.time.time',side_effect=[start+599.9,start+600.2,start+600.2]),patch('lab.worker.asyncio.sleep',new_callable=AsyncMock):
                await worker.paper_exits(m,True)
            self.assertEqual(store.snapshot()['trades'][0]['status'],'OPEN')

    async def test_delayed_buy_cannot_cross_seven_minutes(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'db');worker=Worker(store,tmp);start=1800000000
            now=[start+419.9]
            m={'slug':f'btc-updown-15m-{start}','start':start,'end':start+900,'opening':70000,
               'rule_supported':True,'fee_verified':True,'fee_rate':.07,'rule_hash':'test','feature_schema':'spot-v1'}
            worker.market=m;worker.last_registry=now[0];worker.reference={'price':70100,'source_ts':now[0]}
            def book():return {'source_ts':now[0],'asks':[['.60','100']],'bids':[['.59','100']],'min_shares':'5','tick':'.01'}
            async def books(m):return {'Up':book(),'Down':book()}
            worker.books=books
            async def delay(_):now[0]=start+420.2
            def choose(strategy,*args):
                return ({'side':'Up','limit':.61,'probability':None,'strategy':strategy,'market':m['slug']},'SIGNAL') if strategy=='mid-window-v1' else (None,'SKIP')
            with patch('lab.worker.time.time',side_effect=lambda:now[0]),patch('lab.worker.choose',side_effect=choose),patch('lab.worker.asyncio.sleep',side_effect=delay):
                await worker.cycle()
            self.assertFalse(store.snapshot()['trades'])

class DailyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=Store(Path(self.temp.name)/'db')
        self.day=dt.date(2026,9,23);self.start,self.end=bounds(self.day)
    def tearDown(self):self.temp.cleanup()
    def test_day_separates_entry_from_resolution_and_repeats_safely(self):
        f=simulate_fill([['.60','100']],'5','.60','.07','5','.01')
        self.store.open('early-v1','old','Up',f,{},self.start-100)
        self.store.resolve('old','Down',{'source':'clob_official_winner','closed':True},self.start+20)
        self.store.redeem(self.start+400)
        self.store.decide('early-v1','m','RISK_LIMIT',{},self.start+100)
        self.store.record('book',{},self.start+10)
        self.store.set('worker',{'heartbeat':self.end-100,'status':'RECORDING'})
        r=build_report(self.store,str(self.day),self.end+100)
        a=next(x for x in r['daily'] if x['id']=='early-v1')
        self.assertEqual(a['entries'],0);self.assertEqual(a['closed'],1)
        self.assertAlmostEqual(a['net_pnl_usd'],-5.14);self.assertFalse(r['worker_fresh_at_export'])
        self.assertEqual(a['recorded_decisions'][0]['reason'],'RISK_LIMIT')
        self.assertEqual(r['report_id'],build_report(self.store,str(self.day),self.end+200)['report_id'])
        following=build_report(self.store,str(self.day+dt.timedelta(days=1)),self.end+90000)
        self.assertEqual(next(x for x in following['daily'] if x['id']=='early-v1')['net_pnl_usd'],0)
        self.assertEqual(r['accounts'],following['accounts'])
    def test_dst_and_no_partial_day(self):
        self.assertEqual(bounds(dt.date(2026,3,29))[1]-bounds(dt.date(2026,3,29))[0],23*3600)
        self.assertEqual(bounds(dt.date(2026,10,25))[1]-bounds(dt.date(2026,10,25))[0],25*3600)
        with self.assertRaises(ValueError):build_report(self.store,'2026-09-24',self.end+100)
    def test_snapshot_export_is_readonly(self):
        with self.store.connect() as db:before=list(db.iterdump())
        build_report(self.store,str(self.day),self.end+100)
        with self.store.connect() as db:self.assertEqual(before,list(db.iterdump()))
