import unittest
from decimal import Decimal

from lab.copy_policy import DEVIATION, confirmed_source_price, decide_buy, remember_fill


def book(ask, size='100', extra=None):
    asks = [[str(ask), str(size)]]
    if extra:
        asks.append(extra)
    return {
        'asks': asks, 'bids': [['0.50', '100']], 'min_shares': '5', 'tick': '0.01',
        'fee_rate': '0.07', 'token': '1', 'source_ts': 1000,
    }


class PolicyTests(unittest.TestCase):
    def test_ten_cents_is_inside_and_eleven_is_not(self):
        source = Decimal('0.50')
        why, fill = decide_buy(source, book('0.60'), {})
        self.assertIsNone(why)
        self.assertIsNotNone(fill)
        why, fill = decide_buy(source, book('0.40'), {})
        self.assertIsNone(why)
        why, fill = decide_buy(source, book('0.61'), {})
        self.assertEqual(why, 'SOURCE_PRICE_MOVED')
        self.assertIsNone(fill)
        why, fill = decide_buy(source, book('0.39'), {})
        self.assertEqual(why, 'SOURCE_PRICE_MOVED')
        self.assertEqual(DEVIATION, Decimal('0.10'))

    def test_missing_and_unusable_prices_are_not_taken_from_the_book(self):
        price, why = confirmed_source_price({})
        self.assertIsNone(price)
        self.assertEqual(why, 'SOURCE_PRICE_MISSING')
        price, why = confirmed_source_price({'price': ''})
        self.assertEqual(why, 'SOURCE_PRICE_MISSING')
        price, why = confirmed_source_price({'price': 'nope'})
        self.assertEqual(why, 'SOURCE_PRICE_INVALID')
        price, why = confirmed_source_price({'price': 0.5})
        self.assertEqual(price, Decimal('0.5'))
        self.assertIsNone(why)

    def test_depth_outside_the_band_does_not_complete_the_buy(self):
        source = Decimal('0.50')
        # Five shares are required. The inside level cannot fill them, and the next level is past +10¢.
        why, fill = decide_buy(source, book('0.50', size='6', extra=['0.80', '100']), {})
        self.assertEqual(why, 'BUY_NO_FULL_FILL_OR_MINIMUM')
        self.assertIsNone(fill)

    def test_the_same_snapshot_cannot_fund_a_second_signal(self):
        source = Decimal('0.50')
        snapshot = book('0.50', size='10')
        consumed = {}
        why, fill = decide_buy(source, snapshot, consumed)
        self.assertIsNone(why)
        remember_fill(consumed, snapshot, fill)
        why, again = decide_buy(source, snapshot, consumed)
        self.assertEqual(why, 'BUY_NO_FULL_FILL_OR_MINIMUM')
        self.assertIsNone(again)
