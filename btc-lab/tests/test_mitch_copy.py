import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from lab.core import Store
from lab.mitch_copy import (
    MitchCopy, STINT, WALLETS, copy_notional_usd, price_allows, sell_fraction, our_sell_shares,
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

    def test_chain_fast_quote_is_not_the_price_he_paid(self):
        from lab.mitch_copy import source_dollars, source_price
        quote=dict(self.event(10, '0.99'), _source='chain_fast')
        self.assertIsNone(source_dollars(quote))
        self.assertIsNone(source_price(quote))
        paid=self.event(10, '0.42')
        paid['usdcSize']='4.20'
        self.assertEqual(source_dollars(paid), Decimal('4.20'))
        self.assertEqual(source_price(paid), Decimal('0.42'))

    def test_unconfirmed_fee_and_a_thin_book_do_not_invent_a_fill(self):
        event = self.event(10)
        why, fill = self.engine.plan_buy(event, asks('0.50'), '0', '0.01', '1', 20_000_000, fee_verified=False)
        self.assertEqual(why, 'FEE_UNCONFIRMED')
        self.assertIsNone(fill)
        why, fill = self.engine.plan_buy(event, asks('0.50', '0.01'), '0', '0.01', '1', 20_000_000)
        self.assertEqual(why, 'NO_LIQUIDITY')
        self.assertIsNone(fill)

    def test_partial_sell_then_official_settlement_pays_the_remainder_once(self):
        with self.store.connect() as db:
            self.engine.anchor_source(db, FIRST, 'token-a', '0')
            event = dict(self.event(10, '0.40'), conditionId='cond-1', timestamp=1_800_000_000)
            _why, fill = self.engine.plan_buy(event, asks('0.40'), '0', '0.01', '1', 20_000_000)
            self.assertEqual(self.engine.apply_buy(db, FIRST, 'buy1', event, fill, {}), 'MITCH_BUY')
            add = dict(event, transactionHash='0xadd', size=5, usdcSize=2)
            _why, fill2 = self.engine.plan_buy(add, asks('0.40'), '0', '0.01', '1', 20_000_000)
            self.assertEqual(self.engine.apply_buy(db, FIRST, 'add1', add, fill2, {}), 'MITCH_ADD')
            sell = dict(event, side='SELL', size=1, transactionHash='0xsell')
            fraction = self.engine.fraction_for(db, FIRST, sell)
            self.assertIsNotNone(fraction)
            self.assertLess(float(fraction), 1)
            reason = self.engine.apply_sell(db, FIRST, 'sell1', sell, asks('0.30'), fraction, {}, False)
            self.assertEqual(reason, 'MITCH_SELL')
            open_row = db.execute('SELECT id, body FROM mitch_positions').fetchall()
            still = [json.loads(body) for _pid, body in open_row if json.loads(body)['status'] == 'OPEN']
            self.assertEqual(len(still), 1)
            trade_id = still[0]['id']
            cash_before = db.execute('SELECT cash FROM mitch_accounts WHERE wallet=?', (FIRST,)).fetchone()[0]
        official = {
            'condition_id': 'cond-1', 'closed': True,
            'tokens': [
                {'token_id': 'token-a', 'winner': True},
                {'token_id': 'token-b', 'winner': False},
            ],
        }
        self.engine._settle_one(trade_id, {'closed': False, 'condition_id': 'cond-1', 'tokens': official['tokens']})
        self.engine._settle_one(trade_id, {'closed': True, 'condition_id': 'cond-1', 'tokens': [{'token_id': 'other', 'winner': True}]})
        self.engine._settle_one(trade_id, official)
        self.engine._settle_one(trade_id, official)
        with self.store.connect() as db:
            body = json.loads(db.execute('SELECT body FROM mitch_positions WHERE id=?', (trade_id,)).fetchone()[0])
            cash = db.execute('SELECT cash FROM mitch_accounts WHERE wallet=?', (FIRST,)).fetchone()[0]
            pays = db.execute("SELECT COUNT(*) FROM mitch_ledger WHERE id=?", ('settle:' + trade_id,)).fetchone()[0]
        self.assertEqual(body['status'], 'SETTLED')
        self.assertEqual(pays, 1)
        self.assertEqual(cash, cash_before + int(body['payout']))
        self.assertGreater(int(body['payout']), 0)

    def test_anchor_as_of_keeps_events_already_inside_the_balance(self):
        with self.store.connect() as db:
            self.engine.anchor_source(db, FIRST, 'token-a', '6', as_of=500)
            self.engine._record_source(
                db, FIRST, 'token-a', 'inside', {'size': '4', 'timestamp': 400}, buy=False,
            )
            shares = db.execute(
                'SELECT shares FROM mitch_source WHERE wallet=? AND token=?',
                (FIRST, 'token-a'),
            ).fetchone()[0]
            self.assertEqual(Decimal(shares), Decimal('6'))
            self.engine._record_source(
                db, FIRST, 'token-a', 'after', {'size': '1', 'timestamp': 600}, buy=False,
            )
            shares = db.execute(
                'SELECT shares FROM mitch_source WHERE wallet=? AND token=?',
                (FIRST, 'token-a'),
            ).fetchone()[0]
            self.assertEqual(Decimal(shares), Decimal('5'))

    def test_fresh_signals_are_ahead_of_older_history(self):
        now = self.engine.clock()
        self.store.set('mitch_copy_start', {'at': now - 1000, 'spec': 'mitch-copy-wallets-v1'})
        with self.store.connect() as db:
            db.execute(
                '''CREATE TABLE wallet_activity (
                    wallet TEXT, event_key TEXT, first_seen REAL, source_ts REAL, body TEXT,
                    PRIMARY KEY(wallet, event_key))'''
            )
            old = {'side': 'BUY', 'type': 'TRADE', 'slug': 'btc-updown-15m-1'}
            fresh = {'side': 'BUY', 'type': 'TRADE', 'slug': 'btc-updown-15m-2'}
            db.execute(
                'INSERT INTO wallet_activity VALUES (?,?,?,?,?)',
                (FIRST, 'old', now - 10, now - 400, json.dumps(old)),
            )
            db.execute(
                'INSERT INTO wallet_activity VALUES (?,?,?,?,?)',
                (FIRST, 'fresh', now - 1, now - 2, json.dumps(fresh)),
            )
            rows = self.engine.pending(db, now)
            depth = self.engine.backlog(db, now)
        self.assertEqual([row['event_key'] for row in rows], ['fresh', 'old'])
        self.assertEqual(depth['backlog'], 2)
        self.assertEqual(depth['fresh'], 1)
        self.assertEqual(depth['history'], 1)
        self.assertEqual(depth['buys'], 1)

    def test_executed_timings_survive_a_newer_rejection(self):
        self.store.set('mitch_copy_start', {'at': 100, 'spec': 'mitch-copy-wallets-v1'})
        timing = {
            'detect_ms': 120.0, 'queue_ms': 4000.0, 'book_ms': 70.0,
            'process_ms': 70.0, 'total_confirmed': False,
        }
        with self.store.connect() as db:
            db.execute(
                'INSERT INTO mitch_events VALUES (?,?,?,?,?)',
                (FIRST, 'fill', 'MITCH_BUY', json.dumps({'timing': timing}), 150),
            )
            db.execute(
                'INSERT INTO mitch_events VALUES (?,?,?,?,?)',
                (FIRST, 'reject', 'NOT_BTC_15M', '{}', 180),
            )
            db.execute(
                'INSERT INTO mitch_windows VALUES (?,?,?)',
                (FIRST, 'btc-updown-15m-1799999100', 15_000_000),
            )
            db.execute(
                'INSERT INTO mitch_windows VALUES (?,?,?)',
                (FIRST, 'btc-updown-15m-1800000000', 15_000_000),
            )
            db.execute(
                '''CREATE TABLE wallet_activity (
                    wallet TEXT, event_key TEXT, first_seen REAL, source_ts REAL, body TEXT,
                    PRIMARY KEY(wallet, event_key))'''
            )
            db.execute(
                'INSERT INTO mitch_events VALUES (?,?,?,?,?)',
                (FIRST, 'old-late', 'LATE_BUY_NOT_COPIED', '{}', 160),
            )
            db.execute(
                'INSERT INTO mitch_events VALUES (?,?,?,?,?)',
                (FIRST, 'new-late', 'LATE_BUY_NOT_COPIED', '{}', 170),
            )
            db.execute(
                'INSERT INTO wallet_activity VALUES (?,?,?,?,?)',
                (FIRST, 'old-late', 50, 50, '{}'),
            )
            db.execute(
                'INSERT INTO wallet_activity VALUES (?,?,?,?,?)',
                (FIRST, 'new-late', 200, 200, '{}'),
            )
        payload = self.engine.publish()
        latency = payload['latency']
        self.assertEqual(latency['samples'], 1)
        self.assertEqual(latency['detect']['n'], 1)
        self.assertEqual(latency['queue']['n'], 1)
        self.assertEqual(latency['total']['n'], 0)
        self.assertEqual(latency['executed_without_timing'], 0)
        self.assertFalse(latency['total_confirmed'])
        row = next(item for item in payload['wallets'] if item['wallet'] == FIRST)
        self.assertEqual(row['spent_since_start_micro'], 30_000_000)
        self.assertEqual(row['window_limit_breaks'], 0)
        self.assertEqual(len(row['windows']), 2)
        self.assertTrue(all(item['spent_micro'] == 15_000_000 for item in row['windows']))
        self.assertTrue(all(item['within_limit'] for item in row['windows']))
        self.assertEqual(payload['late']['before_activation'], 1)
        self.assertEqual(payload['late']['after_activation_not_copied'], 1)
        self.assertEqual(payload['late']['unstamped'], 0)

    def test_restart_keeps_the_start_and_does_not_replay(self):
        self.store.set('mitch_copy_start', {'at': 100, 'spec': 'mitch-copy-wallets-v1'})
        again = MitchCopy(self.store, fetch=None, clock=lambda: 200)
        again.ensure()
        self.assertEqual(again.started(), 100)

    def test_five_minute_markets_are_skipped_with_mitch_note(self):
        event = self.event(10, slug='btc-updown-5m-1790000000')
        row = {
            'wallet': MIHA, 'event_key': 'miha-5m', 'body': json.dumps(event),
            'source_ts': self.engine.clock(), 'first_seen': self.engine.clock(),
        }
        pre = self.engine._prefilter(row, 0)
        self.assertTrue(pre['stop'])
        with self.store.connect() as db:
            reason = db.execute(
                'SELECT reason FROM mitch_events WHERE event_key=?', ('miha-5m',),
            ).fetchone()[0]
        self.assertEqual(reason, 'MITCH_SKIP_5M')
        published = self.engine.publish()
        self.assertFalse(published['miha_5m']['copy'])
        self.assertIn('5m', published['miha_5m']['note'])

    def test_a_chain_fast_quote_warms_the_book_instead_of_waiting_three_seconds(self):
        event = dict(self.event(10), _source='chain_fast')
        now = self.engine.clock()
        row = {
            'wallet': FIRST, 'event_key': 'fast-1', 'body': json.dumps(event),
            'source_ts': now, 'first_seen': now,
        }
        pre = self.engine._prefilter(row, 0)
        self.assertTrue(pre['stop'])
        self.assertTrue(pre.get('prefetch'))
        with self.store.connect() as db:
            marked = db.execute(
                'SELECT reason FROM mitch_events WHERE event_key=?', ('fast-1',),
            ).fetchone()
        self.assertIsNone(marked)

    def test_reserved_cash_is_not_spent_on_the_next_buy(self):
        event = self.event(10)
        with self.store.connect() as db:
            db.execute('UPDATE mitch_accounts SET reserved=? WHERE wallet=?', (499_000_000, FIRST))
            _why, fill = self.engine.plan_buy(event, asks('0.50'), '0', '0.01', '1', 20_000_000)
            self.assertEqual(self.engine.apply_buy(db, FIRST, 'reserved-buy', event, fill, {}), 'PROFIT_RESERVED')
        published = self.engine.publish()
        row = next(item for item in published['wallets'] if item['wallet'] == FIRST)
        self.assertEqual(row['reserved_micro'], 499_000_000)
        self.assertLess(row['tradable_micro'], fill['cost'] + fill['fee'])

    def test_a_closed_win_banks_forty_percent(self):
        from lab.profit_bank import RESERVE_PCT, bank_snapshot, lock_profit, reserved_of
        self.assertEqual(RESERVE_PCT, Decimal('0.40'))
        with self.store.connect() as db:
            added = lock_profit(db, 'mitch_accounts', FIRST, 10_000_000)
            self.assertEqual(added, 4_000_000)
            # The reserve sits on the ledger, not on one account.
            self.assertEqual(reserved_of(db, 'mitch_accounts', FIRST), 0)
            self.assertEqual(lock_profit(db, 'mitch_accounts', FIRST, -10_000_000), 0)
            self.assertEqual(lock_profit(db, 'mitch_accounts', FIRST, 10_000_000), 0)
            bank = bank_snapshot(db)
        self.assertEqual(bank['mitch_reserved_micro'], 4_000_000)
        self.assertFalse(bank['live'])
        published = self.engine.publish()
        self.assertEqual(published['profit_bank']['mitch_reserved_micro'], 4_000_000)

    def test_a_public_list_buy_is_not_copied(self):
        event = self.event(10)
        now = self.engine.clock()
        row = {
            'wallet': FIRST, 'event_key': 'rest-1', 'body': json.dumps(event),
            'source_ts': now, 'first_seen': now,
        }
        pre = self.engine._prefilter(row, 0)
        self.assertTrue(pre['stop'])
        with self.store.connect() as db:
            reason = db.execute(
                'SELECT reason FROM mitch_events WHERE event_key=?', ('rest-1',),
            ).fetchone()[0]
        self.assertEqual(reason, 'MITCH_NEED_CHAIN')

    def test_a_late_chain_buy_is_not_copied(self):
        self.store.set('mitch_copy_start', {'at': self.engine.clock() - 60, 'spec': 'mitch-copy-wallets-v1'})
        event = dict(self.event(10), _source='order_filled')
        now = self.engine.clock()
        row = {
            'wallet': FIRST, 'event_key': 'late-1', 'body': json.dumps(event),
            'source_ts': now - 1.5, 'first_seen': now - 1.5,
        }
        pre = self.engine._prefilter(row, 0)
        self.assertTrue(pre['stop'])
        with self.store.connect() as db:
            reason = db.execute(
                'SELECT reason FROM mitch_events WHERE event_key=?', ('late-1',),
            ).fetchone()[0]
        self.assertEqual(reason, 'LATE_BUY_NOT_COPIED')

    def test_chain_fast_older_than_one_second_is_skipped(self):
        event = dict(self.event(10), _source='chain_fast')
        now = self.engine.clock()
        row = {
            'wallet': FIRST, 'event_key': 'fast-old', 'body': json.dumps(event),
            'source_ts': now - 2, 'first_seen': now - 2,
        }
        pre = self.engine._prefilter(row, 0)
        self.assertTrue(pre['stop'])
        self.assertFalse(pre.get('prefetch'))
        with self.store.connect() as db:
            reason = db.execute(
                'SELECT reason FROM mitch_events WHERE event_key=?', ('fast-old',),
            ).fetchone()[0]
        self.assertEqual(reason, 'MITCH_NEED_CHAIN')

    def test_negative_book_pauses_further_buys(self):
        with self.store.connect() as db:
            self.engine.anchor_source(db, FIRST, 'token-a', '25')
            event = self.event(10, '0.40')
            _why, fill = self.engine.plan_buy(event, asks('0.40'), '0', '0.01', '1', 20_000_000)
            self.assertEqual(self.engine.apply_buy(db, FIRST, 'loss-buy', event, fill, {}), 'MITCH_BUY')
            sell = dict(event, side='SELL', size=25, transactionHash='0xlosssell')
            self.assertEqual(
                self.engine.apply_sell(db, FIRST, 'loss-sell', sell, asks('0.01'), Decimal('1'), {}, False),
                'MITCH_SELL',
            )
            again = dict(self.event(10, '0.50'), transactionHash='0xafter')
            _why, fill2 = self.engine.plan_buy(again, asks('0.50'), '0', '0.01', '1', 20_000_000)
            self.assertEqual(self.engine.apply_buy(db, FIRST, 'after-pause', again, fill2, {}), 'MITCH_PAUSED')
        published = self.engine.publish()
        row = next(item for item in published['wallets'] if item['wallet'] == FIRST)
        self.assertTrue(row['paused'])
        self.assertTrue(published['journal'])
        self.assertLess(row['period_net_micro'], 0)
        self.assertEqual(row['period_closed'], 1)
        self.assertEqual(row['period_copies'], 1)
        self.assertEqual(published['period_reasons'].get('MITCH_PAUSED'), 1)
        self.assertIn('MITCH_PAUSED', {e['reason'] for e in published['period_events']})
        self.assertFalse(published['stop_active'])

    def test_pause_stays_after_a_later_plus(self):
        with self.store.connect() as db:
            db.execute(
                "INSERT INTO state VALUES ('mitch_pauses', ?) ON CONFLICT(key) DO UPDATE SET body=excluded.body",
                (json.dumps({'wallets': {FIRST: {'paused': True, 'since': 1, 'reason': 'held', 'stint': STINT['id']}}}),),
            )
            trade = {
                'id': 'win1', 'wallet': FIRST, 'status': 'CLOSED', 'opened': self.engine.clock(),
                'pnl_micro': 5_000_000, 'closed_at': self.engine.clock(),
            }
            db.execute('INSERT INTO mitch_positions VALUES (?,?,?)', ('win1', FIRST, json.dumps(trade)))
            payload = self.engine.refresh_pauses(db)
        self.assertTrue(payload['wallets'][FIRST]['paused'])

    def test_a_stint_change_does_not_unpause_a_negative_book(self):
        clock = self.engine.clock()
        with self.store.connect() as db:
            old = {'id': 'old', 'wallet': FIRST, 'status': 'CLOSED', 'opened': clock - 3600,
                   'pnl_micro': -9_000_000, 'closed_at': clock - 3000}
            db.execute('INSERT INTO mitch_positions VALUES (?,?,?)', ('old', FIRST, json.dumps(old)))
            payload = self.engine.refresh_pauses(db)
        row = payload['wallets'][FIRST]
        self.assertTrue(row['paused'])
        self.assertEqual(row['all_net_usd'], -9.0)

    def test_the_pause_file_stops_new_buys(self):
        (Path(self.store.path).parent / 'PAUSE').write_text('telegram')
        event = self.event(10)
        with self.store.connect() as db:
            _why, fill = self.engine.plan_buy(event, asks('0.50'), '0', '0.01', '1', 20_000_000)
            self.assertEqual(self.engine.apply_buy(db, FIRST, 'stopped', event, fill, {}), 'GLOBAL_STOP')

    def test_a_clob_match_buy_inside_one_second_goes_to_the_book(self):
        self.store.set('mitch_copy_start', {'at': self.engine.clock() - 60, 'spec': 'mitch-copy-wallets-v1'})
        event = dict(self.event(10), _source='clob_match', _ts_basis='match')
        now = self.engine.clock()
        row = {
            'wallet': FIRST, 'event_key': 'match-1', 'body': json.dumps(event),
            'source_ts': now - 0.3, 'first_seen': now - 0.1,
        }
        pre = self.engine._prefilter(row, 0)
        self.assertFalse(pre['stop'])
        self.assertEqual(pre['basis'], 'source_subsecond')

    def test_a_receipt_timed_by_our_own_detection_cannot_buy(self):
        event = dict(self.event(10), _source='order_filled', _ts_basis='local_detect')
        now = self.engine.clock()
        row = {
            'wallet': FIRST, 'event_key': 'local-1', 'body': json.dumps(event),
            'source_ts': now, 'first_seen': now,
        }
        pre = self.engine._prefilter(row, 0)
        self.assertTrue(pre['stop'])
        with self.store.connect() as db:
            reason = db.execute(
                'SELECT reason FROM mitch_events WHERE event_key=?', ('local-1',),
            ).fetchone()[0]
        self.assertEqual(reason, 'SOURCE_TIME_UNKNOWN')


if __name__ == '__main__':
    unittest.main()
