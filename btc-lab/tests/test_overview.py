import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from lab import overview
from lab.core import Store

TZ = overview.TZ


def ts(text):
    return datetime.strptime(text, '%Y-%m-%d %H:%M').replace(tzinfo=TZ).timestamp()


class OverviewTests(unittest.TestCase):
    def test_days_count_by_close_date_in_stockholm(self):
        now = ts('2026-10-16 12:00')
        closed = [(ts('2026-10-16 00:30'), -5_000_000, {'opened': ts('2026-10-15 23:50')}),
                  (ts('2026-10-15 23:59'), 2_000_000, {'opened': ts('2026-10-15 23:40')}),
                  (ts('2026-10-01 10:00'), 9_000_000, {'opened': ts('2026-10-01 09:45')})]
        out = overview.series(closed, now, since=ts('2026-10-10 14:03'))
        self.assertEqual(len(out['days']), overview.DAYS)
        self.assertEqual(out['days'][-1]['day'], '2026-10-16')
        self.assertEqual(out['today_micro'], -5_000_000)
        self.assertEqual(out['week_micro'], -3_000_000)
        self.assertEqual((out['week_days_up'], out['week_days_down']), (1, 1))
        # since counts by open time; the 1 Oct trade is before the desk and outside the 14 days
        self.assertEqual(out['since_micro'], -3_000_000)
        self.assertEqual(out['since_closed'], 2)

    def test_build_reads_both_books_and_the_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'data').mkdir()
            (root / 'logs').mkdir()
            (root / 'logs' / 'daily-audit.json').write_text(json.dumps(
                {'at': 1, 'ok': False, 'streak': 0, 'checks': [{'status': 'PROBLEM', 'detail': 'restart'}]}))
            store = Store(root / 'data' / 'lab.sqlite')
            now = ts('2026-10-16 12:00')
            with store.connect() as db:
                db.execute('CREATE TABLE IF NOT EXISTS mitch_positions (id TEXT PRIMARY KEY, wallet TEXT, body TEXT)')
                db.execute('CREATE TABLE IF NOT EXISTS wallet_copy_positions (id TEXT PRIMARY KEY, wallet TEXT, body TEXT)')
                db.execute("INSERT INTO mitch_positions VALUES ('a','w',?)", (json.dumps(
                    {'opened': now - 3600, 'closed_at': now - 600, 'pnl_micro': 4_000_000}),))
                db.execute("INSERT INTO wallet_copy_positions VALUES ('b','w',?)", (json.dumps(
                    {'opened': now - 7200, 'closed_at': now - 900, 'pnl_micro': -1_000_000}),))
                db.execute("INSERT INTO wallet_copy_positions VALUES ('c','w',?)", (json.dumps(
                    {'opened': now - 60, 'status': 'OPEN'}),))
            store.set('mitch_desk', {'start_at': now - 86400})
            store.set('wallet_roster', {'wallets': {'x': {'state': 'paused'}, 'y': {'state': 'paper_test'}}})
            out = overview.build(store, root, now=now)
            self.assertEqual(out['mitch']['today_micro'], 4_000_000)
            self.assertEqual(out['mitch']['since_micro'], 4_000_000)
            self.assertEqual(out['wallets']['today_micro'], -1_000_000)
            self.assertEqual(out['wallets']['roster'], {'paused': 1, 'paper_test': 1})
            self.assertEqual(out['readiness']['problems'], ['restart'])


if __name__ == '__main__':
    unittest.main()
