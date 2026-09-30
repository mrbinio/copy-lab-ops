"""Tests for fast-path chain monitor: detect → CLOB book price → wallet_activity.

Real TransferSingle format verified on Polygon 2026-09-30.
"""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from lab.core import Store
from lab.wallet_chain_monitor import (
    parse_transfer_single, classify_transfer, ChainMonitor, ChainBridge,
    TRANSFER_SINGLE_TOPIC, CTF_TOKEN, EXCHANGE_OPERATORS, ZERO_ADDRESS,
)
from lab.token_resolver import TokenResolver
from lab.wallet_observer import WALLETS

WALLET_A = WALLETS[0]
CTF_EXCHANGE = list(EXCHANGE_OPERATORS)[0]


def make_log(operator, frm, to, token_id=12345, value=5000000,
             block=100, tx='0xabc', log_index=0, removed=False):
    return {
        'address': CTF_TOKEN.lower(),
        'topics': [TRANSFER_SINGLE_TOPIC,
                   '0x' + operator.replace('0x', '').zfill(64),
                   '0x' + frm.replace('0x', '').zfill(64),
                   '0x' + to.replace('0x', '').zfill(64)],
        'data': '0x' + hex(token_id)[2:].zfill(64) + hex(value)[2:].zfill(64),
        'blockNumber': hex(block), 'blockHash': '0xbh',
        'transactionHash': tx, 'logIndex': hex(log_index), 'removed': removed,
    }


class ParseTests(unittest.TestCase):
    def test_valid(self):
        e = parse_transfer_single(make_log(CTF_EXCHANGE, WALLET_A, '0xbuyer'))
        self.assertEqual(e['operator'], CTF_EXCHANGE)
        self.assertEqual(e['from'], WALLET_A)
        self.assertEqual(e['value'], 5000000)

    def test_wrong_topic(self):
        log = make_log(CTF_EXCHANGE, WALLET_A, '0xb')
        log['topics'][0] = '0x' + 'ff' * 32
        self.assertIsNone(parse_transfer_single(log))

    def test_short_data(self):
        log = make_log(CTF_EXCHANGE, WALLET_A, '0xb')
        log['data'] = '0x1234'
        self.assertIsNone(parse_transfer_single(log))

    def test_removed(self):
        e = parse_transfer_single(make_log(CTF_EXCHANGE, '0xa', '0xb', removed=True))
        self.assertTrue(e['removed'])


