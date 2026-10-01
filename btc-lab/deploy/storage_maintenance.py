"""Bounded cleanup of installer-owned artifacts; never data or credentials."""
import re
import shutil
import sqlite3
from pathlib import Path

BACKUP=re.compile(r'pre-(?:(btc|eth)-)?[0-9a-f]{12}-[0-9]+\.sqlite$')
RELEASE=re.compile(r'[0-9a-f]{12}-[0-9]+$')

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
            # Hot journals may belong to interrupted backups: leave untouched.
            if any(Path(str(p)+suffix).exists() for suffix in ('-journal','-wal','-shm')):continue
            if good[asset]>=2:
                p.unlink();removed.append(str(p));continue
            try:
                with sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True) as db:
                    valid=db.execute('PRAGMA quick_check').fetchall()==[('ok',)]
                    tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                    valid=valid and {'accounts','positions','ledger'}<=tables
                if valid:good[asset]+=1
            except sqlite3.Error:pass
    return removed

def ensure_backup_space(root):
    root=Path(root);required=256*1024**2  # 256 MB minimum free space
    free=shutil.disk_usage(root).free
    if free<required:raise RuntimeError(f'Za malo miejsca na backup: wolne {free/1024**3:.1f} GB, potrzeba {required/1024**3:.1f} GB. Usluga nie zostala zatrzymana.')
