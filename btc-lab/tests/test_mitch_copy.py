import json
import tempfile
import unittest
from pathlib import Path
from lab.core import Store
from lab.mitch_copy import (
    MitchCopy, WALLETS, copy_notional_usd, price_allows, sell_fraction, our_sell_shares,
)
from lab.wallet_roster import bootstrap


MIHA = '0xa82365c8e854728c472812fba6202ca125386215'
FIRST = '0x16217458b59b3458149918058754cd234096b159'


def asks(price, size='1000'):
    return [(str(price), size)]


class MitchFormulaTests(unittest.TestCase):
    def test_examples(self):
        self.assertEqual(copy_notional_usd(10), 10)
        self.assertEqual(copy_notional_usd(15), 15)
        self.assertEqual(copy_notional_usd(50), 16.75)
        self.assertEqual(copy_notional_usd(100), 19.25)
        self.assertEqual(copy_notional_usd(200), 24.25)

    def test_window_cap_is_separate_from_the_formula(self):
        self.assertGreater(copy_notional_usd(200), 20)

    def test_price_is_one_sided(self):
        self.assertTrue(price_allows('0.50', '0.60'))
        self.assertTrue(price_allows('0.70', '0.60'))
        self.assertFalse(price_allows('0.71', '0.60'))

    def test_unknown_source_book_is_not_a_guess(self):
        self.assertIsNone(sell_fraction(5, None))
        self.assertIsNone(our_sell_shares(1_000_000, None))


class MitchBookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'lab.db')
        self.engine = MitchCopy(self.store, fetch=None, clock=lambda: 1_800_000_000)
        self.engine.ensure()

    def tearDown(self):
        self.tmp.cleanup()

    def event(self, dollars, price='0.50', side='BUY', slug='btc-updown-15m-1790000000'):
        size = dollars / float(price)
        return {
            'type': 'TRADE', 'side': side, 'price': price, 'size': size,
            'usdcSize': dollars, 'slug': slug, 'asset': 'token-a',
            'transactionHash': '0xabc', 'outcome': 'Up',
        }

    def test_buy_uses_the_book_not_the_source_price(self):
        event = self.event(10, '0.40')
        why, fill = self.engine.plan_buy(event, asks('0.45'), '0', '0.01', '1', 20_000_000)
        self.assertIsNone(why)
        self.assertAlmostEqual(fill['vwap'], 0.45, places=2)
        self.assertNotAlmostEqual(fill['vwap'], 0.40, places=2)

    def test_ten_cents_and_one_tick_more(self):
        event = self.event(10, '0.50')
        why, fill = self.engine.plan_buy(event, asks('0.60'), '0', '0.01', '1', 20_000_000)
        self.assertIsNone(why)
        self.assertIsNotNone(fill)
        why, fill = self.engine.plan_buy(event, asks('0.61'), '0', '0.01', '1', 20_000_000)
        self.assertEqual(why, 'PRICE_WORSE_THAN_10C')

    def test_mihaxd_cap_and_addons_share_one_window(self):
        event = self.event(100, '0.50')
        with self.store.connect() as db:
            why, fill = self.engine.plan_buy(event, asks('0.50'), '0', '0.01', '1', 5_000_000)
            self.assertIsNone(why)
            self.assertLessEqual(fill['cost'] + fill['fee'], 5_000_000)
            self.engine.apply_buy(db, MIHA, 'k1', event, fill, {})
            spent = self.engine._window_spent(db, MIHA, event['slug'])
            self.assertGreater(spent, 0)
            why2, _fill2 = self.engine.plan_buy(
                self.event(10, '0.50'), asks('0.50'), '0', '0.01', '1', 0,
            )
            self.assertEqual(why2, 'WINDOW_LIMIT')

    def test_both_directions_share_the_window(self):
        up = self.event(10, '0.40', slug='btc-updown-15m-1790000000')
        down = dict(self.event(10, '0.40'), asset='token-b', outcome='Down', transactionHash='0xdef')
        with self.store.connect() as db:
            _why, fill = self.engine.plan_buy(up, asks('0.40'), '0', '0.01', '1', 20_000_000)
            self.engine.apply_buy(db, FIRST, 'up', up, fill, {})
            _why, fill = self.engine.plan_buy(down, asks('0.40'), '0', '0.01', '1', 20_000_000)
            self.engine.apply_buy(db, FIRST, 'down', down, fill, {})
            self.assertEqual(
                self.engine._window_spent(db, FIRST, up['slug']),
                self.engine._window_spent(db, FIRST, down['slug']),
            )
            self.assertGreater(self.engine._window_spent(db, FIRST, up['slug']), fill['cost'])

    def test_duplicate_transaction_is_not_a_second_buy(self):
        event = self.event(10)
        with self.store.connect() as db:
            _why, fill = self.engine.plan_buy(event, asks('0.50'), '0', '0.01', '1', 20_000_000)
            self.assertEqual(self.engine.apply_buy(db, FIRST, 'k1', event, fill, {}), 'MITCH_BUY')
            self.assertEqual(self.engine.apply_buy(db, FIRST, 'k2', event, fill, {}), 'DUPLICATE')

    def test_partial_sell_after_a_skipped_buy_uses_the_source_book(self):
        with self.store.connect() as db:
            self.engine.anchor_source(db, FIRST, 'token-a', '80')
            event = dict(self.event(10, '0.80'), size=20)
            why, _fill = self.engine.plan_buy(event, asks('0.95'), '0', '0.01', '1', 20_000_000)
            self.assertEqual(why, 'PRICE_WORSE_THAN_10C')
            self.engine.note_source_buy(db, FIRST, event)
            bought = dict(self.event(10, '0.40'), size=20, transactionHash='0xkept')
            _why, fill = self.engine.plan_buy(bought, asks('0.40'), '0', '0.01', '1', 20_000_000)
            self.engine.apply_buy(db, FIRST, 'kept', bought, fill, {})
            sell = dict(bought, side='SELL', size=60, transactionHash='0xsell')
            fraction = self.engine.fraction_for(db, FIRST, sell)
            self.assertAlmostEqual(float(fraction), 0.5, places=2)
            reason = self.engine.apply_sell(
                db, FIRST, 'sell1', sell, asks('0.30'), fraction, {}, False,
            )
            self.assertEqual(reason, 'MITCH_SELL')

    def test_old_pause_does_not_block_mitch_and_mitch_does_not_touch_the_old_ledger(self):
        wallet = FIRST
        state = bootstrap(self.store, now=1_800_000_000)
        state['wallets'][wallet] = {
            'wallet': wallet, 'state': 'paused', 'since': 1, 'reason': 'old pause',
        }
        self.store.set('wallet_roster', state)
        self.store.set('strategy_pauses', {'copy-' + wallet: True})
        event = self.event(10)
        with self.store.connect() as db:
            db.execute('CREATE TABLE wallet_copy_accounts (wallet TEXT PRIMARY KEY, cash INTEGER)')
            db.execute('INSERT INTO wallet_copy_accounts VALUES (?,?)', (wallet, 123))
            _why, fill = self.engine.plan_buy(event, asks('0.50'), '0', '0.01', '1', 20_000_000)
            self.engine.apply_buy(db, wallet, 'm1', event, fill, {})
            cash = db.execute('SELECT cash FROM wallet_copy_accounts WHERE wallet=?', (wallet,)).fetchone()[0]
        self.assertEqual(cash, 123)
        published = self.engine.publish()
        self.assertEqual(published['spec'], 'mitch-copy-wallets-v1')
        self.assertEqual(len(published['wallets']), 5)

    def test_restart_keeps_the_start_and_does_not_replay(self):
        self.store.set('mitch_copy_start', {'at': 100, 'spec': 'mitch-copy-wallets-v1'})
        again = MitchCopy(self.store, fetch=None, clock=lambda: 200)
        again.ensure()
        self.assertEqual(again.started(), 100)


if __name__ == '__main__':
    unittest.main()
