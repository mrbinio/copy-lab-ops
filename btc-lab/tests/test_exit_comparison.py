import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from lab.core import Store
from lab.exit_comparison import ExitComparison, summarize, ARMS

def position(arm='candidate-15-10'):
    return {'source_id':1,'arm':arm,'market':'btc-updown-15m-900','side':'Up',
            'shares':10_000_000,'cost':5_000_000,'entry_fee':175_000,'opened':1080,
            'status':'OPEN','last_checked':1080,'pending':None,'invalid_reasons':[], 'attempts':0}

def market(ts,price='.55',size='100'):
    return {'slug':'btc-updown-15m-900','accepting':True,'rule_supported':True,
            'fee_verified':True,'fee_rate':.07,'books':{'Up':{'source_ts':ts,
            'received_at':ts,'bids':[[price,size]],'tick':'.01','min_shares':'5'}}}

class ExitComparisonTests(unittest.TestCase):
    def test_both_exports_include_comparison_without_changing_account_totals(self):
        from lab.daily_report import build_report
        path=Path(__file__).resolve().parents[1]/'deploy/publish_report_macos.py'
        spec=importlib.util.spec_from_file_location('reporter',path)
        reporter=importlib.util.module_from_spec(spec);spec.loader.exec_module(reporter)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'data').mkdir()
            s=Store(root/'data/lab.sqlite');exp=ExitComparison(s)
            exp.step(market(1080),1080)
            expected=s.get('exit_comparison')
            self.assertEqual(reporter.snapshot(root)['exit_comparison'],expected)
            self.assertEqual(build_report(s)['exit_comparison_cumulative'],expected)
            self.assertTrue(all(a['pnl']==0 for a in reporter.snapshot(root)['accounts']))

    def test_different_stop_same_observation_and_delayed_fill(self):
        a,b=position('baseline-10-20'),position()
        for p in (a,b):ExitComparison.advance(p,market(1082,'.46'),1082)
        self.assertIsNone(a['pending'])
        self.assertEqual(b['pending']['reason'],'STOP')
        ExitComparison.advance(b,market(1082.1,'.46'),1082.1)
        self.assertEqual(b['status'],'OPEN')
        ExitComparison.advance(b,market(1084,'.46'),1084)
        self.assertEqual(b['status'],'SOLD')
        self.assertEqual(b['pnl'],4_600_000-173_880-5_000_000-175_000)
        self.assertEqual(b['latency_seconds'],2)

    def test_fixed_floor_no_fill_on_worse_bid_or_insufficient_depth(self):
        for price,size in [('.45','100'),('.46','19')]:
            p=position();ExitComparison.advance(p,market(1082,'.46'),1082)
            ExitComparison.advance(p,market(1084,price,size),1084)
            self.assertEqual(p['status'],'OPEN');self.assertIsNone(p['pending'])

    def test_no_same_source_or_stale_fill(self):
        p=position();ExitComparison.advance(p,market(1082,'.46'),1082)
        m=market(1084,'.46');m['books']['Up']['source_ts']=1082
        ExitComparison.advance(p,m,1084)
        self.assertEqual(p['status'],'OPEN')
        p=position();ExitComparison.advance(p,market(1070,'.46'),1082)
        self.assertIsNone(p['pending'])

    def test_cutoff_and_gap_invalidate_comparison(self):
        p=position();ExitComparison.advance(p,market(1499,'.46'),1499)
        self.assertIn('OBSERVATION_GAP',p['invalid_reasons'])
        ExitComparison.advance(p,market(1500,'.46'),1500)
        self.assertEqual(p['status'],'OPEN');self.assertIsNone(p['pending'])

    def test_paired_summary_excludes_missing_or_invalid_partner(self):
        a,b=position('baseline-10-20'),position()
        a.update(status='SOLD',closed=1082,pnl=10,exit_fee=20)
        b.update(status='SOLD',closed=1084,pnl=-20,exit_fee=30)
        self.assertEqual(summarize([a])['completed_valid_pairs'],0)
        self.assertEqual(summarize([a,b])['completed_valid_pairs'],1)
        b['invalid_reasons'].append('OBSERVATION_GAP')
        self.assertEqual(summarize([a,b])['completed_valid_pairs'],0)

    def test_restart_duplicate_capture_official_settlement_and_no_cash_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=Store(Path(tmp)/'lab.sqlite');exp=ExitComparison(s)
            fill={'shares':10_000_000,'cost':5_000_000,'fee':175_000}
            self.assertEqual(s.open('mid-window-v1','btc-updown-15m-900','Up',fill,{},1080),'FILLED')
            with s.connect() as db:
                before=[tuple(r) for r in db.execute('SELECT * FROM accounts')]
            exp.capture(market(1080),1080);exp.capture(market(1080),1080)
            exp=ExitComparison(s)
            with s.connect() as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM exit_comparison').fetchone()[0],2)
                db.execute('INSERT INTO labels VALUES (?,?,?,?)',('btc-updown-15m-900','Up',1801,
                           json.dumps({'source':'clob_official_winner','closed':True})))
            exp.step(market(1802),1802)
            rows=s.get('exit_comparison')['rows']
            self.assertTrue(all(r['status']=='SETTLED' and r['pnl']==4_825_000 for r in rows))
            exp.step(market(1804),1804)
            with s.connect() as db:
                self.assertEqual(before,[tuple(r) for r in db.execute('SELECT * FROM accounts')])
                self.assertEqual(db.execute('SELECT COUNT(*) FROM ledger').fetchone()[0],1)

    def test_capture_does_not_backfill_old_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=Store(Path(tmp)/'lab.sqlite');exp=ExitComparison(s)
            s.open('mid-window-v1','btc-updown-15m-900','Up',
                   {'shares':10_000_000,'cost':5_000_000,'fee':175_000},{},1080)
            exp.capture(market(1100),1100)
            with s.connect() as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM exit_comparison').fetchone()[0],0)

if __name__=='__main__':unittest.main()
