"""Tests for chain monitor: detect on-chain → poll Data API for price → insert.

Key properties tested:
- Source price comes from Data API, not from CLOB book or chain data
- Same key format as REST observer — true dedup, no duplicate entries
- Aggressively polls until trade appears or timeout
- Chain detection that REST already has is skipped
"""
import asyncio
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from lab.core import Store
from lab.wallet_chain_monitor import (
    parse_transfer_single, classify_transfer, ChainBridge,
    TRANSFER_SINGLE_TOPIC, CTF_TOKEN, EXCHANGE_OPERATORS, ZERO_ADDRESS,
)
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
        'blockNumber': hex(block), 'transactionHash': tx,
        'logIndex': hex(log_index), 'removed': removed,
    }


class ParseTests(unittest.TestCase):
    def test_valid(self):
        e = parse_transfer_single(make_log(CTF_EXCHANGE, '0xseller', WALLET_A))
        self.assertIsNotNone(e)
        self.assertEqual(e['to'], WALLET_A)
        self.assertEqual(e['value'], 5000000)

    def test_wrong_topic(self):
        log = make_log(CTF_EXCHANGE, '0xa', '0xb')
        log['topics'][0] = '0x' + 'ff' * 32
        self.assertIsNone(parse_transfer_single(log))

    def test_short_data(self):
        log = make_log(CTF_EXCHANGE, '0xa', '0xb')
        log['data'] = '0x12'
        self.assertIsNone(parse_transfer_single(log))

    def test_removed(self):
        self.assertTrue(parse_transfer_single(make_log(CTF_EXCHANGE, '0xa', '0xb', removed=True))['removed'])


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
        self.assertIsNone(classify_transfer(self._e('0xrand', WALLET_A, '0xb'), {WALLET_A})[0])

    def test_no_match(self):
        self.assertIsNone(classify_transfer(self._e(CTF_EXCHANGE, '0xa', '0xb'), {WALLET_A})[0])


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'lab.db')
        self.now = 5000.0
        with self.store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS wallet_activity '
                       '(wallet TEXT, event_key TEXT, first_seen REAL, source_ts REAL, '
                       'body TEXT, PRIMARY KEY(wallet,event_key))')
        self.store.wallet_activity_ready = None

    def tearDown(self):
        self.tmp.cleanup()

    def _event(self, tx='0xtx1'):
        return {'wallet': WALLET_A, 'side': 'BUY', 'tx_hash': tx,
                'token_id': 111, 'value': 5000000, 'block_number': 500,
                'detected_at': self.now, 'operator': CTF_EXCHANGE,
                'from': '0xseller', 'to': WALLET_A}

    def _api_row(self, tx='0xtx1', price=0.59):
        return {'transactionHash': tx, 'type': 'TRADE', 'side': 'BUY',
                'proxyWallet': WALLET_A, 'timestamp': self.now - 1,
                'slug': 'btc-updown-15m-4000', 'conditionId': 'cond1',
                'asset': '111', 'price': price, 'size': 5.0, 'usdcSize': 2.95,
                'outcomeIndex': 0}

    def test_bridge_inserts_with_confirmed_api_price(self):
        """Chain detects → poll Data API → insert with real source price."""
        api_row = self._api_row(price=0.59)
        def fetch(url):
            if 'activity' in url: return [api_row]
            return []
        bridge = ChainBridge(self.store, fetch, lambda: self.now, sleep=asyncio.sleep)
        asyncio.run(bridge.on_event(self._event()))
        with self.store.connect() as db:
            rows = db.execute('SELECT * FROM wallet_activity').fetchall()
        self.assertEqual(len(rows), 1)
        body = json.loads(rows[0]['body'])
        self.assertEqual(body['price'], 0.59)  # real source price, not book price
        self.assertEqual(body['transactionHash'], '0xtx1')
        self.assertEqual(body['_source'], 'chain_accelerated')
        self.assertEqual(bridge.bridged, 1)

    def test_same_key_as_rest_observer(self):
        """Bridge uses same key format as REST observer — true dedup."""
        api_row = self._api_row()
        fields = {k: api_row.get(k) for k in (
            'transactionHash', 'type', 'asset', 'side', 'size', 'usdcSize',
            'price', 'timestamp', 'conditionId', 'outcomeIndex')}
        expected_key = hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()

        def fetch(url):
            if 'activity' in url: return [api_row]
            return []
        bridge = ChainBridge(self.store, fetch, lambda: self.now, sleep=asyncio.sleep)
        asyncio.run(bridge.on_event(self._event()))
        with self.store.connect() as db:
            row = db.execute('SELECT event_key FROM wallet_activity').fetchone()
        self.assertEqual(row[0], expected_key)

    def test_rest_already_has_tx_skipped(self):
        """If REST observer already inserted this txHash, bridge skips."""
        rest_body = json.dumps({'transactionHash': '0xsame', 'type': 'TRADE', 'price': 0.6})
        with self.store.connect() as db:
            db.execute('INSERT INTO wallet_activity VALUES (?,?,?,?,?)',
                       (WALLET_A, 'rest_key', self.now, self.now, rest_body))
        bridge = ChainBridge(self.store, lambda u: [], lambda: self.now, sleep=asyncio.sleep)
        asyncio.run(bridge.on_event(self._event(tx='0xsame')))
        self.assertEqual(bridge.already_seen, 1)
        self.assertEqual(bridge.bridged, 0)

    def test_rest_after_chain_is_deduped(self):
        """Chain inserts first with same key → REST INSERT OR IGNORE skips."""
        api_row = self._api_row(tx='0xfirst')
        def fetch(url):
            if 'activity' in url: return [api_row]
            return []
        bridge = ChainBridge(self.store, fetch, lambda: self.now, sleep=asyncio.sleep)
        asyncio.run(bridge.on_event(self._event(tx='0xfirst')))
        # REST observer tries to insert same row — same key = IGNORE
        fields = {k: api_row.get(k) for k in (
            'transactionHash', 'type', 'asset', 'side', 'size', 'usdcSize',
            'price', 'timestamp', 'conditionId', 'outcomeIndex')}
        key = hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()
        with self.store.connect() as db:
            cur = db.execute('INSERT OR IGNORE INTO wallet_activity VALUES (?,?,?,?,?)',
                             (WALLET_A, key, self.now, self.now, json.dumps(api_row)))
            self.assertEqual(cur.rowcount, 0)  # deduped!
            count = db.execute('SELECT COUNT(*) FROM wallet_activity').fetchone()[0]
            self.assertEqual(count, 1)  # only one entry

    def test_timeout_when_api_never_returns_tx(self):
        """If Data API never indexes the trade, bridge times out."""
        times = [self.now]
        def clock():
            return times[0]
        def fetch(url):
            if 'activity' in url: return []  # never found
            return []
        async def fast_sleep(s):
            times[0] += s  # advance clock
        bridge = ChainBridge(self.store, fetch, clock, sleep=fast_sleep)
        asyncio.run(bridge.on_event(self._event()))
        self.assertEqual(bridge.timeouts, 1)
        self.assertEqual(bridge.bridged, 0)

    def test_polls_until_found(self):
        """Bridge polls multiple times until Data API has the trade."""
        poll_count = [0]
        api_row = self._api_row()
        times = [self.now]
        def fetch(url):
            if 'activity' in url:
                poll_count[0] += 1
                if poll_count[0] >= 3: return [api_row]  # appears on 3rd poll
                return []
            return []
        async def fast_sleep(s):
            times[0] += s
        bridge = ChainBridge(self.store, fetch, lambda: times[0], sleep=fast_sleep)
        asyncio.run(bridge.on_event(self._event()))
        self.assertEqual(bridge.bridged, 1)
        self.assertGreaterEqual(poll_count[0], 3)

    def test_status(self):
        bridge = ChainBridge(self.store, lambda u: [], lambda: self.now)
        s = bridge.status()
        self.assertIn('bridged', s)
        self.assertIn('timeouts', s)
        self.assertIn('already_seen', s)


if __name__ == '__main__':
    unittest.main()
