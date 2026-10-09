"""Bank 40% of each new high of a ledger's closed result.

Damian, 9 Oct 2026: a win that only wins back an earlier loss is not
profit. Each ledger (Mitch, the wallet qualifier) keeps its closed result
(realized) and its best level so far (peak), across all its accounts, in
time order. A close that lifts realized above peak reserves 40% of the
rise. A loss lowers realized and leaves the reserve alone. Banked stays
banked. The ledgers are separate books and are not summed into one peak.

The earlier rule banked 40% of every winning close and ignored losses: on
9 Oct it showed 283 USD reserved while the two ledgers had lost 384 USD.

The per-account `reserved` column stays for the buy check (cash minus
reserved). Under this rule it is zero; on LIVE the reserve leaves the
trading wallet instead.
"""
import json
import time
from decimal import Decimal

RESERVE_PCT = Decimal('0.40')
RULE = 'ledger-high-water-40-v1'
LEDGERS = {'mitch_accounts': 'mitch_positions', 'wallet_copy_accounts': 'wallet_copy_positions'}


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


def _key(table):
    return 'profit_bank:' + table


def ledger_state(db, table):
    row = db.execute('SELECT body FROM state WHERE key=?', (_key(table),)).fetchone()
    body = json.loads(row[0]) if row else {}
    return {
        'rule': body.get('rule'),
        'realized_micro': int(body.get('realized_micro') or 0),
        'peak_micro': int(body.get('peak_micro') or 0),
        'reserved_micro': int(body.get('reserved_micro') or 0),
        'peak_at': body.get('peak_at'),
        'previous_rule_reserved_micro': body.get('previous_rule_reserved_micro'),
    }


def _save(db, table, state):
    db.execute(
        "INSERT INTO state VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET body=excluded.body",
        (_key(table), json.dumps(state)),
    )


def _closes(db, positions_table):
    out = []
    for (body,) in db.execute('SELECT body FROM %s' % positions_table):
        trade = json.loads(body)
        # RESOLVED still waits for its cash; its close calls lock_profit later.
        if trade.get('status') in ('OPEN', 'RESOLVED'):
            continue
        if trade.get('pnl_micro') is None or not trade.get('closed_at'):
            continue
        out.append((float(trade['closed_at']), int(trade['pnl_micro'])))
    return sorted(out)


def rebuild_high_water(db, table, positions_table):
    """Replay the ledger's closes once under this rule. Returns True when it ran."""
    ensure_reserved_column(db, table)
    if ledger_state(db, table)['rule'] == RULE:
        return False
    before = int(db.execute('SELECT COALESCE(SUM(reserved),0) FROM %s' % table).fetchone()[0] or 0)
    realized = peak = reserved = 0
    peak_at = None
    for at, pnl in _closes(db, positions_table):
        realized += pnl
        if realized > peak:
            reserved += int(Decimal(realized - peak) * RESERVE_PCT)
            peak = realized
            peak_at = at
    db.execute('UPDATE %s SET reserved=0' % table)
    _save(db, table, {
        'rule': RULE, 'realized_micro': realized, 'peak_micro': peak,
        'reserved_micro': reserved, 'peak_at': peak_at,
        'previous_rule_reserved_micro': before,
    })
    return True


def lock_profit(db, table, wallet, pnl_micro):
    """Record a close in its ledger. Reserve 40% of the part above the ledger's peak."""
    if pnl_micro is None:
        return 0
    state = ledger_state(db, table)
    state['rule'] = RULE
    state['realized_micro'] += int(pnl_micro)
    add = 0
    if state['realized_micro'] > state['peak_micro']:
        add = int(Decimal(state['realized_micro'] - state['peak_micro']) * RESERVE_PCT)
        state['peak_micro'] = state['realized_micro']
        state['peak_at'] = time.time()
    state['reserved_micro'] += add
    _save(db, table, state)
    return add


def bank_snapshot(db):
    """Visible PAPER bank: each ledger's reserve and the sum shown on the board."""
    has_state = db.execute("SELECT 1 FROM sqlite_master WHERE name='state'").fetchone()
    ledgers = {table: ledger_state(db, table) if has_state else {} for table in LEDGERS}
    mitch = int((ledgers.get('mitch_accounts') or {}).get('reserved_micro') or 0)
    copy = int((ledgers.get('wallet_copy_accounts') or {}).get('reserved_micro') or 0)
    return {
        'id': 'profit-bank',
        'label': 'Rezerwa zysku',
        'reserved_micro': mitch + copy,
        'mitch_reserved_micro': mitch,
        'copy_reserved_micro': copy,
        'ledgers': ledgers,
        'reserve_pct': float(RESERVE_PCT),
        'rule': RULE,
        'live': False,
        'note': '40% z każdego nowego szczytu wyniku netto księgi (Mitch i kwalifikator osobno). '
                'Wygrana, która tylko odrabia stratę, nic nie dodaje. Raz odłożone zostaje. PAPER.',
    }
