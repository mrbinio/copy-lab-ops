import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from lab.copy_totals import paper_board, summarize, path_stats
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

    def test_board_keeps_disabled_losses_and_matches_the_journal(self):
        now = datetime(2026, 10, 5, 15, 0, tzinfo=ZoneInfo('Europe/Stockholm')).timestamp()
        yesterday = datetime(2026, 10, 4, 12, 0, tzinfo=ZoneInfo('Europe/Stockholm')).timestamp()
        trades = [
            {'wallet': 'on', 'status': 'SETTLED', 'closed_at': now - 10, 'pnl_micro': 2_000_000, 'cost': 1, 'fee': 1, 'exit_fee': 1, 'opened': now - 20, 'side': 'Up', 'market': 'm'},
            {'wallet': 'off', 'status': 'CLOSED', 'closed_at': yesterday, 'pnl_micro': -5_000_000, 'cost': 1, 'fee': 1, 'exit_fee': 0, 'opened': yesterday - 10, 'side': 'Down', 'market': 'n'},
            {'wallet': 'on', 'status': 'OPEN', 'cost': 100, 'fee': 1},
        ]
        roster = {'wallets': {
            'on': {'state': 'paper_active'},
            'off': {'state': 'paused', 'reason': '7d net <= -15'},
            'idle': {'state': 'paper_test'},
        }}
        pauses = {'copy-off': True, 'copy-on': False, 'copy-idle': False}
        board = paper_board(trades, roster, pauses, now)
        whole = board['periods']['all']
        self.assertEqual(whole['net_micro'], -3_000_000)
        self.assertEqual(sum(row['net_micro'] for row in whole['wallets']), whole['net_micro'])
        self.assertEqual(sum(row['pnl_micro'] for row in board['journal']), whole['net_micro'])
        self.assertEqual(board['periods']['today']['net_micro'], 2_000_000)
        self.assertEqual(board['periods']['today']['closed'], 1)
        idle = next(row for row in board['periods']['today']['wallets'] if row['wallet'] == 'idle')
        self.assertEqual(idle['net_micro'], 0)
        self.assertEqual(idle['closed'], 0)
        self.assertTrue(idle['copying'])
        off = next(row for row in board['periods']['week']['wallets'] if row['wallet'] == 'off')
        self.assertFalse(off['copying'])
        self.assertEqual(off['pause_reason'], '7d net <= -15')
        self.assertEqual(off['net_micro'], -5_000_000)
        self.assertEqual(board['periods']['week']['net_micro'], -3_000_000)
        self.assertIsNone(board['open']['mark_micro'])
        self.assertEqual(board['open']['count'], 1)
        self.assertEqual(board['open']['mark_note'], 'brak aktualnej wyceny')

    def test_missing_pnl_is_not_a_zero(self):
        board = paper_board([
            {'wallet': 'a', 'status': 'SETTLED', 'closed_at': 10, 'pnl_micro': None},
        ], {'wallets': {}}, {}, 20)
        self.assertIsNone(board['periods']['all']['net_micro'])
        self.assertIsNone(board['periods']['all']['wallets'][0]['net_micro'])

    def test_no_open_position_is_a_confirmed_zero_mark(self):
        board = paper_board([], {'wallets': {}}, {}, 20)
        self.assertEqual(board['open']['count'], 0)
        self.assertEqual(board['open']['mark_micro'], 0)
        self.assertEqual(board['periods']['all']['net_micro'], 0)
        self.assertEqual(board['periods']['all']['closed'], 0)

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
