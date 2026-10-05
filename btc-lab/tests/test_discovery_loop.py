import asyncio
import tempfile
import unittest
from pathlib import Path

from lab.core import Store
from lab.strategy_control import is_paused
from lab.wallet_discovery import WalletDiscovery, screen_activity
from lab.wallet_observer import SEED_WALLETS, get_active_wallets

NEW = '0x' + 'ab' * 20


def prints(wallet, *, price=0.4, size=10.0, span_days=2, late=False, count=12, burst=False,
           seconds_before_end=None, detected_after=None, after_close=False):
    start = 1_700_000_000 // 300 * 300
    rows = []
    for i in range(count):
        if burst and i < 7:
            slot = start
            ts = float(start + 30)
        else:
            day = 0 if i < count / 2 else span_days
            slot = start + int(day * 86400) + (i % 6) * 300
            if after_close:
                ts = slot + 301
            elif seconds_before_end is not None:
                ts = slot + 300 - seconds_before_end
            else:
                ts = slot + (290 if late else 30)
        row = {
            'proxyWallet': wallet,
            'type': 'TRADE',
            'side': 'BUY',
            'slug': f'btc-updown-5m-{slot}',
            'price': price,
            'size': size if i < count - 1 else size,
            'timestamp': ts,
        }
        if detected_after is not None:
            row['detected_after'] = detected_after
        rows.append(row)
    return rows


def scan(store, rows, leaderboard=None, tape=None):
    def fetch(url):
        if 'activity' in url:
            return rows
        if 'trades' in url:
            return rows if tape is None else tape
        if 'leaderboard' in url:
            return [] if leaderboard is None else leaderboard
        raise AssertionError(url)
    asyncio.run(WalletDiscovery(store, fetch).scan())


class DiscoveryLoopTests(unittest.TestCase):
    def test_tape_wallet_is_observed_not_paper(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d) / 'lab.db')
            scan(store, prints(NEW))
            state = store.get('wallet_discovery')
            cand = next(c for c in state['candidates'] if c['wallet'] == NEW)
            self.assertEqual(cand['source'], 'market_trades')
            self.assertEqual(cand['decision'], 'ADMITTED')
            self.assertEqual(cand['month_reported_pnl'], None)
            self.assertFalse(state['copy_enabled'])
            roster = store.get('wallet_roster')['wallets'][NEW]
            self.assertEqual(roster['state'], 'observed')
            self.assertIn(NEW, get_active_wallets(store))
            self.assertTrue(is_paused(store, 'copy-' + NEW))
            self.assertEqual(store.get('wallet_selection_audit')[-1]['action'], 'discovered')
            self.assertIsNone(cand['copyable_after_costs'])
            self.assertFalse(cand['copyable_after_costs_known'])
            self.assertGreaterEqual(cand['passes_copy_filters_share'], 0.25)

    def test_cut_off_activity_page_is_not_a_young_wallet(self):
        page = prints(NEW, span_days=0, count=12)
        screened = screen_activity(page, history_complete=False)
        self.assertFalse(screened['age_known'])
        self.assertTrue(screened['history_span_is_lower_bound'])
        self.assertNotIn('too_little_history', screened['reject_reasons'])
        self.assertIsNone(screened['copyable_after_costs'])
        self.assertGreaterEqual(screened['passes_copy_filters_share'], 0.25)
        self.assertEqual(screened['decision'], 'ADMITTED')
        complete = screen_activity(page, history_complete=True)
        self.assertIn('too_little_history', complete['reject_reasons'])
        self.assertTrue(complete['age_known'])

    def test_fast_detect_near_the_close_is_not_a_discovery_time_reject(self):
        rows = prints(NEW, seconds_before_end=12, detected_after=0.2)
        screened = screen_activity(rows)
        self.assertNotIn('cannot_copy_in_time', screened['reject_reasons'])
        self.assertEqual(screened['decision'], 'ADMITTED')
        self.assertEqual(screened['passes_copy_filters_share'], 1.0)

    def test_short_history_one_trade_price_and_lateness_are_rejected(self):
        cases = (
            ('too_little_history', prints(NEW, span_days=0)),
            ('one_trade_dominates', [dict(row, size=(1000 if i == 0 else 1)) for i, row in enumerate(prints(NEW))]),
            ('poor_liquidity_or_price_band', prints(NEW, price=0.95)),
            ('cannot_copy_in_time', prints(NEW, after_close=True)),
            ('suspicious_activity', prints(NEW, burst=True)),
        )
        for reason, rows in cases:
            with self.subTest(reason=reason):
                screened = screen_activity(rows)
                self.assertIn(reason, screened['reject_reasons'])
                self.assertEqual(screened['decision'], 'REJECTED')
                with tempfile.TemporaryDirectory() as d:
                    store = Store(Path(d) / 'lab.db')
                    scan(store, rows)
                    self.assertNotIn(NEW, store.get('wallet_roster')['wallets'])
                    audit = store.get('wallet_selection_audit')
                    self.assertTrue(any(row['action'] == 'rejected' and reason in row['reason'] for row in audit))

    def test_leaderboard_without_our_markets_is_not_admitted(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d) / 'lab.db')
            other = '0x' + 'ef' * 20
            board = [{'proxyWallet': other, 'pnl': 50, 'vol': 5000, 'userName': 'board'}]
            activity = [{'type': 'TRADE', 'slug': 'bitcoin-up-or-down-october-3', 'price': 0.4, 'size': 10, 'timestamp': 1}] * 20
            scan(store, activity, leaderboard=board, tape=[])
            cand = store.get('wallet_discovery')['candidates'][0]
            self.assertEqual(cand['status'], 'WRONG_MARKETS')
            self.assertIn('wrong_markets', cand['reject_reasons'])
            self.assertNotIn(other, store.get('wallet_roster')['wallets'])

    def test_seed_already_on_the_roster_is_not_readded(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d) / 'lab.db')
            wallet = SEED_WALLETS[0]
            scan(store, prints(wallet))
            cand = next(c for c in store.get('wallet_discovery')['candidates'] if c['wallet'] == wallet)
            self.assertEqual(cand['decision'], 'already_on_roster')
            self.assertEqual(store.get('wallet_roster')['wallets'][wallet]['state'], 'paper_active')
            self.assertFalse(any(row['action'] == 'rejected' and row['wallet'] == wallet for row in store.get('wallet_selection_audit', [])))
