"""Tests for wallet_chain_monitor, ChainToActivityBridge, and TokenResolver."""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from lab.core import Store
from lab.wallet_chain_monitor import (
    parse_order_filled, parse_transfer_single, matches_wallet,
    ChainMonitor, ChainToActivityBridge,
    ORDER_FILLED_TOPIC, TRANSFER_SINGLE_TOPIC,
    CTF_EXCHANGE, NEG_RISK_CTF_EXCHANGE,
)
from lab.token_resolver import TokenResolver

WALLET_A = '0x16217458b59b3458149918058754cd234096b159'
WALLET_B = '0xeda9247a2b3c99a9e0bf46cdac6e1974365cf589'


def make_order_filled_log(maker, taker, maker_asset=111, taker_asset=222,
                          maker_amount=600000, taker_amount=1000000, fee=12000,
                          block=100, tx='0xabc', log_index=0):
    """Build a raw log entry matching OrderFilled event format."""
    order_hash = '0' * 64
    m = maker.lower().replace('0x', '').zfill(64)
    t = taker.lower().replace('0x', '').zfill(64)
    data = '0x' + (
        order_hash +
        m + t +
        hex(maker_asset)[2:].zfill(64) +
        hex(taker_asset)[2:].zfill(64) +
        hex(maker_amount)[2:].zfill(64) +
        hex(taker_amount)[2:].zfill(64) +
        hex(fee)[2:].zfill(64)
    )
    return {
        'address': CTF_EXCHANGE,
        'topics': [ORDER_FILLED_TOPIC],
        'data': data,
        'blockNumber': hex(block),
        'blockHash': '0xblockhash',
        'transactionHash': tx,
        'logIndex': hex(log_index),
    }


class ParseTests(unittest.TestCase):
    def test_parse_order_filled(self):
        log = make_order_filled_log(WALLET_A, WALLET_B, maker_amount=600000, taker_amount=1000000)
        event = parse_order_filled(log)
        self.assertIsNotNone(event)
        self.assertEqual(event['type'], 'ORDER_FILLED')
        self.assertEqual(event['maker'].lower(), WALLET_A)
        self.assertEqual(event['taker'].lower(), WALLET_B)
        self.assertEqual(event['maker_amount'], 600000)
        self.assertEqual(event['taker_amount'], 1000000)
        self.assertEqual(event['block_number'], 100)

    def test_parse_order_filled_wrong_topic(self):
        log = make_order_filled_log(WALLET_A, WALLET_B)
        log['topics'] = ['0xdeadbeef']
        self.assertIsNone(parse_order_filled(log))

    def test_parse_order_filled_short_data(self):
        log = make_order_filled_log(WALLET_A, WALLET_B)
        log['data'] = '0x1234'
        self.assertIsNone(parse_order_filled(log))

    def test_parse_transfer_single(self):
        operator = '0x' + WALLET_A[2:].zfill(64)
        sender = '0x' + '0' * 64  # from zero = mint
        recipient = '0x' + WALLET_B[2:].zfill(64)
        log = {
            'address': '0x4D97DCd97eC945f40cF65F87097ACe5EA0476045',
            'topics': [TRANSFER_SINGLE_TOPIC, operator, sender, recipient],
            'data': '0x' + hex(12345)[2:].zfill(64) + hex(500000)[2:].zfill(64),
            'blockNumber': hex(200),
            'transactionHash': '0xdef',
            'logIndex': hex(1),
        }
        event = parse_transfer_single(log)
        self.assertIsNotNone(event)
        self.assertEqual(event['type'], 'TRANSFER_SINGLE')
        self.assertEqual(event['token_id'], 12345)
        self.assertEqual(event['value'], 500000)


class MatchTests(unittest.TestCase):
    def test_order_filled_matches_maker(self):
        event = {'type': 'ORDER_FILLED', 'maker': WALLET_A, 'taker': '0xother'}
        wallet, role = matches_wallet(event, [WALLET_A, WALLET_B])
        self.assertEqual(wallet, WALLET_A)
        self.assertEqual(role, 'maker')

    def test_order_filled_matches_taker(self):
        event = {'type': 'ORDER_FILLED', 'maker': '0xother', 'taker': WALLET_B}
        wallet, role = matches_wallet(event, [WALLET_A, WALLET_B])
        self.assertEqual(wallet, WALLET_B)
        self.assertEqual(role, 'taker')

    def test_no_match_returns_none(self):
        event = {'type': 'ORDER_FILLED', 'maker': '0xother', 'taker': '0xanother'}
        wallet, role = matches_wallet(event, [WALLET_A])
        self.assertIsNone(wallet)
        self.assertIsNone(role)

    def test_case_insensitive(self):
        event = {'type': 'ORDER_FILLED', 'maker': WALLET_A.upper(), 'taker': '0xother'}
        wallet, role = matches_wallet(event, [WALLET_A])
        self.assertEqual(wallet, WALLET_A)


class ResolverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'lab.db')
        self.now = 1000.0
        self.fetch_calls = []

    def tearDown(self):
        self.tmp.cleanup()

    def make_gamma_response(self, slug='btc-updown-15m-9000', condition='cond123',
                            tokens=('tok_up', 'tok_down')):
        return [{
            'slug': slug,
            'conditionId': condition,
            'outcomes': ['Up', 'Down'],
            'clobTokenIds': [tokens[0], tokens[1]],
        }]

    def fetch(self, url):
        self.fetch_calls.append(url)
        if 'gamma-api' in url and 'tok_up' in url:
            return self.make_gamma_response()
        if 'gamma-api' in url and 'tok_down' in url:
            return self.make_gamma_response()
        return []

    def test_resolve_known_token(self):
        resolver = TokenResolver(self.store, self.fetch, lambda: self.now)
        info = asyncio.run(resolver.resolve('tok_up'))
        self.assertIsNotNone(info)
        self.assertEqual(info['slug'], 'btc-updown-15m-9000')
        self.assertEqual(info['conditionId'], 'cond123')
        self.assertEqual(info['side'], 'Up')
        self.assertEqual(info['status'], 'RESOLVED')

    def test_resolve_unknown_token_returns_none(self):
        def fetch_empty(url):
            return []
        resolver = TokenResolver(self.store, fetch_empty, lambda: self.now)
        info = asyncio.run(resolver.resolve(99999))
        self.assertIsNone(info)

    def test_cache_prevents_second_fetch(self):
        resolver = TokenResolver(self.store, self.fetch, lambda: self.now)
        asyncio.run(resolver.resolve('tok_up'))
        self.assertEqual(len(self.fetch_calls), 1)
        asyncio.run(resolver.resolve('tok_up'))
        self.assertEqual(len(self.fetch_calls), 1)  # still 1, no second fetch

    def test_cache_persists_across_instances(self):
        resolver1 = TokenResolver(self.store, self.fetch, lambda: self.now)
        asyncio.run(resolver1.resolve('tok_up'))
        self.assertEqual(len(self.fetch_calls), 1)
        # New instance, same store
        resolver2 = TokenResolver(self.store, self.fetch, lambda: self.now)
        info = asyncio.run(resolver2.resolve('tok_up'))
        self.assertEqual(len(self.fetch_calls), 1)  # loaded from SQLite
        self.assertEqual(info['slug'], 'btc-updown-15m-9000')

    def test_non_polymarket_token_cached_as_negative(self):
        def fetch_non_pm(url):
            return [{'slug': 'some-other-market', 'conditionId': 'x',
                     'outcomes': ['Yes', 'No'], 'clobTokenIds': ['a', 'b']}]
        resolver = TokenResolver(self.store, fetch_non_pm, lambda: self.now)
        info = asyncio.run(resolver.resolve('a'))
        self.assertIsNone(info)  # Not btc/eth updown
        stats = resolver.cache_stats()
        self.assertEqual(stats['total'], 1)

    def test_cache_stats(self):
        resolver = TokenResolver(self.store, self.fetch, lambda: self.now)
        asyncio.run(resolver.resolve('tok_up'))
        stats = resolver.cache_stats()
        self.assertEqual(stats['resolved'], 1)
        self.assertEqual(stats['memory'], 1)


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'lab.db')
        self.now = 5000.0
        # Create wallet_activity table (normally done by WalletObserver)
        with self.store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS wallet_activity (wallet TEXT, event_key TEXT, first_seen REAL, source_ts REAL, body TEXT, PRIMARY KEY(wallet,event_key))')
        # Bridge __init__ needs asyncio.Event which requires a running loop on Python 3.9.
        # Pre-set the attribute so Bridge skips Event() creation.
        self.store.wallet_activity_ready = None  # placeholder; bridge checks hasattr()

    def tearDown(self):
        self.tmp.cleanup()

    def fetch(self, url):
        if 'gamma-api' in url:
            return [{'slug': 'btc-updown-15m-4000', 'conditionId': 'cond1',
                      'outcomes': ['Up', 'Down'], 'clobTokenIds': ['111', '222']}]
        return []

    def test_order_filled_creates_wallet_activity(self):
        bridge = ChainToActivityBridge(self.store, self.fetch, lambda: self.now)
        event = {
            'type': 'ORDER_FILLED',
            'wallet': WALLET_A,
            'role': 'taker',
            'maker_asset_id': 111,
            'taker_asset_id': 222,
            'maker_amount': 600000,
            'taker_amount': 1000000,
            'tx_hash': '0xtest123',
            'log_index': 0,
            'block_number': 500,
            'detected_at': self.now,
        }
        asyncio.run(bridge.on_chain_event(event))
        with self.store.connect() as db:
            rows = db.execute('SELECT * FROM wallet_activity').fetchall()
        self.assertEqual(len(rows), 1)
        body = json.loads(rows[0]['body'])
        self.assertEqual(body['slug'], 'btc-updown-15m-4000')
        self.assertEqual(body['conditionId'], 'cond1')
        self.assertEqual(body['side'], 'BUY')  # taker = buyer
        self.assertEqual(body['_source'], 'chain_monitor')
        self.assertEqual(bridge.events_bridged, 1)

    def test_duplicate_event_not_inserted_twice(self):
        bridge = ChainToActivityBridge(self.store, self.fetch, lambda: self.now)
        event = {
            'type': 'ORDER_FILLED', 'wallet': WALLET_A, 'role': 'taker',
            'maker_asset_id': 111, 'taker_asset_id': 222,
            'maker_amount': 600000, 'taker_amount': 1000000,
            'tx_hash': '0xdup', 'log_index': 0, 'block_number': 500,
            'detected_at': self.now,
        }
        asyncio.run(bridge.on_chain_event(event))
        asyncio.run(bridge.on_chain_event(event))
        with self.store.connect() as db:
            count = db.execute('SELECT COUNT(*) FROM wallet_activity').fetchone()[0]
        self.assertEqual(count, 1)
        self.assertEqual(bridge.events_bridged, 1)
        self.assertEqual(bridge.events_skipped, 1)

    def test_non_order_event_skipped(self):
        bridge = ChainToActivityBridge(self.store, self.fetch, lambda: self.now)
        event = {'type': 'TRANSFER_SINGLE', 'wallet': WALLET_A}
        asyncio.run(bridge.on_chain_event(event))
        self.assertEqual(bridge.events_skipped, 1)
        self.assertEqual(bridge.events_bridged, 0)

    def test_unresolvable_token_tracked(self):
        def fetch_empty(url):
            return []
        bridge = ChainToActivityBridge(self.store, fetch_empty, lambda: self.now)
        event = {
            'type': 'ORDER_FILLED', 'wallet': WALLET_A, 'role': 'taker',
            'maker_asset_id': 99999, 'taker_asset_id': 88888,
            'maker_amount': 100, 'taker_amount': 200,
            'tx_hash': '0xunk', 'log_index': 0, 'block_number': 500,
            'detected_at': self.now,
        }
        asyncio.run(bridge.on_chain_event(event))
        self.assertEqual(bridge.events_unresolved, 1)
        self.assertEqual(bridge.events_bridged, 0)

    def test_status_includes_resolver_stats(self):
        bridge = ChainToActivityBridge(self.store, self.fetch, lambda: self.now)
        status = bridge.status()
        self.assertIn('resolver_cache', status)
        self.assertIn('events_bridged', status)


