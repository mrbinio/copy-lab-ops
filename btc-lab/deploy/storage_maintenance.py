"""Bounded cleanup of installer-owned artifacts; never data or credentials."""
import re
import shutil
import sqlite3
import time
from pathlib import Path

BACKUP=re.compile(r'pre-(?:(btc|eth)-)?[0-9a-f]{12}-[0-9]+\.sqlite$')
RELEASE=re.compile(r'[0-9a-f]{12}-[0-9]+$')
# 0-byte leftover WAL from a finished copy is not a live writer.
STALE_JOURNAL_SECONDS=3600

def _journal_hot(path):
    """True only when a WAL/journal still looks like an in-progress writer."""
    now=time.time()
    for suffix in ('-journal','-wal'):
        journal=Path(str(path)+suffix)
        if journal.exists() and journal.stat().st_size>0 and now-journal.stat().st_mtime<STALE_JOURNAL_SECONDS:
            return True
    return False

def _drop_journals(path):
    for suffix in ('-journal','-wal','-shm','.partial','.partial-wal','.partial-shm'):
        extra=Path(str(path)+suffix)
        if extra.exists() and extra.is_file() and not extra.is_symlink():
            extra.unlink()

def cleanup(root,protected=()):
    root=Path(root);removed=[]
    releases=root/'releases'
    if releases.is_dir() and not releases.is_symlink():
        candidates=sorted((p for p in releases.iterdir() if p.is_dir() and not p.is_symlink() and RELEASE.fullmatch(p.name)),key=lambda p:p.stat().st_mtime,reverse=True)
        keep={Path(p).resolve() for p in protected}|{p.resolve() for p in candidates[:2]}
        for p in candidates:
            if p.resolve() not in keep:shutil.rmtree(p);removed.append(str(p))
    backups=root/'backups'
    if backups.is_dir() and not backups.is_symlink():
        candidates=sorted((p for p in backups.iterdir() if p.is_file() and not p.is_symlink() and BACKUP.fullmatch(p.name)),key=lambda p:p.stat().st_mtime,reverse=True)
        good={'btc':0,'eth':0}
        for p in candidates:
            asset=BACKUP.fullmatch(p.name).group(1) or 'btc'
            if _journal_hot(p):
                continue
            _drop_journals(p)
            if good[asset]>=2:
                p.unlink();removed.append(str(p));continue
            try:
                with sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True) as db:
                    valid=db.execute('PRAGMA quick_check').fetchall()==[('ok',)]
                    tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                    valid=valid and {'accounts','positions','ledger'}<=tables
                if valid:good[asset]+=1
            except sqlite3.Error:pass
        for leftover in backups.iterdir():
            name=leftover.name
            if leftover.is_file() and not leftover.is_symlink() and (name.endswith(('-wal','-shm','-journal')) or '.partial' in name):
                leftover.unlink();removed.append(str(leftover))
    return removed

def ensure_backup_space(root):
    root=Path(root);required=256*1024**2  # 256 MB minimum free space
    free=shutil.disk_usage(root).free
    if free<required:raise RuntimeError(f'Za malo miejsca na backup: wolne {free/1024**3:.1f} GB, potrzeba {required/1024**3:.1f} GB. Usluga nie zostala zatrzymana.')
