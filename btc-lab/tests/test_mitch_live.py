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
            self.assertIsNone(live.on_buy('w', 'k' * 30, event(), {'vwap': '0.43', 'cost': 1}, Decimal('0.52')))
            self.assertEqual(client.orders, [])

    def test_dry_signs_the_minimum_buy_at_the_paper_cap_and_never_posts(self):
        with tempfile.TemporaryDirectory() as tmp:
            live, client = self.make(tmp, 'dry')
            row = live.on_buy('w', 'k' * 30, event(), {'vwap': '0.43', 'cost': 1}, Decimal('0.523'))
            self.assertEqual(row['status'], 'DRY_SIGNED')
            self.assertEqual(client.posted, [])
            args = client.orders[0]
            self.assertEqual(args.side, 'BUY')
            self.assertEqual(Decimal(str(args.price)), Decimal('0.52'))   # floored to the tick
            self.assertEqual(Decimal(str(args.amount)), Decimal('2.60'))  # paper 1 micro x 1/5 < minimum 5 x 0.52
            self.assertEqual(args.order_type, 'FOK')

    def test_live_needs_the_code_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            live, client = self.make(tmp, 'live')
            row = live.on_buy('w', 'k' * 30, event(), {'vwap': '0.43', 'cost': 1}, Decimal('0.52'))
            self.assertEqual(row['status'], 'ERROR')
            self.assertIn('disabled in code', row['error'])
            self.assertEqual(client.posted, [])

    def test_limits_skip_before_signing(self):
        with tempfile.TemporaryDirectory() as tmp:
            live, client = self.make(tmp, 'dry', client=FakeClient(mos=10))
            row = live.on_buy('w', 'a' * 30, event(), {'vwap': '0.43', 'cost': 1}, Decimal('0.52'))
            self.assertEqual(row['status'], 'SKIPPED_MIN_ABOVE_CAP')  # 10 x 0.52 > 5 USD cap
            row = live.on_buy('w', 'b' * 30, event(), {'vwap': '0.43', 'cost': 1}, Decimal('0.52'), stopped=True)
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
            row = live.on_buy('w', 'c' * 30, event(), {'vwap': '0.43', 'cost': 1}, Decimal('0.52'))
            self.assertEqual(row['status'], 'SKIPPED_EXPOSURE_CAP')


    def test_dry_sell_mirrors_the_paper_fraction_of_what_was_signed(self):
        with tempfile.TemporaryDirectory() as tmp:
            live, client = self.make(tmp, 'dry')
            live.on_buy('w', 'd' * 30, event('0.40'), {'vwap': '0.41', 'cost': 1}, Decimal('0.50'))
            row = live.on_sell('w', 'e' * 30, event('0.70'), Decimal('1'), Decimal('0.60'))
            self.assertEqual(row['status'], 'DRY_SIGNED')
            self.assertEqual(row['shares'], '5.00')
            self.assertEqual(client.orders[-1].side, 'SELL')
            half = live.on_sell('w', 'f' * 30, event('0.70'), Decimal('0.5'), Decimal('0.60'))
            self.assertEqual(half['status'], 'SKIPPED_NOTHING_HELD')

    def test_a_partial_sell_under_the_minimum_is_held_to_settlement(self):
        with tempfile.TemporaryDirectory() as tmp:
            live, client = self.make(tmp, 'dry')
            live.on_buy('w', 'g' * 30, event('0.40'), {'vwap': '0.41', 'cost': 1}, Decimal('0.50'))
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
            first = live.on_buy('w', 'z' * 30, event(), {'vwap': '0.43', 'cost': 1}, Decimal('0.52'))
            second = live.on_buy('w', 'z' * 30, event(), {'vwap': '0.43', 'cost': 1}, Decimal('0.52'))
            self.assertEqual(first['status'], 'DRY_SIGNED')
            self.assertIsNone(second)
            self.assertEqual(len(client.orders), 1)


    def test_every_order_is_also_journaled_outside_the_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            live, _ = self.make(tmp, 'dry')
            live.on_buy('w', 'q' * 30, event(), {'vwap': '0.43', 'cost': 1}, Decimal('0.52'))
            lines = (Path(tmp) / 'logs' / 'live-orders.jsonl').read_text().splitlines()
            self.assertEqual(json.loads(lines[-1])['status'], 'DRY_SIGNED')


if __name__ == '__main__':
    unittest.main()
