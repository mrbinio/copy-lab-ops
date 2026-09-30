"""Tests for hybrid chain monitor: on-chain detection → REST price.

Chain monitor detects trades (~2-3s) and triggers immediate REST poll.
It does NOT insert into wallet_activity or extract execution price.
Price comes from Data API via wallet_observer.

Real on-chain format (verified Polygon 2026-09-30):
  TransferSingle: 4 topics (sig, operator, from, to), 2 data words (token_id, value)
  Emitted by CTF Token contract 0x4D97...6045
"""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from lab.core import Store
from lab.wallet_chain_monitor import (
    parse_transfer_single, classify_transfer, ChainMonitor,
    TRANSFER_SINGLE_TOPIC, CTF_TOKEN, EXCHANGE_OPERATORS, ZERO_ADDRESS,
)
from lab.wallet_observer import WalletObserver, WALLETS

WALLET_A = WALLETS[0]
WALLET_B = WALLETS[1]
CTF_EXCHANGE = list(EXCHANGE_OPERATORS)[0]


def make_transfer_log(operator, frm, to, token_id=12345, value=5000000,
                      block=100, tx='0xabc', log_index=0, removed=False):
    """Build a raw log matching real TransferSingle format."""
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
        'blockHash': '0xbh',
        'transactionHash': tx,
        'logIndex': hex(log_index),
        'removed': removed,
    }


class ParseTests(unittest.TestCase):
    def test_valid_transfer(self):
        log = make_transfer_log(CTF_EXCHANGE, WALLET_A, WALLET_B, token_id=99999, value=7000000)
        e = parse_transfer_single(log)
        self.assertIsNotNone(e)
        self.assertEqual(e['operator'], CTF_EXCHANGE)
        self.assertEqual(e['from'], WALLET_A)
        self.assertEqual(e['to'], WALLET_B)
        self.assertEqual(e['token_id'], 99999)
        self.assertEqual(e['value'], 7000000)
        self.assertEqual(e['block_number'], 100)
        self.assertFalse(e['removed'])

    def test_wrong_topic(self):
        log = make_transfer_log(CTF_EXCHANGE, WALLET_A, WALLET_B)
        log['topics'][0] = '0x' + 'dead' * 16
        self.assertIsNone(parse_transfer_single(log))

    def test_short_data(self):
        log = make_transfer_log(CTF_EXCHANGE, WALLET_A, WALLET_B)
        log['data'] = '0x1234'
        self.assertIsNone(parse_transfer_single(log))

    def test_missing_topics(self):
        log = make_transfer_log(CTF_EXCHANGE, WALLET_A, WALLET_B)
        log['topics'] = [TRANSFER_SINGLE_TOPIC]
        self.assertIsNone(parse_transfer_single(log))

    def test_removed_flag(self):
        log = make_transfer_log(CTF_EXCHANGE, WALLET_A, WALLET_B, removed=True)
        e = parse_transfer_single(log)
        self.assertTrue(e['removed'])


class ClassifyTests(unittest.TestCase):
    def _event(self, operator, frm, to, **kw):
        return parse_transfer_single(make_transfer_log(operator, frm, to, **kw))

    def test_buy(self):
        e = self._event(CTF_EXCHANGE, '0xseller', WALLET_A)
        w, s = classify_transfer(e, {WALLET_A})
        self.assertEqual(w, WALLET_A)
        self.assertEqual(s, 'BUY')

    def test_sell(self):
        e = self._event(CTF_EXCHANGE, WALLET_A, '0xbuyer')
        w, s = classify_transfer(e, {WALLET_A})
        self.assertEqual(w, WALLET_A)
        self.assertEqual(s, 'SELL')

    def test_non_exchange_ignored(self):
        e = self._event('0xrandom', WALLET_A, WALLET_B)
        w, _ = classify_transfer(e, {WALLET_A, WALLET_B})
        self.assertIsNone(w)

    def test_mint_ignored(self):
        e = self._event(CTF_EXCHANGE, ZERO_ADDRESS, WALLET_A)
        w, _ = classify_transfer(e, {ZERO_ADDRESS})
        self.assertIsNone(w)

    def test_both_wallets_buy_wins(self):
        e = self._event(CTF_EXCHANGE, WALLET_A, WALLET_B)
        w, s = classify_transfer(e, {WALLET_A, WALLET_B})
        self.assertEqual(w, WALLET_B)
        self.assertEqual(s, 'BUY')

    def test_no_match(self):
        e = self._event(CTF_EXCHANGE, '0xa', '0xb')
        w, _ = classify_transfer(e, {WALLET_A})
        self.assertIsNone(w)


class TriggerTests(unittest.IsolatedAsyncioTestCase):
    """Test that chain detection triggers immediate REST poll."""

    async def test_trigger_poll_wakes_observer(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d) / 'lab.db')
            observer = WalletObserver(store, lambda url: [])
            alert = asyncio.Event()
            observer.chain_alerts[WALLET_A] = alert
            self.assertFalse(alert.is_set())
            observer.trigger_poll(WALLET_A)
            self.assertTrue(alert.is_set())

    async def test_trigger_unknown_wallet_safe(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d) / 'lab.db')
            observer = WalletObserver(store, lambda url: [])
            observer.trigger_poll('0xunknown')

    async def test_chain_detection_triggers_observer(self):
        """Full flow: chain detects → on_detection → trigger_poll → alert set."""
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d) / 'lab.db')
            observer = WalletObserver(store, lambda url: [])
            alert = asyncio.Event()
            observer.chain_alerts[WALLET_A] = alert
            detections = []
            async def on_detection(wallet, tx_hash, side, token_id, block_number, detected_at):
                detections.append(side)
                observer.trigger_poll(wallet)
            log = make_transfer_log(CTF_EXCHANGE, '0xseller', WALLET_A, block=500, tx='0xtx1')
            event = parse_transfer_single(log)
            wallet, side = classify_transfer(event, {WALLET_A})
            await on_detection(wallet, event['tx_hash'], side, event['token_id'], 500, 1000.0)
            self.assertEqual(detections, ['BUY'])
            self.assertTrue(alert.is_set())


class MonitorTests(unittest.TestCase):
    def test_status_defaults(self):
        m = ChainMonitor('wss://fake', [WALLET_A], lambda **kw: None)
        s = m.status()
        self.assertEqual(s['mode'], 'HYBRID_DETECTION_ONLY')
        self.assertFalse(s['connected'])
        self.assertEqual(s['events_seen'], 0)


if __name__ == '__main__':
    unittest.main()
