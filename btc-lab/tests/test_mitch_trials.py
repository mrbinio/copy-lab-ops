import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from lab import mitch_trials as trials
from lab.core import Store

W = '0x' + 'ab' * 20


def row(price='0.40', usdc='8', ts=1000.0, slug='btc-updown-15m-1791000000', side='BUY', tx='0x1'):
    return {'side': side, 'slug': slug, 'price': price, 'usdcSize': usdc, 'timestamp': ts,
            'asset': '777', 'outcome': 'Down', 'transactionHash': tx}


class TrialTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'lab.sqlite')
        self.book = {'asks': [{'price': '0.42', 'size': '100'}, {'price': '0.60', 'size': '100'}]}

    def tearDown(self):
        trials.WALLETS.clear()
        self.tmp.cleanup()

    def test_pick_skips_mitch_and_other_markets(self):
        d = {'passed': [{'wallet': W, 'market': 'BTC 15m', 'copy_90d': 500},
                        {'wallet': '0x' + 'cd' * 20, 'market': 'BTC 5m', 'copy_90d': 900},
                        {'wallet': '0x' + 'ef' * 20, 'market': 'BTC 15m', 'copy_90d': 900}]}
        self.assertEqual(list(trials.pick(d, {'0x' + 'ef' * 20})), [W])

    def test_a_buy_inside_one_second_is_copied_up_to_five_dollars(self):
        r = row(usdc='2')
        self.assertEqual(trials.decide(self.store, lambda t: self.book, W, r, 1000.5, now=1000.5), 'COPIED')
        self.assertEqual(trials.decide(self.store, lambda t: self.book, W, dict(r, transactionHash='0x2', usdcSize='9'), 1000.6,
                                       now=1000.6), 'COPIED')
        self.assertEqual(trials.decide(self.store, lambda t: self.book, W, dict(r, transactionHash='0x3'), 1000.7,
                                       now=1000.7), 'WINDOW_LIMIT')
        with self.store.connect() as db:
            self.assertLessEqual(trials.spent(db, W, r['slug']), Decimal('5'))

    def test_late_and_too_expensive_are_not_copied(self):
        self.assertEqual(trials.decide(self.store, lambda t: self.book, W, row(), 1001.2), 'LATE')
        cheap = row(price='0.20')
        self.assertEqual(trials.decide(self.store, lambda t: self.book, W, cheap, 1000.2), 'NO_LIQUIDITY')

    def test_settle_pays_the_winner(self):
        trials.decide(self.store, lambda t: self.book, W, row(), 1000.5, now=1000.5)
        market = {'closed': True, 'clobTokenIds': json.dumps(['777', '888']), 'outcomePrices': json.dumps(['1', '0'])}
        self.assertEqual(trials.settle(self.store, lambda url: market, now=1791000000 + 900 + 200), 1)
        trials.WALLETS.clear()
        trials.WALLETS[W] = {'label': 'x'}
        s = trials.summary(self.store, now=1791000000 + 1200)
        self.assertGreater(s['wallets'][0]['pnl'], 0)


if __name__ == '__main__':
    unittest.main()
