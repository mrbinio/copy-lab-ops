import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from lab.core import Store
from lab.wallet_observation import ensure_schema, settle_batch


class ObservationSettlementFairnessTests(unittest.TestCase):
    def test_unresolved_batch_does_not_starve_ninth_after_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / 'lab.db')
            with store.connect() as db:
                ensure_schema(db)
                for index in range(9):
                    trade = {
                        'id': str(index), 'wallet': 'wallet', 'status': 'OPEN',
                        'end': 100, 'condition': str(index), 'token': 'yes',
                        'shares': 5_000_000, 'cost': 3_000_000, 'fee': 100_000,
                    }
                    db.execute(
                        'INSERT INTO wallet_observation_positions VALUES (?,?,?)',
                        (str(index), 'wallet', json.dumps(trade)),
                    )
            calls = []

            def fetch(url):
                condition = url.rsplit('/', 1)[-1]
                calls.append(condition)
                return {
                    'condition_id': condition,
                    'closed': condition == '8',
                    'tokens': [{'token_id': 'yes', 'winner': condition == '8'}],
                }

            asyncio.run(settle_batch(SimpleNamespace(
                store=store, clock=lambda: 1000, fetch=fetch,
            )))
            self.assertEqual(calls, [str(index) for index in range(8)])

            # A new copier object models a process restart. The persisted check
            # timestamps must allow row 9 through instead of retrying rows 1-8.
            asyncio.run(settle_batch(SimpleNamespace(
                store=store, clock=lambda: 1001, fetch=fetch,
            )))
            self.assertEqual(calls, [str(index) for index in range(9)])

            asyncio.run(settle_batch(SimpleNamespace(
                store=store, clock=lambda: 1302, fetch=fetch,
            )))
            with store.connect() as db:
                body = db.execute(
                    "SELECT body FROM wallet_observation_positions WHERE id='8'"
                ).fetchone()[0]
            settled = json.loads(body)
            self.assertEqual(settled['status'], 'SETTLED')
            self.assertEqual(settled['pnl_micro'], 1_900_000)


if __name__ == '__main__':
    unittest.main()
