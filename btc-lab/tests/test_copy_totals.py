import unittest
from lab.copy_totals import summarize, path_stats
from lab.feed_watchdog import next_backoff

class CopyTotalsTests(unittest.TestCase):
    def test_paused_losses_stay_in_history_not_active(self):
        trades=[
            {'wallet':'win','status':'CLOSED','closed_at':10,'pnl_micro':5_000_000,'cost':1,'fee':0},
            {'wallet':'lose','status':'CLOSED','closed_at':11,'pnl_micro':-8_000_000,'cost':1,'fee':0},
            {'wallet':'win','status':'OPEN','cost':2_000_000,'fee':100_000},
        ]
        pauses={'copy-win':False,'copy-lose':True}
        s=summarize(trades,pauses,now=20,observed=4,copy_wallets=['win','lose'])
        self.assertEqual(s['active_net_usd'],5)
        self.assertEqual(s['all_copies_net_usd'],-3)
        self.assertEqual(s['historical_net_usd'],-3)
        self.assertIsNone(s['open_unrealized_usd'])
        self.assertEqual(s['open_count'],1)
        self.assertEqual(s['wallets_active'],1)
        self.assertEqual(s['wallets_paused'],1)
        self.assertTrue(s['separate_books'])

    def test_empty_is_zero_not_missing(self):
        s=summarize([],{},now=1,observed=0)
        self.assertEqual(s['active_net_usd'],0)
        self.assertEqual(s['all_copies_net_usd'],0)
        self.assertEqual(s['open_count'],0)
        self.assertEqual(s['open_unrealized_usd'],0)
        self.assertIn('zero', s['unrealized_reason'])

    def test_omitted_accounts_explain_the_gap(self):
        trades=[
            {'wallet':'listed','status':'SETTLED','closed_at':10,'pnl_micro':1_000_000},
            {'wallet':'old','status':'SETTLED','closed_at':11,'pnl_micro':-2_770_000},
            {'wallet':'old','status':'CLOSED','closed_at':12,'pnl_micro':-100_000},
        ]
        s=summarize(trades,{},now=20,copy_wallets=['listed'])
        self.assertEqual(s['active_net_usd'],1)
        self.assertEqual(s['omitted_net_usd'],-2.87)
        self.assertEqual(s['omitted_trades'],2)
        self.assertAlmostEqual(s['active_net_usd']+s['omitted_net_usd'], s['all_copies_net_usd'])
        self.assertEqual(s['all_copies_net_usd'],-1.87)

    def test_chain_fast_is_not_counted_as_time_from_trade(self):
        from lab.copy_totals import path_record
        event={'_source':'chain_fast','timestamp':1000.2}
        row={'source_ts':1000.2,'first_seen':1000.25}
        path=path_record(event,row,queued_at=1000.4,book_started=1000.4,book_done=1000.5,decided_at=1000.55)
        self.assertIsNone(path['detect_from_trade_ms'])
        self.assertEqual(path['local_insert_lag_ms'],50)
        self.assertEqual(path['clob'],'inactive_paper')
        self.assertIsNone(path['clob_sign_ms'])
        stats=path_stats([path])
        self.assertNotIn('detect_from_trade_ms', stats['stages'])
        self.assertEqual(stats['by_source']['chain_fast']['n'],1)
        self.assertIsNone(path_stats([])['median_ms'])

    def test_reconnect_backoff_grows_then_caps(self):
        self.assertEqual(next_backoff(1), 2)
        self.assertEqual(next_backoff(16), 30)
        self.assertEqual(next_backoff(30), 30)
        self.assertEqual(next_backoff(None), 2)

    def test_path_stats_median_and_p95(self):
        samples=[{'detect_ms':10,'book_ms':40,'total_ms':n} for n in (100,120,130,800)]
        p=path_stats(samples)
        self.assertEqual(p['n'],4)
        self.assertEqual(p['median_ms'],125)
        self.assertEqual(p['p95_ms'],800)
        self.assertEqual(p['slowest_stage'],'book_ms')
