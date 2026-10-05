import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from lab.core import Store
from lab.source_chain import (
    TokenBalanceReader, _parse_transfer, encode_balance_of, http_url_from_wss,
    reconcile_recent, reconcile_token, resolve_event)
from lab.wallet_copy import source_position
from lab.wallet_observer import WALLETS

WALLET = WALLETS[0]
OTHER = '0x' + '11' * 20
TOKEN = '1'
NOW = 1_700_000_000


def raw_shares(shares):
    return int(Decimal(shares) * Decimal(10) ** 6)


class FakeChain:
    def __init__(self, head=100):
        self.head = head
        self.balances = {}
        self.receipts = {}
        self.logs = []
        self.on_balance = None
        self.fail = None

    def block_number(self):
        if self.fail == 'head':
            raise RuntimeError('down')
        return self.head

    def token_balance_raw(self, wallet, token_id, block):
        if self.fail == 'balance':
            raise RuntimeError('down')
        if self.on_balance:
            self.on_balance(wallet, token_id, block)
        key = (wallet.lower(), str(token_id), int(block))
        if key not in self.balances:
            raise RuntimeError('missing balance')
        return self.balances[key]

    def transfers(self, tx_hash):
        if self.fail == 'receipt':
            raise RuntimeError('down')
        if tx_hash not in self.receipts:
            raise RuntimeError('missing receipt')
        return self.receipts[tx_hash]

    def transfers_after(self, wallet, token_id, start_block, end_block):
        if self.fail == 'logs':
            raise RuntimeError('down')
        rows = []
        for item in self.logs:
            if str(item.get('token_id')) != str(token_id):
                continue
            if int(start_block) <= int(item['block']) <= int(end_block):
                rows.append(item)
        return sorted(rows, key=lambda item: (int(item['block']), int(item['log_index'])))


def log(index, shares, side, block, tx='0xlog'):
    sender = OTHER if side == 'BUY' else WALLET
    receiver = WALLET if side == 'BUY' else OTHER
    return {
        'log_index': index,
        'token_id': TOKEN,
        'from': sender,
        'to': receiver,
        'shares': format(Decimal(shares), 'f'),
        'block': block,
        'tx': tx,
    }


def receipt(block, logs, ok=True):
    return {'block': block, 'ok': ok, 'logs': logs}


class SourceChainTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'lab.db')
        self.chain = FakeChain()
        self.chain.balances[(WALLET, TOKEN, 95)] = raw_shares(100)

    def tearDown(self):
        self.temp.cleanup()

    def activity(self, key, side, size, tx, block_hint=None, ts=None):
        when = NOW if ts is None else ts
        body = {
            'proxyWallet': WALLET, 'type': 'TRADE', 'side': side, 'asset': TOKEN,
            'size': str(size), 'timestamp': when, 'transactionHash': tx,
        }
        with self.store.connect() as db:
            db.execute(
                '''CREATE TABLE IF NOT EXISTS wallet_activity (
                     wallet TEXT, event_key TEXT, first_seen REAL, source_ts REAL, body TEXT,
                     PRIMARY KEY(wallet, event_key))''')
            db.execute(
                'INSERT OR REPLACE INTO wallet_activity VALUES (?,?,?,?,?)',
                (WALLET, key, when, when, json.dumps(body)))

    def book(self):
        with self.store.connect() as db:
            return source_position(db, WALLET, TOKEN)

    def test_trade_arriving_during_the_balance_read_is_applied_once(self):
        def reveal(_wallet, _token, block):
            self.chain.logs.append(log(1, 40, 'BUY', block + 1, '0xlate'))
        self.chain.on_balance = reveal
        first = reconcile_token(self.store, self.chain, WALLET, TOKEN, NOW)
        self.assertTrue(first['ok'])
        self.assertEqual(first['block'], 95)
        self.assertEqual(self.book()['shares'], Decimal('140'))
        again = reconcile_token(self.store, self.chain, WALLET, TOKEN, NOW)
        self.assertEqual(again['shares'], Decimal('140'))
        self.assertEqual(self.book()['shares'], Decimal('140'))

    def test_same_second_events_follow_log_index_not_arrival(self):
        # Listed sell-first. The lower log index is still the buy.
        self.chain.logs = [
            log(2, 50, 'SELL', 96, '0xsell'),
            log(1, 100, 'BUY', 96, '0xbuy'),
        ]
        result = reconcile_token(self.store, self.chain, WALLET, TOKEN, NOW)
        self.assertTrue(result['ok'])
        self.assertEqual(self.book()['shares'], Decimal('150'))
        with self.store.connect() as db:
            proportion = db.execute(
                'SELECT proportion FROM wallet_source_events WHERE event_key=?',
                ('0xsell:2',)).fetchone()[0]
        self.assertEqual(Decimal(proportion), Decimal('0.25'))

    def test_duplicate_restart_does_not_apply_twice_or_open_a_copy(self):
        self.chain.logs = [log(1, 100, 'BUY', 96, '0xbuy')]
        first = reconcile_token(self.store, self.chain, WALLET, TOKEN, NOW)
        self.assertEqual(first['shares'], Decimal('200'))
        restarted = FakeChain(head=100)
        restarted.balances[(WALLET, TOKEN, 95)] = raw_shares(100)
        restarted.logs = [log(1, 100, 'BUY', 96, '0xbuy')]
        restarted.fail = 'receipt'
        second = reconcile_token(self.store, restarted, WALLET, TOKEN, NOW)
        self.assertEqual(second['shares'], Decimal('200'))
        self.assertEqual(self.book()['block'], 95)
        with self.store.connect() as db:
            copies = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='wallet_copy_events'"
            ).fetchone()
            events = db.execute(
                'SELECT COUNT(*) FROM wallet_source_events WHERE wallet=? AND token=?',
                (WALLET, TOKEN)).fetchone()[0]
        self.assertIsNone(copies)
        self.assertEqual(events, 1)

    def test_provider_silence_leaves_the_position_unknown(self):
        self.chain.fail = 'head'
        self.chain.logs = [log(1, 100, 'BUY', 96, '0xbuy')]
        result = reconcile_token(self.store, self.chain, WALLET, TOKEN, NOW)
        self.assertFalse(result['ok'])
        self.assertEqual(result['error'], 'RuntimeError')
        self.assertFalse(self.book()['known'])
        self.assertIsNone(self.book()['shares'])

    def test_transfer_inside_the_anchor_block_is_not_added_again(self):
        self.chain.logs = [log(4, 100, 'BUY', 95, '0xinside')]
        result = reconcile_token(self.store, self.chain, WALLET, TOKEN, NOW)
        self.assertTrue(result['ok'])
        self.assertEqual(self.book()['shares'], Decimal('100'))
        self.assertEqual(result['applied'], 0)

    def test_two_fills_in_one_transaction_both_count(self):
        self.chain.balances[(WALLET, TOKEN, 95)] = 0
        self.chain.logs = [
            log(1, 10, 'BUY', 96, '0xamb'),
            log(2, 10, 'BUY', 96, '0xamb'),
        ]
        result = reconcile_token(self.store, self.chain, WALLET, TOKEN, NOW)
        self.assertTrue(result['ok'])
        self.assertEqual(self.book()['shares'], Decimal('20'))
        again = reconcile_token(self.store, self.chain, WALLET, TOKEN, NOW)
        self.assertEqual(again['shares'], Decimal('20'))

    def test_later_trade_on_a_known_book_updates_the_sell_proportion(self):
        self.activity('open', 'BUY', 100, '0xopen')
        self.chain.logs = [log(1, 100, 'BUY', 96, '0xopen')]
        first = reconcile_token(self.store, self.chain, WALLET, TOKEN, NOW)
        self.assertEqual(first['shares'], Decimal('200'))
        self.activity('again', 'BUY', 40, '0xagain')
        self.chain.head = 120
        self.chain.balances[(WALLET, TOKEN, 115)] = raw_shares(200)
        self.chain.logs = [
            log(1, 40, 'BUY', 116, '0xagain'),
            log(2, 60, 'SELL', 116, '0xcut'),
        ]
        refreshed = reconcile_recent(self.store, NOW, reader=self.chain)
        self.assertTrue(refreshed[0]['ok'])
        self.assertEqual(self.book()['block'], 115)
        self.assertEqual(self.book()['shares'], Decimal('180'))
        with self.store.connect() as db:
            proportion = db.execute(
                'SELECT proportion FROM wallet_source_events WHERE event_key=?',
                ('0xcut:2',)).fetchone()[0]
            copies = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='wallet_copy_events'"
            ).fetchone()
        self.assertEqual(Decimal(proportion), Decimal('0.25'))
        self.assertIsNone(copies)

    def test_missing_reader_does_not_invent_a_book(self):
        self.activity('buy', 'BUY', 1, '0xbuy')
        result = reconcile_recent(self.store, NOW, reader=None, environ={})
        self.assertEqual(result, [])
        self.assertEqual(self.store.get('wallet_source_anchor_error')['error'], 'ALCHEMY_WSS missing')
        self.assertFalse(self.book()['known'])

    def test_balance_call_uses_the_block_and_hides_the_url(self):
        seen = {}

        def post(url, payload):
            seen['url'] = url
            seen['payload'] = payload
            if payload['method'] == 'eth_blockNumber':
                return {'result': '0x64'}
            if payload['method'] == 'eth_call':
                self.assertEqual(payload['params'][1], '0x5f')
                self.assertEqual(payload['params'][0]['data'][:10], '0x00fdd58e')
                return {'result': '0x' + format(raw_shares('2.547170'), 'x')}
            raise AssertionError(payload['method'])

        reader = TokenBalanceReader('https://rpc.test/secret-path', post=post)
        self.assertEqual(reader.block_number(), 100)
        self.assertEqual(reader.token_balance_raw(WALLET, 1, 95), raw_shares('2.547170'))
        self.assertIn('secret-path', seen['url'])

        def boom(url, payload):
            raise RuntimeError(url + ' secret-path refused')

        reader = TokenBalanceReader('https://rpc.test/secret-path', post=boom)
        with self.assertRaises(RuntimeError) as caught:
            reader.block_number()
        self.assertNotIn('secret-path', str(caught.exception))
        self.assertEqual(str(caught.exception), 'rpc.test: no response')

    def test_transfer_log_matches_the_raw_balance_units(self):
        value = 2547170
        data = '0x' + format(1, 'x').rjust(64, '0') + format(value, 'x').rjust(64, '0')
        entry = {
            'address': '0x4D97DCd97eC945f40cF65F87097ACe5EA0476045',
            'topics': [
                '0xc3d58168c5ae7397731d063d5bbf3d657854427343f4c083240f7aacaa2d0f62',
                '0x' + '22' * 32,
                '0x' + OTHER.lower().removeprefix('0x').rjust(64, '0'),
                '0x' + WALLET.lower().removeprefix('0x').rjust(64, '0'),
            ],
            'data': data,
            'logIndex': '0x3',
            'blockNumber': '0x5a9c3c8',
        }
        parsed = _parse_transfer(entry, 0)
        self.assertEqual(parsed['log_index'], 3)
        self.assertEqual(parsed['block'], int(entry['blockNumber'], 16))
        self.assertEqual(Decimal(parsed['shares']), Decimal(value) / Decimal(10) ** 6)
        encoded = encode_balance_of(WALLET, parsed['token_id'])
        self.assertTrue(encoded.startswith('0x00fdd58e'))
        self.assertEqual(len(encoded), 2 + 8 + 64 + 64)
        self.assertEqual(http_url_from_wss('wss://rpc.test/secret-path'), 'https://rpc.test/secret-path')

    def test_confirmed_book_resolves_the_next_event_without_a_timestamp(self):
        from lab.wallet_copy import anchor_source_position, note_source_event
        with self.store.connect() as db:
            anchor_source_position(db, WALLET, TOKEN, Decimal('100'), 95)
        event = {
            'proxyWallet': WALLET, 'type': 'TRADE', 'side': 'SELL', 'asset': TOKEN,
            'size': '25', 'timestamp': NOW, 'transactionHash': '0xnext',
        }
        self.chain.head = 100
        self.chain.balances[(WALLET, TOKEN, 95)] = raw_shares(100)
        self.chain.logs = [log(1, 25, 'SELL', 96, '0xnext')]
        result = reconcile_token(self.store, self.chain, WALLET, TOKEN, NOW)
        self.assertTrue(result['ok'])
        from lab.source_chain import proportion_for_transaction
        noted = proportion_for_transaction(self.store, WALLET, TOKEN, '0xnext', '25')
        book = self.book()
        self.assertEqual(noted['proportion'], Decimal('0.25'))
        self.assertEqual(book['shares'], Decimal('75'))
        self.assertEqual(book['block'], 95)
        again = reconcile_token(self.store, self.chain, WALLET, TOKEN, NOW)
        self.assertEqual(again['shares'], Decimal('75'))
        with self.store.connect() as db:
            copies = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='wallet_copy_events'"
            ).fetchone()
        self.assertIsNone(copies)