class MonitorTests(unittest.TestCase):
    def test_handle_log_dispatches_matching_event(self):
        received = []
        async def on_event(event):
            received.append(event)

        monitor = ChainMonitor('wss://fake', [WALLET_A], on_event)
        log = make_order_filled_log(WALLET_A, '0xother', block=200, tx='0xtx1')
        asyncio.run(monitor._handle_log(log))
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]['wallet'], WALLET_A)
        self.assertEqual(received[0]['role'], 'maker')
        self.assertEqual(monitor.events_matched, 1)

    def test_handle_log_ignores_non_matching(self):
        received = []
        async def on_event(event):
            received.append(event)

        monitor = ChainMonitor('wss://fake', [WALLET_A], on_event)
        log = make_order_filled_log('0xother1', '0xother2')
        asyncio.run(monitor._handle_log(log))
        self.assertEqual(len(received), 0)
        self.assertEqual(monitor.events_seen, 1)
        self.assertEqual(monitor.events_matched, 0)

    def test_status_reports_correctly(self):
        monitor = ChainMonitor('wss://fake', [WALLET_A], lambda e: None)
        status = monitor.status()
        self.assertFalse(status['connected'])
        self.assertEqual(status['events_seen'], 0)


if __name__ == '__main__':
    unittest.main()
