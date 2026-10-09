import asyncio
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from lab.core import Store
from lab.fast_match import FastMatch, insert_row, remember_window
from lab.match_decoder import decode_match, wallet_fills
from lab.order_fill import fill_for_wallet

FIXTURES = Path(__file__).parent / 'fixtures'
DC27 = json.loads((FIXTURES / 'match_dc27_2026-10-09.json').read_text())
SAMPLES = json.loads((FIXTURES / 'match_samples_2026-10-09.json').read_text())


class DecodeTests(unittest.TestCase):
    def test_his_buy_from_the_pending_transaction(self):
        match = decode_match(DC27['tx'])
        legs = wallet_fills(match, [DC27['wallet']])
        self.assertEqual(len(legs), 1)
        leg = legs[0]
        self.assertEqual(leg['side'], 'BUY')
        self.assertEqual(leg['token'], DC27['token'])
        self.assertEqual(leg['shares'], Decimal('13.5'))
        self.assertEqual(leg['usdc'], Decimal('3.78'))
        self.assertEqual(leg['fee'], Decimal('0.19051'))
        self.assertEqual(leg['price'], Decimal('0.28'))
        self.assertEqual(leg['role'], 'taker')
        self.assertAlmostEqual(leg['signed_at'], 1791535909.843, places=3)

    def test_real_fills_match_the_public_list_with_fee(self):
        for sample in SAMPLES:
            match = decode_match({'to': sample['to'], 'input': sample['input'], 'hash': sample['tx']})
            legs = wallet_fills(match, [sample['wallet']])
            self.assertEqual(len(legs), 1, sample['tx'])
            leg = legs[0]
            self.assertEqual(leg['token'], sample['public']['token'])
            self.assertEqual(leg['shares'], Decimal(sample['public']['shares']).quantize(Decimal('0.000001')))
            self.assertLessEqual(abs(leg['usdc'] + leg['fee'] - Decimal(sample['public']['usdc_with_fee'])), Decimal('0.00001'))

    def test_another_contract_or_function_is_not_guessed(self):
        self.assertIsNone(decode_match(dict(DC27['tx'], to='0x' + '1' * 40)))
        self.assertIsNone(decode_match(dict(DC27['tx'], input='0xdeadbeef' + DC27['tx']['input'][10:])))
        self.assertIsNone(decode_match(dict(DC27['tx'], input=DC27['tx']['input'][:200])))

    def test_an_unwatched_wallet_has_no_leg(self):
        self.assertEqual(wallet_fills(decode_match(DC27['tx']), ['0x' + '2' * 40]), [])


class ReceiptTests(unittest.TestCase):
    def test_new_exchange_order_filled_is_read(self):
        fill = fill_for_wallet(DC27['receipt']['logs'], DC27['wallet'], DC27['token'], '13.5')
        self.assertIsNotNone(fill)
        self.assertEqual(fill['side'], 'BUY')
        self.assertEqual(fill['size'], Decimal('13.5'))
        self.assertEqual(fill['usdc'], Decimal('3.78'))
        self.assertEqual(fill['fee'], Decimal('0.19051'))
        self.assertEqual(fill['fills'], 1)

    def test_the_counterparty_log_is_not_his_fill(self):
        # The maker on the other token names him as taker. Counting it would
        # double his shares on the wrong token.
        other = '97030274416114027865880817336616444306203393410822614643111353029915015054417'
        self.assertIsNone(fill_for_wallet(DC27['receipt']['logs'], DC27['wallet'], other))


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


