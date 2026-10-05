import tempfile
import unittest
from pathlib import Path
from lab.core import Store
from lab.server import dashboard_state, drop_dashboard_state

class DashboardStateTests(unittest.TestCase):
    def test_overlapping_reads_share_one_snapshot(self):
        drop_dashboard_state()
        with tempfile.TemporaryDirectory() as d:
            store=Store(Path(d)/'lab.db')
            calls={'n':0}
            real=store.snapshot
            def wrapped():
                calls['n']+=1
                return real()
            store.snapshot=wrapped
            first=dashboard_state(store)
            second=dashboard_state(store)
            self.assertEqual(calls['n'],1)
            self.assertIs(first,second)
            names=[a['id'] for a in first['accounts']]
            self.assertIn('value-v1',names)
