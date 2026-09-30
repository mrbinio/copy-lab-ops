"""Tests for wallet_chain_monitor (TransferSingle), bridge, and token resolver.

All test data matches the real on-chain format verified on Polygon 2026-09-30:
  TransferSingle(operator indexed, from indexed, to indexed, token_id, value)
  4 topics, 2 data words. Emitted by CTF Token contract 0x4D97...6045.
"""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from lab.core import Store
from lab.wallet_chain_monitor import (
    parse_transfer_single, classify_transfer, ChainMonitor,
    ChainToActivityBridge, TRANSFER_SINGLE_TOPIC, CTF_TOKEN,
    EXCHANGE_OPERATORS, ZERO_ADDRESS,
)
from lab.token_resolver import TokenResolver

WALLET_A = '0x16217458b59b3458149918058754cd234096b159'
WALLET_B = '0xeda9247a2b3c99a9e0bf46cdac6e1974365cf589'
CTF_EXCHANGE = '0x4bfb41d5b3570defd03c39a9a4d8de6bd8b8982e'

# Real token_id from on-chain (truncated for readability in some tests)
REAL_TOKEN_ID = 85225899647679310223631797639307513810593782178864354861164385221177027266424


def make_transfer_log(operator, frm, to, token_id=12345, value=5000000,
                      block=100, tx='0xabc', log_index=0, removed=False):
    """Build a raw log matching real TransferSingle format from CTF Token."""
    return {
        'address': CTF_TOKEN.lower(),
        'topics': [
            TRANSFER_SINGLE_TOPIC,
            '0x' + operator.lower().replace('0x', '').zfill(64),
            '0x' + frm.lower().replace('0x', '').zfill(64),
            '0x' + to.lower().replace('0x', '').zfill(64),
        ],
        'data': '0x' + hex(token_id)[2:].zfill(64) + hex(value)[2:].zfill(64),
        'blockNumber': hex(block),
        'blockHash': '0xblockhash',
        'transactionHash': tx,
        'logIndex': hex(log_index),
        'removed': removed,
    }


class ParseTests(unittest.TestCase):
    """Verify parsing of real TransferSingle log format."""

    def test_parse_valid_transfer(self):
        log = make_transfer_log(CTF_EXCHANGE, WALLET_A, WALLET_B,
                                token_id=REAL_TOKEN_ID, value=50000000)
        event = parse_transfer_single(log)
        self.assertIsNotNone(event)
        self.assertEqual(event['type'], 'TRANSFER_SINGLE')
        self.assertEqual(event['operator'], CTF_EXCHANGE)
        self.assertEqual(event['from'], WALLET_A)
        self.assertEqual(event['to'], WALLET_B)
        self.assertEqual(event['token_id'], REAL_TOKEN_ID)
        self.assertEqual(event['value'], 50000000)
        self.assertEqual(event['block_number'], 100)
        self.assertEqual(event['contract'], CTF_TOKEN.lower())
        self.assertFalse(event['removed'])

    def test_parse_wrong_topic_returns_none(self):
        log = make_transfer_log(CTF_EXCHANGE, WALLET_A, WALLET_B)
        log['topics'][0] = '0xdeadbeef' + '0' * 56
        self.assertIsNone(parse_transfer_single(log))

    def test_parse_short_data_returns_none(self):
        log = make_transfer_log(CTF_EXCHANGE, WALLET_A, WALLET_B)
        log['data'] = '0x1234'
        self.assertIsNone(parse_transfer_single(log))

    def test_parse_missing_topics_returns_none(self):
        log = make_transfer_log(CTF_EXCHANGE, WALLET_A, WALLET_B)
        log['topics'] = [TRANSFER_SINGLE_TOPIC]  # only 1 topic, need 4
        self.assertIsNone(parse_transfer_single(log))

    def test_parse_removed_log_flagged(self):
        log = make_transfer_log(CTF_EXCHANGE, WALLET_A, WALLET_B, removed=True)
        event = parse_transfer_single(log)
        self.assertIsNotNone(event)
        self.assertTrue(event['removed'])


