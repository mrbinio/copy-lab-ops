import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'deploy'))
from storage_maintenance import cleanup,ensure_backup_space
from lab.core import Store,simulate_fill

class CapacityTests(unittest.TestCase):
    def test_remaining_week_capacity_preserves_loss_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'db');now=1800000000
            with store.connect() as db:
                db.execute("INSERT INTO positions(strategy,market,side,shares,cost,fee,opened,status,payout,resolved,redeemed,evidence) VALUES ('mid-window-v1','old','Up',1,25426114,0,?,'REDEEMED',0,?,?,'{}')",(now-90000,)*3)
                db.execute("UPDATE accounts SET cash=cash-25426114 WHERE strategy='mid-window-v1'")
            cap=store.entry_capacity('mid-window-v1',now);self.assertEqual(cap,4573886)
            fill=simulate_fill([['.60','100']],str((cap-100)/1e6/1.07),'.60','.07','5','.01')
            self.assertIsNotNone(fill);self.assertLessEqual(fill['cost']+fill['fee'],cap)
            self.assertEqual(store.open('mid-window-v1','new','Up',fill,{},now),'FILLED')
            self.assertEqual(store.entry_capacity('mid-window-v1',now),0)

class CleanupTests(unittest.TestCase):
    def test_preserves_active_two_good_backups_data_and_unknown_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'releases').mkdir();(root/'backups').mkdir();(root/'data').mkdir()
            sentinel=root/'data/lab.sqlite';sentinel.write_text('never delete')
            dirs=[]
            for i in range(4):
                p=root/'releases'/('a'*12+'-'+str(i));p.mkdir();os.utime(p,(i,i));dirs.append(p)
            backups=[]
            for asset in ('btc','eth'):
                for i in range(3):
                    p=root/'backups'/f'pre-{asset}-aaaaaaaaaaaa-{i}.sqlite'
                    with sqlite3.connect(p) as db:
                        for table in ('accounts','positions','ledger'):db.execute(f'CREATE TABLE {table}(id INTEGER)')
                    os.utime(p,(i,i));backups.append(p)
            bad=root/'backups'/'pre-btc-aaaaaaaaaaaa-99.sqlite';bad.write_text('incomplete');os.utime(bad,(99,99))
            unknown=root/'backups'/'manual.sqlite';unknown.write_text('keep')
            cleanup(root,[dirs[0]])
            self.assertTrue(dirs[0].exists());self.assertFalse(dirs[1].exists());self.assertTrue(dirs[2].exists());self.assertTrue(dirs[3].exists())
            self.assertEqual(sum(p.exists() for p in backups),4)
            self.assertTrue(bad.exists());self.assertTrue(unknown.exists());self.assertEqual(sentinel.read_text(),'never delete')
    def test_space_preflight_does_not_mutate_data(self):
        with tempfile.TemporaryDirectory() as tmp,patch('storage_maintenance.shutil.disk_usage') as usage:
            usage.return_value.free=1
            with self.assertRaisesRegex(RuntimeError,'Usluga nie zostala zatrzymana'):ensure_backup_space(tmp)
    def test_stale_zero_wal_does_not_block_old_backup_delete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'backups').mkdir()
            kept=[]
            for i in range(3):
                p=root/'backups'/f'pre-btc-aaaaaaaaaaaa-{i}.sqlite'
                with sqlite3.connect(p) as db:
                    for table in ('accounts','positions','ledger'):db.execute(f'CREATE TABLE {table}(id INTEGER)')
                os.utime(p,(i,i))
                Path(str(p)+'-wal').write_bytes(b'')
                Path(str(p)+'-shm').write_bytes(b'\x00'*32)
                os.utime(Path(str(p)+'-wal'),(i,i));os.utime(Path(str(p)+'-shm'),(i,i))
                kept.append(p)
            cleanup(root)
            self.assertFalse(kept[0].exists())
            self.assertTrue(kept[1].exists())
            self.assertTrue(kept[2].exists())
            self.assertFalse(Path(str(kept[0])+'-wal').exists())
    def test_prune_ephemeral_keeps_fresh_and_other_kinds(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'db');now=1_800_000_000
            store.record('book',{'old':True},now-50*3600)
            store.record('book',{'fresh':True},now-3600)
            store.record('private',{'keep':True},now-50*3600)
            self.assertEqual(store.prune_ephemeral(now=now,keep_seconds=48*3600,limit=100),1)
            with store.connect() as db:
                kinds=[r[0] for r in db.execute('SELECT kind FROM observations ORDER BY id')]
            self.assertEqual(kinds,['book','private'])
