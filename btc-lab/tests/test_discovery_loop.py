import asyncio
import tempfile
import unittest
from pathlib import Path

from lab.core import Store
from lab.strategy_control import is_paused
from lab.wallet_discovery import WalletDiscovery, screen_activity
from lab.wallet_observer import SEED_WALLETS, get_active_wallets

NEW = '0x' + 'ab' * 20


def prints(wallet, *, price=0.4, size=10.0, span_days=2, late=False, count=12, burst=False):
    start = 1_700_000_000 // 300 * 300
    rows = []
    for i in range(count):
        if burst and i < 7:
            slot = start
            ts = float(start + 30)
        else:
            day = 0 if i < count / 2 else span_days
            slot = start + int(day * 86400) + (i % 6) * 300
            ts = slot + (290 if late else 30)
        rows.append({
            'proxyWallet': wallet,
            'type': 'TRADE',
            'side': 'BUY',
            'slug': f'btc-updown-5m-{slot}',
            'price': price,
            'size': size if i < count - 1 else size,
            'timestamp': ts,
        })
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

    def test_short_history_one_trade_price_and_lateness_are_rejected(self):
        cases = (
            ('too_little_history', prints(NEW, span_days=0)),
            ('one_trade_dominates', [dict(row, size=(1000 if i == 0 else 1)) for i, row in enumerate(prints(NEW))]),
            ('poor_liquidity_or_price_band', prints(NEW, price=0.95)),
            ('cannot_copy_in_time', prints(NEW, late=True)),
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
