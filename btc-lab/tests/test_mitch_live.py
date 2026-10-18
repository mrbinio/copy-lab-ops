import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from lab import mitch_live
from lab.core import Store


class Now:
    def __init__(self, at):
        self.at = at

    def __call__(self):
        return self.at


class FakeClient:
    def __init__(self, mos=5, tick='0.01'):
        self.mos, self.tick = mos, tick
        self.orders, self.posted = [], []

    def get_clob_market_info(self, condition):
        return {'mos': self.mos, 'mts': self.tick, 't': [{'t': 'tok'}]}

    def create_market_order(self, args):
        self.orders.append(args)
        return {'signed': True, 'args': args}

    def post_order(self, order, order_type):
        self.posted.append(order)
        return {'success': True, 'status': 'matched', 'makingAmount': '1.5', 'takingAmount': '3.0'}

    def create_or_derive_api_key(self):
        return 'creds'

    def set_api_creds(self, creds):
        self.creds = creds


class SameThread:
    def submit(self, fn, *args):
        return fn(*args)


def event(price='0.42'):
    return {'slug': 'btc-updown-15m-1792200000', 'asset': 'tok', 'conditionId': '0xc',
            'price': price, 'timestamp': 1792200100.0}


class MitchLiveTests(unittest.TestCase):
    def make(self, tmp, mode, client=None, **settings):
        root = Path(tmp)
        (root / 'data').mkdir(exist_ok=True)
        (root / 'data' / 'mitch_live.json').write_text(json.dumps(dict(settings, mode=mode)))
        store = Store(root / 'data' / 'lab.sqlite')
        client = client or FakeClient()
        live = mitch_live.MitchLive(store, root, clock=Now(1792200100.5),
                                    client_factory=lambda: client, pool=SameThread())
        return live, client

    def test_off_does_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            live, client = self.make(tmp, 'off')
            self.assertIsNone(live.on_buy('w', 'k' * 30, event(), {'vwap': '0.43', 'cost': 13_000_000}, Decimal('0.52')))
            self.assertEqual(client.orders, [])

    def test_dry_signs_the_minimum_buy_at_the_paper_cap_and_never_posts(self):
        with tempfile.TemporaryDirectory() as tmp:
            live, client = self.make(tmp, 'dry')
            row = live.on_buy('w', 'k' * 30, event(), {'vwap': '0.43', 'cost': 13_000_000}, Decimal('0.523'))
            self.assertEqual(row['status'], 'DRY_SIGNED')
            self.assertEqual(client.posted, [])
            args = client.orders[0]
            self.assertEqual(args.side, 'BUY')
            self.assertEqual(Decimal(str(args.price)), Decimal('0.52'))   # floored to the tick
            self.assertEqual(Decimal(str(args.amount)), Decimal('2.60'))  # paper 13 x 1/5 = minimum 5 x 0.52
            self.assertEqual(args.order_type, 'FOK')

    def test_live_needs_the_code_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            live, client = self.make(tmp, 'live')
            row = live.on_buy('w', 'k' * 30, event(), {'vwap': '0.43', 'cost': 13_000_000}, Decimal('0.52'))
            self.assertEqual(row['status'], 'ERROR')
            self.assertIn('disabled in code', row['error'])
            self.assertEqual(client.posted, [])

    def test_limits_skip_before_signing(self):
        with tempfile.TemporaryDirectory() as tmp:
            live, client = self.make(tmp, 'dry', client=FakeClient(mos=10))
            row = live.on_buy('w', 'a' * 30, event(), {'vwap': '0.43', 'cost': 13_000_000}, Decimal('0.52'))
            self.assertEqual(row['status'], 'SKIPPED_MIN_ABOVE_CAP')  # 10 x 0.52 > 5 USD cap
            row = live.on_buy('w', 'b' * 30, event(), {'vwap': '0.43', 'cost': 13_000_000}, Decimal('0.52'), stopped=True)
            self.assertEqual(row['status'], 'SKIPPED_STOP')
            self.assertEqual(client.orders, [])

    def test_a_config_cannot_raise_the_hard_caps(self):
        with tempfile.TemporaryDirectory() as tmp:
            live, _ = self.make(tmp, 'dry', max_order_usd='500', max_exposure_usd='1000')
            s = live.settings()
            self.assertEqual(s['max_order_usd'], mitch_live.MAX_ORDER_USD)
            self.assertEqual(s['max_exposure_usd'], mitch_live.MAX_EXPOSURE_USD)

    def test_exposure_cap_counts_open_filled_buys(self):
        with tempfile.TemporaryDirectory() as tmp:
            live, client = self.make(tmp, 'dry', max_exposure_usd='4')
            live._save({'id': 'x', 'paper_key': 'x', 'side': 'BUY', 'status': 'FILLED', 'spent_usd': '2.0'})
            row = live.on_buy('w', 'c' * 30, event(), {'vwap': '0.43', 'cost': 13_000_000}, Decimal('0.52'))
            self.assertEqual(row['status'], 'SKIPPED_EXPOSURE_CAP')


    def test_dry_sell_mirrors_the_paper_fraction_of_what_was_signed(self):
        with tempfile.TemporaryDirectory() as tmp:
            live, client = self.make(tmp, 'dry')
            live.on_buy('w', 'd' * 30, event('0.40'), {'vwap': '0.41', 'cost': 12_500_000}, Decimal('0.50'))
            row = live.on_sell('w', 'e' * 30, event('0.70'), Decimal('1'), Decimal('0.60'))
            self.assertEqual(row['status'], 'DRY_SIGNED')
            self.assertEqual(row['shares'], '5.00')
            self.assertEqual(client.orders[-1].side, 'SELL')
            half = live.on_sell('w', 'f' * 30, event('0.70'), Decimal('0.5'), Decimal('0.60'))
            self.assertEqual(half['status'], 'SKIPPED_NOTHING_HELD')

    def test_a_partial_sell_under_the_minimum_is_held_to_settlement(self):
        with tempfile.TemporaryDirectory() as tmp:
            live, client = self.make(tmp, 'dry')
            live.on_buy('w', 'g' * 30, event('0.40'), {'vwap': '0.41', 'cost': 12_500_000}, Decimal('0.50'))
            row = live.on_sell('w', 'h' * 30, event('0.70'), Decimal('0.4'), Decimal('0.60'))
            self.assertEqual(row['status'], 'HELD_BELOW_MIN')


    def test_a_buy_is_one_fifth_of_the_paper_amount(self):
        with tempfile.TemporaryDirectory() as tmp:
            live, client = self.make(tmp, 'dry')
            row = live.on_buy('w', 'i' * 30, event('0.20'), {'vwap': '0.21', 'cost': 15_000_000}, Decimal('0.30'))
            self.assertEqual(row['amount_usd'], '3.00')            # 15 USD on paper -> 3 USD live
            row = live.on_buy('w', 'j' * 30, event('0.20'), {'vwap': '0.21', 'cost': 40_000_000}, Decimal('0.30'))
            self.assertEqual(row['amount_usd'], '5')               # 8 USD wanted, capped at 5 an order


    def test_the_same_paper_buy_is_one_live_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            live, client = self.make(tmp, 'dry')
            first = live.on_buy('w', 'z' * 30, event(), {'vwap': '0.43', 'cost': 13_000_000}, Decimal('0.52'))
            second = live.on_buy('w', 'z' * 30, event(), {'vwap': '0.43', 'cost': 13_000_000}, Decimal('0.52'))
            self.assertEqual(first['status'], 'DRY_SIGNED')
            self.assertIsNone(second)
            self.assertEqual(len(client.orders), 1)


    def test_every_order_is_also_journaled_outside_the_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            live, _ = self.make(tmp, 'dry')
            live.on_buy('w', 'q' * 30, event(), {'vwap': '0.43', 'cost': 13_000_000}, Decimal('0.52'))
            lines = (Path(tmp) / 'logs' / 'live-orders.jsonl').read_text().splitlines()
            self.assertEqual(json.loads(lines[-1])['status'], 'DRY_SIGNED')


    def settled_store(self, tmp, winner):
        live, client = self.make(tmp, 'dry')
        live.clock = Now(1792200000 + 900 + 200)        # window ended, settle delay passed
        live.on_buy('w', 'm' * 30, event('0.40'), {'vwap': '0.40', 'cost': 10_000_000}, Decimal('0.50'))
        fetch = lambda url: {'closed': True, 'clobTokenIds': '["tok", "other"]',
                             'outcomePrices': '["1", "0"]' if winner == 'tok' else '["0", "1"]'}
        return live, fetch

    def test_a_dry_win_is_settled_on_the_estimate(self):
        with tempfile.TemporaryDirectory() as tmp:
            live, fetch = self.settled_store(tmp, 'tok')
            self.assertEqual(live.exposure_usd(), Decimal('2.50'))     # 1/5 of 10 USD is under 5 shares x 0.50
            self.assertEqual(live.settle(fetch=fetch), 1)
            res = live.result()
            # 2.50 USD at 0.40 with fee 0.07*0.4*0.6 per share -> 5.99 shares paid 1 each
            self.assertEqual(res['closed'], 1)
            self.assertEqual(res['won'], 1)
            self.assertTrue(res['estimated'])
            self.assertAlmostEqual(float(res['pnl_usd']), 5.99 - 2.50, places=2)
            self.assertEqual(live.exposure_usd(), Decimal(0))
            self.assertEqual(live.settle(fetch=fetch), 0)                # once only

    def test_a_dry_loss_counts_for_the_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            live, fetch = self.settled_store(tmp, 'other')
            live.settle(fetch=fetch)
            self.assertEqual(live.result()['pnl_usd'], '-2.5000')
            self.assertEqual(live.day_loss_usd(), Decimal('2.5000'))

    def test_a_market_minimum_over_twice_paper_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            live, client = self.make(tmp, 'dry')
            # paper 5 USD x 1/5 = 1 USD; the minimum 5 x 0.52 = 2.60 is over 2 USD
            row = live.on_buy('w', 'd' * 30, event(), {'vwap': '0.43', 'cost': 5_000_000}, Decimal('0.52'))
            self.assertEqual(row['status'], 'SKIPPED_MIN_TOO_BIG')
            self.assertEqual(client.orders, [])

    def test_day_loss_starts_at_midnight_and_counts_money_in_play(self):
        with tempfile.TemporaryDirectory() as tmp:
            live, client = self.make(tmp, 'dry')
            now = live.clock()
            live._save({'id': 'y', 'paper_key': 'y', 'side': 'BUY', 'status': 'DRY_SIGNED', 'closed': True,
                        'closed_at': now - 86400, 'pnl_usd': '50'})      # yesterday's gain does not cover today
            live._save({'id': 'z', 'paper_key': 'z', 'side': 'BUY', 'status': 'DRY_SIGNED', 'closed': True,
                        'closed_at': now - 1, 'pnl_usd': '-3'})
            live._save({'id': 'o', 'paper_key': 'o', 'side': 'BUY', 'status': 'DRY_SIGNED', 'amount_usd': '4'})
            self.assertEqual(live.day_loss_usd(), Decimal('7'))
            live, client = self.make(tmp, 'dry', day_loss_stop_usd='7')
            row = live.on_buy('w', 'e' * 30, event(), {'vwap': '0.43', 'cost': 13_000_000}, Decimal('0.52'))
            self.assertEqual(row['status'], 'SKIPPED_DAY_LOSS_STOP')

    def test_an_open_window_is_not_settled(self):
        with tempfile.TemporaryDirectory() as tmp:
            live, fetch = self.settled_store(tmp, 'tok')
            live.clock = Now(1792200000 + 900 + 30)
            self.assertEqual(live.settle(fetch=fetch), 0)


if __name__ == '__main__':
    unittest.main()