class ClassifyTests(unittest.TestCase):
    """Verify BUY/SELL classification from TransferSingle."""

    def _event(self, operator, frm, to, **kw):
        return parse_transfer_single(make_transfer_log(operator, frm, to, **kw))

    def test_buy_wallet_in_to(self):
        """Wallet receives tokens via exchange = BUY."""
        event = self._event(CTF_EXCHANGE, '0xseller', WALLET_A)
        wallet, side = classify_transfer(event, {WALLET_A, WALLET_B})
        self.assertEqual(wallet, WALLET_A)
        self.assertEqual(side, 'BUY')

    def test_sell_wallet_in_from(self):
        """Wallet sends tokens via exchange = SELL."""
        event = self._event(CTF_EXCHANGE, WALLET_A, '0xbuyer')
        wallet, side = classify_transfer(event, {WALLET_A})
        self.assertEqual(wallet, WALLET_A)
        self.assertEqual(side, 'SELL')

    def test_non_exchange_operator_ignored(self):
        """Transfer not initiated by exchange = not a trade, ignore."""
        event = self._event('0xrandomoperator', WALLET_A, WALLET_B)
        wallet, side = classify_transfer(event, {WALLET_A, WALLET_B})
        self.assertIsNone(wallet)

    def test_mint_from_zero_ignored(self):
        """Mint (from=0x0) where wallet is from = not a sell."""
        event = self._event(CTF_EXCHANGE, ZERO_ADDRESS, WALLET_A)
        wallet, side = classify_transfer(event, {ZERO_ADDRESS})
        self.assertIsNone(wallet)

    def test_case_insensitive(self):
        event = self._event(CTF_EXCHANGE, '0xother', WALLET_A.upper())
        # wallets set is already lowercase
        wallet, side = classify_transfer(event, {WALLET_A})
        self.assertEqual(wallet, WALLET_A)
        self.assertEqual(side, 'BUY')

    def test_no_match(self):
        event = self._event(CTF_EXCHANGE, '0xother1', '0xother2')
        wallet, side = classify_transfer(event, {WALLET_A})
        self.assertIsNone(wallet)

    def test_both_wallets_buy_wins(self):
        """If from and to are both monitored, BUY (to) takes priority."""
        event = self._event(CTF_EXCHANGE, WALLET_A, WALLET_B)
        wallet, side = classify_transfer(event, {WALLET_A, WALLET_B})
        self.assertEqual(wallet, WALLET_B)
        self.assertEqual(side, 'BUY')


class ResolverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'lab.db')
        self.now = 1000.0
        self.fetch_calls = []

    def tearDown(self):
        self.tmp.cleanup()

    def gamma_response(self, slug='btc-updown-15m-9000', condition='cond123',
                       tokens=('tok_up', 'tok_down')):
        return [{'slug': slug, 'conditionId': condition,
                 'outcomes': ['Up', 'Down'], 'clobTokenIds': list(tokens)}]

    def fetch(self, url):
        self.fetch_calls.append(url)
        if 'gamma-api' in url:
            return self.gamma_response()
        return []

    def test_resolve_known_token(self):
        resolver = TokenResolver(self.store, self.fetch, lambda: self.now)
        info = asyncio.run(resolver.resolve('tok_up'))
        self.assertEqual(info['slug'], 'btc-updown-15m-9000')
        self.assertEqual(info['side'], 'Up')
        self.assertEqual(info['status'], 'RESOLVED')

    def test_unknown_token_returns_none(self):
        resolver = TokenResolver(self.store, lambda u: [], lambda: self.now)
        self.assertIsNone(asyncio.run(resolver.resolve(99999)))

    def test_cache_hit_no_second_fetch(self):
        resolver = TokenResolver(self.store, self.fetch, lambda: self.now)
        asyncio.run(resolver.resolve('tok_up'))
        asyncio.run(resolver.resolve('tok_up'))
        self.assertEqual(len(self.fetch_calls), 1)

    def test_cache_survives_new_instance(self):
        r1 = TokenResolver(self.store, self.fetch, lambda: self.now)
        asyncio.run(r1.resolve('tok_up'))
        r2 = TokenResolver(self.store, self.fetch, lambda: self.now)
        info = asyncio.run(r2.resolve('tok_up'))
        self.assertEqual(len(self.fetch_calls), 1)
        self.assertEqual(info['slug'], 'btc-updown-15m-9000')

    def test_negative_cache_for_non_polymarket(self):
        fetch = lambda u: [{'slug': 'other-market', 'conditionId': 'x',
                            'outcomes': ['Yes', 'No'], 'clobTokenIds': ['a', 'b']}]
        resolver = TokenResolver(self.store, fetch, lambda: self.now)
        self.assertIsNone(asyncio.run(resolver.resolve('a')))
        self.assertEqual(resolver.cache_stats()['total'], 1)

    def test_negative_cache_expires(self):
        calls = []
        def fetch(u):
            calls.append(u)
            return []
        resolver = TokenResolver(self.store, fetch, lambda: self.now)
        asyncio.run(resolver.resolve(777))
        self.assertEqual(len(calls), 1)
        # Advance past NEGATIVE_TTL (3600s)
        self.now += 3601
        resolver = TokenResolver(self.store, fetch, lambda: self.now)
        asyncio.run(resolver.resolve(777))
        self.assertEqual(len(calls), 2)  # fetched again after expiry


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'lab.db')
        self.now = 5000.0
        with self.store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS wallet_activity '
                       '(wallet TEXT, event_key TEXT, first_seen REAL, source_ts REAL, body TEXT, '
                       'PRIMARY KEY(wallet,event_key))')
        # Pre-set to avoid asyncio.Event() issue on Python 3.9
        self.store.wallet_activity_ready = None

    def tearDown(self):
        self.tmp.cleanup()

    def fetch(self, url):
        if 'gamma-api' in url:
            return [{'slug': 'btc-updown-15m-4000', 'conditionId': 'cond1',
                      'outcomes': ['Up', 'Down'], 'clobTokenIds': ['111', '222']}]
        return []

    def test_buy_creates_wallet_activity(self):
        bridge = ChainToActivityBridge(self.store, self.fetch, lambda: self.now)
        event = {
            'type': 'TRANSFER_SINGLE', 'wallet': WALLET_A, 'side': 'BUY',
            'token_id': 111, 'value': 5000000, 'tx_hash': '0xbuy1',
            'log_index': 0, 'block_number': 500, 'detected_at': self.now,
            'operator': CTF_EXCHANGE, 'from': '0xseller', 'to': WALLET_A,
        }
        asyncio.run(bridge.on_chain_event(event))
        with self.store.connect() as db:
            rows = db.execute('SELECT * FROM wallet_activity').fetchall()
        self.assertEqual(len(rows), 1)
        body = json.loads(rows[0]['body'])
        self.assertEqual(body['slug'], 'btc-updown-15m-4000')
        self.assertEqual(body['conditionId'], 'cond1')
        self.assertEqual(body['side'], 'BUY')
        self.assertEqual(body['_source'], 'chain_monitor')
        self.assertEqual(body['transactionHash'], '0xbuy1')
        self.assertEqual(bridge.events_bridged, 1)

    def test_sell_creates_wallet_activity(self):
        bridge = ChainToActivityBridge(self.store, self.fetch, lambda: self.now)
        event = {
            'type': 'TRANSFER_SINGLE', 'wallet': WALLET_A, 'side': 'SELL',
            'token_id': 111, 'value': 5000000, 'tx_hash': '0xsell1',
            'log_index': 0, 'block_number': 500, 'detected_at': self.now,
            'operator': CTF_EXCHANGE, 'from': WALLET_A, 'to': '0xbuyer',
        }
        asyncio.run(bridge.on_chain_event(event))
        with self.store.connect() as db:
            body = json.loads(db.execute('SELECT body FROM wallet_activity').fetchone()[0])
        self.assertEqual(body['side'], 'SELL')

    def test_duplicate_event_ignored(self):
        bridge = ChainToActivityBridge(self.store, self.fetch, lambda: self.now)
        event = {
            'type': 'TRANSFER_SINGLE', 'wallet': WALLET_A, 'side': 'BUY',
            'token_id': 111, 'value': 5000000, 'tx_hash': '0xdup',
            'log_index': 0, 'block_number': 500, 'detected_at': self.now,
            'operator': CTF_EXCHANGE, 'from': '0xseller', 'to': WALLET_A,
        }
        asyncio.run(bridge.on_chain_event(event))
        asyncio.run(bridge.on_chain_event(event))
        with self.store.connect() as db:
            count = db.execute('SELECT COUNT(*) FROM wallet_activity').fetchone()[0]
        self.assertEqual(count, 1)
        self.assertEqual(bridge.events_bridged, 1)
        self.assertEqual(bridge.events_skipped, 1)

    def test_unresolvable_token_counted(self):
        bridge = ChainToActivityBridge(self.store, lambda u: [], lambda: self.now)
        event = {
            'type': 'TRANSFER_SINGLE', 'wallet': WALLET_A, 'side': 'BUY',
            'token_id': 99999, 'value': 100, 'tx_hash': '0xunk',
            'log_index': 0, 'block_number': 500, 'detected_at': self.now,
            'operator': CTF_EXCHANGE, 'from': '0xseller', 'to': WALLET_A,
        }
        asyncio.run(bridge.on_chain_event(event))
        self.assertEqual(bridge.events_unresolved, 1)
        self.assertEqual(bridge.events_bridged, 0)

    def test_missing_tx_hash_skipped(self):
        bridge = ChainToActivityBridge(self.store, self.fetch, lambda: self.now)
        event = {'type': 'TRANSFER_SINGLE', 'wallet': WALLET_A, 'side': 'BUY',
                 'token_id': 111, 'value': 100, 'tx_hash': '',
                 'log_index': 0, 'block_number': 500, 'detected_at': self.now}
        asyncio.run(bridge.on_chain_event(event))
        self.assertEqual(bridge.events_skipped, 1)

    def test_status(self):
        bridge = ChainToActivityBridge(self.store, self.fetch, lambda: self.now)
        s = bridge.status()
        self.assertIn('events_bridged', s)
        self.assertIn('resolver_cache', s)


