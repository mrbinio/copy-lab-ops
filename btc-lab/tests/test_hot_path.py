import asyncio
import unittest
from lab.hot_path import cached_book, clear_hot_path, remember_book
from lab.mitch_copy import MitchCopy
from lab.core import Store
from lab.wallet_chain_monitor import confirmed_print, note_market_trade
from lab.worker import Worker
import tempfile
from pathlib import Path


def book(token, now):
    return {
        'asset_id': token, 'timestamp': str(int(now * 1000)),
        'asks': [{'price': '0.45', 'size': '100'}],
        'bids': [{'price': '0.44', 'size': '100'}],
        'min_order_size': '1', 'tick_size': '0.01',
    }


class HotPathTests(unittest.TestCase):
    def setUp(self):
        clear_hot_path()
        note_market_trade.shape_logged = False

    def tearDown(self):
        clear_hot_path()

    def test_a_dropped_feed_keeps_the_last_tick(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        worker = Worker(Store(Path(tmp.name) / 'lab.db'), tmp.name)
        worker.reference = {'source_ts': 10}
        worker.note_feed_down(TimeoutError('timed out during opening handshake'))
        self.assertEqual(worker.reference['source_ts'], 10)
        self.assertIn('TimeoutError', worker.feed_error)

    def test_cached_book_is_used_without_http(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        now = 1_800_000_000
        store = Store(Path(tmp.name) / 'lab.db')
        engine = MitchCopy(store, fetch=lambda url: (_ for _ in ()).throw(AssertionError(url)), clock=lambda: now)
        remember_book('token-a', book('token-a', now), now)
        got = asyncio.run(engine._book('token-a'))
        self.assertEqual(got['asks'][0][0], '0.45')
        self.assertNotIn('error', got)

    def test_pool_wait_is_not_called_http(self):
        from lab.hot_path import measured_call
        import time
        submitted = time.perf_counter() - 0.02

        def slow(_url):
            time.sleep(0.01)
            return {'ok': True}

        raw, stage = measured_call(slow, 'https://clob.polymarket.com/book', submitted)
        self.assertEqual(raw, {'ok': True})
        self.assertGreater(stage['pool_ms'], 10)
        self.assertGreater(stage['http_ms'], 5)
        self.assertLess(stage['http_ms'], stage['pool_ms'] + stage['http_ms'])
        self.assertNotEqual(round(stage['http_ms'], 1), round(stage['pool_ms'] + stage['http_ms'], 1))

    def test_print_without_a_transaction_is_not_his_price(self):
        note_market_trade({'event_type': 'last_trade_price', 'price': '0.4', 'size': '2', 'asset_id': '999'})
        self.assertIsNone(confirmed_print('0xno-hash', '999', 2))

    def test_print_matches_transaction_token_and_size(self):
        note_market_trade({
            'event_type': 'last_trade_price', 'transaction_hash': '0xAbC',
            'price': '0.40', 'size': '2', 'asset_id': '111', 'timestamp': '1800000000',
        })
        got = confirmed_print('0xabc', '111', 2)
        self.assertIsNotNone(got)
        self.assertEqual(got['price'], got['usdc'] / got['size'])
