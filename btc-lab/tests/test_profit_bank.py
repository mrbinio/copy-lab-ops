import json
import sqlite3
import unittest

from lab.profit_bank import bank_snapshot, ledger_state, lock_profit, rebuild_high_water


def db_with(positions, wallets=('a', 'b')):
    db = sqlite3.connect(':memory:')
    db.execute('CREATE TABLE state (key TEXT PRIMARY KEY, body TEXT)')
    db.execute('CREATE TABLE mitch_accounts (wallet TEXT PRIMARY KEY, cash INTEGER, reserved INTEGER NOT NULL DEFAULT 0)')
    db.execute('CREATE TABLE mitch_positions (id TEXT, wallet TEXT, body TEXT)')
    for w in wallets:
        db.execute("INSERT INTO mitch_accounts VALUES (?, 500000000, 0)", (w,))
    for i, (wallet, status, at, pnl) in enumerate(positions):
        db.execute('INSERT INTO mitch_positions VALUES (?,?,?)', (str(i), wallet, json.dumps(
            {'status': status, 'closed_at': at, 'pnl_micro': pnl})))
    return db


class LedgerHighWaterTests(unittest.TestCase):
    def test_a_win_that_only_recovers_a_loss_reserves_nothing(self):
        db = db_with([])
        self.assertEqual(lock_profit(db, 'mitch_accounts', 'a', -10_000_000), 0)
        self.assertEqual(lock_profit(db, 'mitch_accounts', 'b', 10_000_000), 0)
        self.assertEqual(lock_profit(db, 'mitch_accounts', 'a', 5_000_000), 2_000_000)
        self.assertEqual(lock_profit(db, 'mitch_accounts', 'b', -3_000_000), 0)
        self.assertEqual(ledger_state(db, 'mitch_accounts')['reserved_micro'], 2_000_000)

    def test_one_account_up_and_another_down_is_one_ledger(self):
        # Per account the old rule banked 40% of a's +20. The ledger never rose.
        db = db_with([('b', 'CLOSED', 1, -20_000_000), ('a', 'CLOSED', 2, 20_000_000)])
        db.execute("UPDATE mitch_accounts SET reserved=8000000 WHERE wallet='a'")
        self.assertTrue(rebuild_high_water(db, 'mitch_accounts', 'mitch_positions'))
        state = ledger_state(db, 'mitch_accounts')
        self.assertEqual((state['realized_micro'], state['peak_micro'], state['reserved_micro']), (0, 0, 0))
        self.assertEqual(state['previous_rule_reserved_micro'], 8_000_000)
        self.assertEqual(db.execute('SELECT SUM(reserved) FROM mitch_accounts').fetchone()[0], 0)

    def test_rebuild_replays_in_time_order_once_and_skips_unpaid(self):
        db = db_with([('a', 'CLOSED', 3, 5_000_000), ('a', 'CLOSED', 1, 20_000_000), ('b', 'SETTLED', 2, -15_000_000),
                      ('a', 'RESOLVED', 4, 50_000_000), ('a', 'OPEN', None, None)])
        self.assertTrue(rebuild_high_water(db, 'mitch_accounts', 'mitch_positions'))
        state = ledger_state(db, 'mitch_accounts')
        self.assertEqual((state['realized_micro'], state['peak_micro'], state['reserved_micro']),
                         (10_000_000, 20_000_000, 8_000_000))
        self.assertFalse(rebuild_high_water(db, 'mitch_accounts', 'mitch_positions'))
        self.assertEqual(bank_snapshot(db)['mitch_reserved_micro'], 8_000_000)


if __name__ == '__main__':
    unittest.main()