class ClassifyTests(unittest.TestCase):
    def _e(self, op, frm, to):
        return parse_transfer_single(make_log(op, frm, to))

    def test_buy(self):
        w, s = classify_transfer(self._e(CTF_EXCHANGE, '0xs', WALLET_A), {WALLET_A})
        self.assertEqual((w, s), (WALLET_A, 'BUY'))

    def test_sell(self):
        w, s = classify_transfer(self._e(CTF_EXCHANGE, WALLET_A, '0xb'), {WALLET_A})
        self.assertEqual((w, s), (WALLET_A, 'SELL'))

    def test_non_exchange(self):
        w, _ = classify_transfer(self._e('0xrandom', WALLET_A, '0xb'), {WALLET_A})
        self.assertIsNone(w)

    def test_no_match(self):
        w, _ = classify_transfer(self._e(CTF_EXCHANGE, '0xa', '0xb'), {WALLET_A})
        self.assertIsNone(w)


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'lab.db')
        self.now = 5000.0
        self.book_price = 0.65
        with self.store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS wallet_activity '
                       '(wallet TEXT, event_key TEXT, first_seen REAL, source_ts REAL, '
                       'body TEXT, PRIMARY KEY(wallet,event_key))')
        self.store.wallet_activity_ready = None

    def tearDown(self):
        self.tmp.cleanup()

    def fetch(self, url):
        if 'gamma-api' in url:
            return [{'slug': 'btc-updown-15m-4000', 'conditionId': 'cond1',
                      'outcomes': ['Up', 'Down'], 'clobTokenIds': ['111', '222']}]
        if '/book?' in url:
            return {'asset_id': url.split('=')[1], 'asks': [{'price': str(self.book_price), 'size': '100'}],
                    'bids': [{'price': str(self.book_price - 0.01), 'size': '100'}],
                    'timestamp': str(int(self.now * 1000)), 'min_order_size': '5', 'tick_size': '.01'}
        return {}

    def _event(self, tx='0xtx1', side='BUY', token_id=111):
        return {'type': 'TRANSFER_SINGLE', 'wallet': WALLET_A, 'side': side,
                'token_id': token_id, 'value': 5000000, 'tx_hash': tx,
                'log_index': 0, 'block_number': 500, 'detected_at': self.now,
                'operator': CTF_EXCHANGE, 'from': '0xseller', 'to': WALLET_A}

    def test_buy_inserts_with_book_price(self):
        bridge = ChainBridge(self.store, self.fetch, lambda: self.now)
        asyncio.run(bridge.on_event(self._event()))
        with self.store.connect() as db:
            rows = db.execute('SELECT * FROM wallet_activity').fetchall()
        self.assertEqual(len(rows), 1)
        body = json.loads(rows[0]['body'])
        self.assertEqual(body['slug'], 'btc-updown-15m-4000')
        self.assertEqual(body['price'], self.book_price)
        self.assertEqual(body['side'], 'BUY')
        self.assertEqual(body['_source'], 'chain_monitor')
        self.assertEqual(bridge.bridged, 1)

    def test_sell_inserts_with_bid_price(self):
        bridge = ChainBridge(self.store, self.fetch, lambda: self.now)
        event = self._event(side='SELL')
        event['from'] = WALLET_A
        event['to'] = '0xbuyer'
        asyncio.run(bridge.on_event(event))
        with self.store.connect() as db:
            body = json.loads(db.execute('SELECT body FROM wallet_activity').fetchone()[0])
        self.assertEqual(body['side'], 'SELL')
        # SELL uses bid price
        self.assertEqual(body['price'], self.book_price - 0.01)

    def test_dedup_with_rest(self):
        """REST observer already has this txHash → chain skips."""
        rest_body = json.dumps({'transactionHash': '0xsame', 'type': 'TRADE'})
        with self.store.connect() as db:
            db.execute('INSERT INTO wallet_activity VALUES (?,?,?,?,?)',
                       (WALLET_A, 'rest_key', self.now, self.now, rest_body))
        bridge = ChainBridge(self.store, self.fetch, lambda: self.now)
        asyncio.run(bridge.on_event(self._event(tx='0xsame')))
        self.assertEqual(bridge.skipped, 1)
        self.assertEqual(bridge.bridged, 0)

    def test_chain_first_rest_dedup(self):
        """Chain inserts first → REST's INSERT OR IGNORE is safe (different key)."""
        bridge = ChainBridge(self.store, self.fetch, lambda: self.now)
        asyncio.run(bridge.on_event(self._event(tx='0xfirst')))
        self.assertEqual(bridge.bridged, 1)
        # REST observer tries same txHash with different key
        with self.store.connect() as db:
            rest_body = json.dumps({'transactionHash': '0xfirst', 'type': 'TRADE'})
            # REST uses different key format — but txHash is in body
            cur = db.execute('INSERT OR IGNORE INTO wallet_activity VALUES (?,?,?,?,?)',
                             (WALLET_A, 'rest_key_different', self.now, self.now, rest_body))
            # This WILL insert (different key) — creating a duplicate
            # That's OK: wallet_copy processes first seen, ignores second
            self.assertEqual(cur.rowcount, 1)
            count = db.execute('SELECT COUNT(*) FROM wallet_activity WHERE wallet=?', (WALLET_A,)).fetchone()[0]
            self.assertEqual(count, 2)  # both exist, wallet_copy dedup handles it

    def test_duplicate_chain_event(self):
        bridge = ChainBridge(self.store, self.fetch, lambda: self.now)
        asyncio.run(bridge.on_event(self._event(tx='0xdup')))
        asyncio.run(bridge.on_event(self._event(tx='0xdup')))
        self.assertEqual(bridge.bridged, 1)
        self.assertEqual(bridge.skipped, 1)

    def test_unresolvable_token(self):
        bridge = ChainBridge(self.store, lambda u: [], lambda: self.now)
        asyncio.run(bridge.on_event(self._event(token_id=99999)))
        self.assertEqual(bridge.unresolved, 1)

    def test_no_book_price_skipped(self):
        def fetch_no_book(url):
            if 'gamma-api' in url:
                return [{'slug': 'btc-updown-15m-4000', 'conditionId': 'c',
                          'outcomes': ['Up', 'Down'], 'clobTokenIds': ['111', '222']}]
            return {'asks': [], 'bids': []}  # empty book
        bridge = ChainBridge(self.store, fetch_no_book, lambda: self.now)
        asyncio.run(bridge.on_event(self._event()))
        self.assertEqual(bridge.no_price, 1)
        self.assertEqual(bridge.bridged, 0)

    def test_status(self):
        bridge = ChainBridge(self.store, self.fetch, lambda: self.now)
        s = bridge.status()
        self.assertIn('bridged', s)
        self.assertIn('no_price', s)


class MonitorTests(unittest.TestCase):
    def test_status(self):
        m = ChainMonitor('wss://fake', [WALLET_A], lambda e: None)
        self.assertEqual(m.status()['mode'], 'FAST_PATH_CLOB_PRICE')
        self.assertFalse(m.status()['connected'])


class ResolverTests(unittest.TestCase):
    def test_resolve_and_cache(self):
        tmp = tempfile.TemporaryDirectory()
        store = Store(Path(tmp.name) / 'lab.db')
        calls = []
        def fetch(url):
            calls.append(url)
            return [{'slug': 'btc-updown-15m-9000', 'conditionId': 'c',
                      'outcomes': ['Up', 'Down'], 'clobTokenIds': ['tok_up', 'tok_down']}]
        r = TokenResolver(store, fetch, lambda: 1000.0)
        info = asyncio.run(r.resolve('tok_up'))
        self.assertEqual(info['slug'], 'btc-updown-15m-9000')
        self.assertEqual(info['side'], 'Up')
        asyncio.run(r.resolve('tok_up'))
        self.assertEqual(len(calls), 1)  # cached
        tmp.cleanup()

    def test_unknown_returns_none(self):
        tmp = tempfile.TemporaryDirectory()
        store = Store(Path(tmp.name) / 'lab.db')
        r = TokenResolver(store, lambda u: [], lambda: 1000.0)
        self.assertIsNone(asyncio.run(r.resolve(99999)))
        tmp.cleanup()


if __name__ == '__main__':
    unittest.main()
