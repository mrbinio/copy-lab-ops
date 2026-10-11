import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from lab import daily_audit as audit


def db_with(desk, positions):
    db = sqlite3.connect(':memory:')
    db.execute('CREATE TABLE state (key TEXT PRIMARY KEY, body TEXT)')
    db.execute('CREATE TABLE mitch_positions (id TEXT PRIMARY KEY, wallet TEXT, body TEXT)')
    db.execute("INSERT INTO state VALUES ('mitch_desk', ?)", (json.dumps(desk),))
    for i, body in enumerate(positions):
        db.execute('INSERT INTO mitch_positions VALUES (?,?,?)', (str(i), 'w', json.dumps(body)))
    return db


class AuditTests(unittest.TestCase):
    def test_ledger_matches_the_closed_copies_since_the_desk(self):
        desk = {'start_at': 100, 'line_micro': 500_000_000, 'realized_micro': -5_000_000, 'swept_micro': 2_000_000}
        rows = [{'opened': 150, 'status': 'SETTLED', 'pnl_micro': -5_000_000, 'closed_at': 200},
                {'opened': 50, 'status': 'SETTLED', 'pnl_micro': 9_000_000, 'closed_at': 60}]
        self.assertEqual(audit.ledger(db_with(desk, rows))['status'], 'OK')
        desk['realized_micro'] = -1_000_000
        self.assertEqual(audit.ledger(db_with(desk, rows))['status'], 'PROBLEM')

    def test_a_restart_in_the_last_day_is_a_problem(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'watchdog.out').write_text('\n'.join([
                json.dumps({'at': 1000, 'action': 'restart_requested'}),
                json.dumps({'at': 5000, 'action': 'ok'}),
            ]))
            self.assertEqual(audit.restarts(tmp, 500)['value'], 1)
            self.assertEqual(audit.restarts(tmp, 2000)['status'], 'OK')

    def test_readiness_needs_three_clean_days_in_a_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'h.json'
            day = 86400
            for i, ok in enumerate((True, False, True, True)):
                report = audit.update_history({'at': 1_800_000_000 + i * day, 'ok': ok, 'checks': []}, path)
            self.assertEqual((report['streak'], report['ready']), (2, False))
            report = audit.update_history({'at': 1_800_000_000 + 4 * day, 'ok': True, 'checks': []}, path)
            self.assertTrue(report['ready'])

    def test_text_names_each_check(self):
        report = {'ok': False, 'streak': 0, 'results': {'windows': 3, 'won': 1, 'lost': 2, 'net_micro': -4_500_000},
                  'checks': [audit.check('db_lock', 'PROBLEM', 'czekanie 2000 ms'),
                             audit.check('live_gate', 'OK', 'PAPER')]}
        text = audit.text(report)
        self.assertIn('❌ Baza danych: czekanie 2000 ms', text)
        self.assertIn('netto -4.50 USD', text)
        self.assertIn('0/3', text)


if __name__ == '__main__':
    unittest.main()
