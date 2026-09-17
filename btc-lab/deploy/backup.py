"""Consistent SQLite backup. Copy output encrypted to another host afterwards."""
import argparse
import sqlite3
from pathlib import Path

parser=argparse.ArgumentParser()
parser.add_argument('database')
parser.add_argument('destination')
args=parser.parse_args()
if Path(args.destination).exists():raise SystemExit('Refusing to overwrite an existing backup')
source=sqlite3.connect(f'file:{Path(args.database).resolve()}?mode=ro',uri=True)
target=sqlite3.connect(args.destination)
source.backup(target)
assert target.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
target.close();source.close()
print('Consistent backup created:',args.destination)
