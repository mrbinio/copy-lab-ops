import os
import sqlite3
import tempfile
import unittest

from lab import worker


class WalTests(unittest.TestCase):
    def test_small_log_gets_a_passive_checkpoint_big_one_truncate(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 't.sqlite')
            db = sqlite3.connect(path)
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE t(x)')
            db.execute('INSERT INTO t VALUES (1)')
            db.commit()
            self.assertEqual(worker.wal_checkpoint(path)[0], 'PASSIVE')
            saved = worker.WAL_TRUNCATE_ABOVE
            worker.WAL_TRUNCATE_ABOVE = -1
            try:
                self.assertEqual(worker.wal_checkpoint(path)[0], 'TRUNCATE')
            finally:
                worker.WAL_TRUNCATE_ABOVE = saved
                db.close()


if __name__ == '__main__':
    unittest.main()
