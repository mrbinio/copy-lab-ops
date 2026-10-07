import unittest
from decimal import Decimal

from lab.order_fill import ORDER_FILLED_TOPIC, fill_for_wallet, parse_order_filled


WALLET = '0x16217458b59b3458149918058754cd234096b159'
OTHER = '0xeda9247a0000000000000000000000005cf589'
TOKEN = 111
SCALE = 10 ** 6


def word(value):
    return format(int(value), '064x')


def log(maker, taker, maker_asset, taker_asset, maker_amount, taker_amount, index='0x1', removed=False):
    return {
        'topics': [
            ORDER_FILLED_TOPIC,
            '0x' + word(1),
            '0x' + word(int(maker, 16)),
            '0x' + word(int(taker, 16)),
        ],
        'data': '0x' + ''.join(word(part) for part in (
            maker_asset, taker_asset, maker_amount, taker_amount, 0,
        )),
        'logIndex': index,
        'transactionHash': '0xabc',
        'removed': removed,
    }


class OrderFillTests(unittest.TestCase):
    def test_a_buy_is_the_collateral_actually_paid(self):
        shares = 2 * SCALE
        usdc = int(Decimal('0.40') * shares)
        parsed = fill_for_wallet([log(WALLET, OTHER, 0, TOKEN, usdc, shares)], WALLET, TOKEN, 2)
        self.assertEqual(parsed['side'], 'BUY')
        self.assertEqual(parsed['price'], Decimal('0.40'))
        self.assertEqual(parsed['size'], Decimal(2))
        self.assertEqual(parsed['usdc'], Decimal('0.80'))
        self.assertEqual(parsed['fills'], 1)

    def test_a_removed_log_and_a_duplicate_index_are_not_extra_fills(self):
        shares = 2 * SCALE
        usdc = int(Decimal('0.40') * shares)
        kept = log(WALLET, OTHER, 0, TOKEN, usdc, shares)
        self.assertIsNone(parse_order_filled(dict(kept, removed=True)))
        parsed = fill_for_wallet([kept, dict(kept), dict(kept, removed=True)], WALLET, TOKEN, 2)
        self.assertEqual(parsed['fills'], 1)
        self.assertEqual(parsed['size'], Decimal(2))

    def test_two_fills_sum_and_the_wrong_wallet_is_ignored(self):
        half = 1 * SCALE
        usdc = int(Decimal('0.40') * half)
        first = log(WALLET, OTHER, 0, TOKEN, usdc, half, '0x1')
        second = log(WALLET, OTHER, 0, TOKEN, usdc, half, '0x2')
        stranger = log(OTHER, WALLET, 0, 999, usdc, half, '0x3')
        parsed = fill_for_wallet([first, second, stranger], WALLET, TOKEN, 2)
        self.assertEqual(parsed['fills'], 2)
        self.assertEqual(parsed['size'], Decimal(2))
        self.assertIsNone(fill_for_wallet([stranger], WALLET, TOKEN, 1))

    def test_a_transfer_size_that_does_not_match_is_not_his_fill(self):
        shares = 2 * SCALE
        usdc = int(Decimal('0.40') * shares)
        self.assertIsNone(fill_for_wallet(
            [log(WALLET, OTHER, 0, TOKEN, usdc, shares)], WALLET, TOKEN, 9,
        ))


if __name__ == '__main__':
    unittest.main()
