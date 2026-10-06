import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from lab.core import Store
from lab.mitch_copy import source_dollars, source_price
from lab.wallet_observer import WalletObserver


WALLET = '0x16217458b59b3458149918058754cd234096b159'


def trade(size, usdc, price, source=None):
    row = {
        'proxyWallet': WALLET, 'type': 'TRADE', 'side': 'BUY', 'asset': 'token-a',
        'transactionHash': '0xabc', 'timestamp': 100, 'size': size, 'usdcSize': usdc, 'price': price,
        'slug': 'btc-updown-15m-1000',
    }
    if source:
        row['_source'] = source
    return row


class ActivityMergeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'lab.db')
        self.observer = WalletObserver(self.store, None)

    def tearDown(self):
        self.temp.cleanup()

    def body(self):
        with self.store.connect() as db:
            raw = db.execute('SELECT body FROM wallet_activity').fetchone()[0]
        return json.loads(raw)

    def test_several_fills_sum_once_and_a_refetch_does_not_add_them_again(self):
        self.observer.ingest(WALLET, [trade('10', '3', '0.30')], 200)
        self.observer.ingest(WALLET, [trade('2', '1', '0.50')], 201)
        self.observer.ingest(WALLET, [trade('2', '1', '0.50')], 202)
        body = self.body()
        self.assertEqual(Decimal(body['size']), Decimal('12'))
        self.assertEqual(Decimal(body['usdcSize']), Decimal('4'))
        self.assertEqual(Decimal(body['price']), Decimal('4') / Decimal('12'))
        self.assertEqual(len(body['_fills']), 2)
        self.assertEqual(source_dollars(body), Decimal('4'))
        self.assertEqual(source_price(body), Decimal('4') / Decimal('12'))
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM wallet_activity').fetchone()[0], 1)

    def test_chain_fast_quote_is_replaced_by_the_confirmed_price(self):
        self.observer.ingest(WALLET, [trade('10', '9.9', '0.99', 'chain_fast')], 200)
        self.assertIsNone(source_dollars(self.body()))
        self.observer.ingest(WALLET, [trade('10', '4.2', '0.42')], 201)
        body = self.body()
        self.assertEqual(source_dollars(body), Decimal('4.2'))
        self.assertEqual(source_price(body), Decimal('0.42'))
        self.assertNotEqual(body.get('_source'), 'chain_fast')