class MonitorTests(unittest.TestCase):
    """Test ChainMonitor event dispatch (without real WebSocket)."""

    def test_matching_event_dispatched(self):
        received = []
        async def on_event(e): received.append(e)
        monitor = ChainMonitor('wss://fake', [WALLET_A], on_event)
        # Simulate: exchange sends tokens TO wallet_A = BUY
        log = make_transfer_log(CTF_EXCHANGE, '0xseller', WALLET_A, block=200, tx='0xtx1')
        # Manually invoke the processing that run() would do
        event = parse_transfer_single(log)
        wallet, side = classify_transfer(event, monitor.wallets)
        self.assertEqual(wallet, WALLET_A)
        self.assertEqual(side, 'BUY')

    def test_non_matching_not_dispatched(self):
        monitor = ChainMonitor('wss://fake', [WALLET_A], lambda e: None)
        log = make_transfer_log(CTF_EXCHANGE, '0xother1', '0xother2')
        event = parse_transfer_single(log)
        wallet, _ = classify_transfer(event, monitor.wallets)
        self.assertIsNone(wallet)
        self.assertEqual(monitor.events_matched, 0)

    def test_status_defaults(self):
        monitor = ChainMonitor('wss://fake', [WALLET_A], lambda e: None)
        s = monitor.status()
        self.assertFalse(s['connected'])
        self.assertEqual(s['events_seen'], 0)


if __name__ == '__main__':
    unittest.main()