class FastLaneTests(unittest.TestCase):
    def setUp(self):
        remember_window(DC27['token'], 'btc-updown-15m-1791535500', '0xcond')

    def run_lane(self, replies):
        clock = Clock(1791535910.0)
        got = []

        async def sink(wallet, row, arrived):
            got.append((wallet, row))

        calls = []

        def lookup(url, tx):
            calls.append(url)
            return replies.pop(0) if replies else None

        async def sleep(seconds):
            clock.now += seconds

        lane = FastMatch([DC27['wallet']], sink, urls=['rpc-a'], lookup=lookup, clock=clock, sleep=sleep)
        print_item = {'transaction_hash': DC27['tx']['hash'], 'timestamp': '1791535909900'}

        async def go():
            task = lane.note(print_item, arrived=clock.now)
            return await task

        rows = asyncio.run(go())
        return lane, rows, got, calls

    def test_a_pending_match_reaches_the_copier_with_match_time(self):
        lane, rows, got, _ = self.run_lane([dict(DC27['tx'], blockNumber=None)])
        self.assertEqual(len(got), 1)
        wallet, row = got[0]
        self.assertEqual(wallet, DC27['wallet'])
        self.assertEqual(row['_source'], 'clob_match')
        self.assertEqual(row['timestamp'], 1791535909.9)
        self.assertEqual(row['slug'], 'btc-updown-15m-1791535500')
        self.assertEqual(row['size'], '13.500000')
        self.assertEqual(row['usdcSize'], '3.970510')
        self.assertEqual(lane.status()['resolved'], 1)

    def test_not_in_the_mempool_yet_is_retried_then_given_up(self):
        lane, rows, got, calls = self.run_lane([None, None, dict(DC27['tx'], blockNumber=None)])
        self.assertEqual(len(got), 1)
        self.assertEqual(len(calls), 3)
        lane, rows, got, calls = self.run_lane([])
        self.assertEqual(got, [])
        self.assertEqual(lane.status()['missed'], 1)
        self.assertLessEqual(len(calls), 17)

    def test_the_same_print_twice_is_one_lookup(self):
        lane = FastMatch([DC27['wallet']], None, urls=['x'], lookup=lambda u, t: None)
        item = {'transaction_hash': '0xaa', 'timestamp': '1'}

        async def go():
            first = lane.note(item)
            second = lane.note(item)
            await first
            return second

        self.assertIsNone(asyncio.run(go()))
        self.assertEqual(lane.status()['prints'], 1)


class HandOffTests(unittest.TestCase):
    def test_the_copy_runs_on_the_worker_loop_not_the_socket_loop(self):
        import threading
        from lab.fast_match import hand_to_loop
        main = asyncio.new_event_loop()
        ran = []
        done = threading.Event()

        async def sink(wallet, row, arrived):
            ran.append((wallet, threading.current_thread().name))
            done.set()

        thread = threading.Thread(target=main.run_forever, name='worker-loop', daemon=True)
        thread.start()
        try:
            asyncio.run(hand_to_loop(main, sink)('0xw', {}, 1.0))
            self.assertTrue(done.wait(2))
            self.assertEqual(ran, [('0xw', 'worker-loop')])
        finally:
            main.call_soon_threadsafe(main.stop)
            thread.join(2)
            main.close()


class InsertTests(unittest.TestCase):
    def test_a_match_row_is_not_replaced_and_keeps_its_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'lab.db')
            body = {'transactionHash': '0xt', 'type': 'TRADE', 'asset': 'tok', 'side': 'BUY',
                    'timestamp': 100.5, '_source': 'clob_match', 'price': '0.4', 'size': '5'}
            with store.connect() as db:
                db.execute('CREATE TABLE IF NOT EXISTS wallet_activity (wallet TEXT, event_key TEXT, first_seen REAL, source_ts REAL, body TEXT, PRIMARY KEY (wallet, event_key))')
            row = insert_row(store, '0xw', body, 100.6)
            self.assertEqual(row['source_ts'], 100.5)
            self.assertIsNone(insert_row(store, '0xw', body, 100.7))
            from lab.wallet_observer import merge_activity_body
            with store.connect() as db:
                stored = db.execute('SELECT body FROM wallet_activity').fetchone()[0]
            merged, changed = merge_activity_body(stored, {'size': '5', 'usdcSize': '2.1', 'price': '0.42'})
            self.assertFalse(changed)
            self.assertEqual(json.loads(merged)['_source'], 'clob_match')


class LiveGateTests(unittest.TestCase):
    def test_no_config_can_build_a_real_order_client(self):
        from lab.clob_order import CLOBClient
        from lab.live_gate import LiveOrdersDisabled, LIVE_ORDERS_ALLOWED
        self.assertFalse(LIVE_ORDERS_ALLOWED)
        with self.assertRaises(LiveOrdersDisabled):
            CLOBClient(private_key='0x' + '1' * 64)


if __name__ == '__main__':
    unittest.main()
