"""Bank a share of a closed win. The rest stays tradable cash.

Reserved cash is still on the account. It is not a second ledger and it is
not a reset of losses. Only a later close with a positive pnl adds to it.
"""
from decimal import Decimal

RESERVE_PCT = Decimal('0.40')


def ensure_reserved_column(db, table):
    columns = [row[1] for row in db.execute('PRAGMA table_info(%s)' % table)]
    if 'reserved' not in columns:
        db.execute(
            'ALTER TABLE %s ADD COLUMN reserved INTEGER NOT NULL DEFAULT 0' % table
        )


def reserved_of(db, table, wallet):
    row = db.execute(
        'SELECT reserved FROM %s WHERE wallet=?' % table, (wallet,),
    ).fetchone()
    if not row or row[0] is None:
        return 0
    return int(row[0])


def tradable_cash(cash, reserved):
    return int(cash) - int(reserved or 0)


def bank_snapshot(db):
    """Visible PAPER bank. Reserved cash stays in the books; this is the sum."""
    mitch = 0
    copy = 0
    if db.execute("SELECT 1 FROM sqlite_master WHERE name='mitch_accounts'").fetchone():
        ensure_reserved_column(db, 'mitch_accounts')
        mitch = int(db.execute('SELECT COALESCE(SUM(reserved),0) FROM mitch_accounts').fetchone()[0] or 0)
    if db.execute("SELECT 1 FROM sqlite_master WHERE name='wallet_copy_accounts'").fetchone():
        ensure_reserved_column(db, 'wallet_copy_accounts')
        copy = int(db.execute('SELECT COALESCE(SUM(reserved),0) FROM wallet_copy_accounts').fetchone()[0] or 0)
    return {
        'id': 'profit-bank',
        'label': 'Rezerwa zysku',
        'reserved_micro': mitch + copy,
        'mitch_reserved_micro': mitch,
        'copy_reserved_micro': copy,
        'reserve_pct': float(RESERVE_PCT),
        'live': False,
        'note': '40% z nowych zamkniętych plusów. PAPER. Nie LIVE u Mitcha.',
    }


def lock_profit(db, table, wallet, pnl_micro):
    """Move 40% of a closed win out of the spendable balance. A loss is not touched."""
    if pnl_micro is None:
        return 0
    pnl = int(pnl_micro)
    if pnl <= 0:
        return 0
    add = int(Decimal(pnl) * RESERVE_PCT)
    if add <= 0:
        return 0
    db.execute(
        'UPDATE %s SET reserved=reserved+? WHERE wallet=?' % table,
        (add, wallet),
    )
    return add
