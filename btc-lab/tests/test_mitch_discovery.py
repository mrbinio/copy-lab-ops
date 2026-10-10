import unittest
from decimal import Decimal

from lab.mitch_discovery import (
    fee, notional, replay_window, source_window, summarize, trades_by_window, winners_from_redeems,
)


def buy(price, usdc, outcome=0, ts=1):
    p = Decimal(str(price)); u = Decimal(str(usdc))
    return {'ts': ts, 'side': 'BUY', 'outcome': outcome, 'price': p, 'size': u / p, 'usdc': u, 'condition': 'c'}


def sell(price, size, outcome=0, ts=2):
    p = Decimal(str(price)); s = Decimal(str(size))
    return {'ts': ts, 'side': 'SELL', 'outcome': outcome, 'price': p, 'size': s, 'usdc': p * s, 'condition': 'c'}


class ReplayTests(unittest.TestCase):
    def test_mitch_sizing_formula(self):
        self.assertEqual(notional(Decimal(10), 'mitch15'), Decimal(10))
        self.assertEqual(notional(Decimal(55), 'mitch15'), Decimal(17))
        self.assertEqual(notional(Decimal(55), 'lane5'), Decimal(5))

    def test_two_cents_worse_with_fee_and_a_win(self):
        pnl, spent = replay_window([buy(0.40, 10)], 0, 'mitch15')
        price = Decimal('0.42')
        shares = Decimal(10) / (price * (1 + Decimal('0.07') * (1 - price)))
        self.assertAlmostEqual(float(spent), 10, places=6)
        self.assertAlmostEqual(float(pnl), float(shares - 10), places=6)
        loss, _ = replay_window([buy(0.40, 10)], 1, 'mitch15')
        self.assertAlmostEqual(float(loss), -10, places=6)

    def test_window_cap_and_proportional_sell(self):
        items = [buy(0.50, 100), buy(0.50, 100, ts=2)]
        _, spent = replay_window(items, 0, 'mitch15')
        self.assertLessEqual(spent, Decimal(20))
        half = [buy(0.50, 10), sell(0.60, 10, ts=3)]   # he sells half of his 20 shares
        pnl, _ = replay_window(half, 1, 'mitch15')
        self.assertGreater(pnl, Decimal(-10))           # half came back at 0.58

    def test_source_result_and_redeem_winners(self):
        self.assertAlmostEqual(float(source_window([buy(0.25, 5)], 0)), 15.0)
        rows = [{'type': 'REDEEM', 'usdcSize': 3, 'conditionId': 'x', 'outcomeIndex': 1},
                {'type': 'REDEEM', 'usdcSize': 0, 'conditionId': 'y', 'outcomeIndex': 0}]
        self.assertEqual(winners_from_redeems(rows), {'x': 1})

    def test_without_best_window_and_days(self):
        day = 1_791_000_000
        s = summarize([(day, Decimal(100)), (day + 900, Decimal(-30)), (day + 86400, Decimal(-5))], day + 2 * 86400, 30)
        self.assertEqual(s['pnl'], 65.0)
        self.assertEqual(s['pnl_without_best_window'], -35.0)
        self.assertEqual((s['days_up'], s['days_down']), (1, 1))

    def test_only_our_markets_are_grouped(self):
        rows = [{'type': 'TRADE', 'side': 'BUY', 'slug': 'btc-updown-15m-900', 'timestamp': 1, 'outcomeIndex': 0,
                 'price': 0.5, 'size': 2, 'usdcSize': 1, 'conditionId': 'c'},
                {'type': 'TRADE', 'side': 'BUY', 'slug': 'will-x-happen', 'timestamp': 1, 'outcomeIndex': 0,
                 'price': 0.5, 'size': 2, 'usdcSize': 1, 'conditionId': 'd'}]
        self.assertEqual(list(trades_by_window(rows)), ['btc-updown-15m-900'])
        self.assertEqual(fee(Decimal('0.5'), Decimal(10)), Decimal('0.175'))


if __name__ == '__main__':
    unittest.main()
