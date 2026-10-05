"""Versioned PAPER observation of the live copy policy.

This is not the independent hold-to-settlement study and it is not the
PAPER account. History starts at an explicit time. Older signals are not
repriced against today's book.
"""
import asyncio
import json
from urllib.parse import quote

from .copy_policy import POLICY, band_reason, confirmed_source_price, decide_buy, decide_sell, remember_fill
from .wallet_copy import INITIAL, market_spec

OBSERVE_VERSION = 'copy-observe-v1'
META_KEY = 'wallet_observation_meta'


def ensure_schema(db):
    db.executescript('''
      CREATE TABLE IF NOT EXISTS wallet_observation_accounts(wallet TEXT PRIMARY KEY, cash INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS wallet_observation_positions(id TEXT PRIMARY KEY, wallet TEXT, body TEXT);
      CREATE TABLE IF NOT EXISTS wallet_observation_events(wallet TEXT, event_key TEXT, ts REAL, reason TEXT, body TEXT, PRIMARY KEY(wallet, event_key));
      CREATE TABLE IF NOT EXISTS wallet_observation_ledger(id TEXT PRIMARY KEY, wallet TEXT, amount INTEGER NOT NULL);
    ''')


def ensure_meta(store, now):
    """Set the start once. A later process must not move it backward."""
    meta = store.get(META_KEY) or {}
    if meta.get('started_at'):
        meta.setdefault('version', OBSERVE_VERSION)
        meta.setdefault('paper_policy', POLICY)
        return meta
    meta = {'version': OBSERVE_VERSION, 'paper_policy': POLICY, 'started_at': now}
    store.set(META_KEY, meta)
    return meta


def due_rows(store, meta, now, limit=4):
    started = float(meta['started_at'])
    roster = (store.get('wallet_roster') or {}).get('wallets') or {}
    wallets = [wallet for wallet, row in roster.items() if row.get('state') in ('observed', 'paused')]
    if not wallets:
        return []
    fresh = max(started, now - 90)
    marks = ','.join('?' * len(wallets))
    with store.connect() as db:
        ensure_schema(db)
        return [dict(row) for row in db.execute(
            f'''SELECT a.* FROM wallet_activity a
                LEFT JOIN wallet_observation_events e
                  ON a.wallet=e.wallet AND a.event_key=e.event_key
                WHERE e.event_key IS NULL AND a.wallet IN ({marks})
                  AND a.source_ts>=? AND a.first_seen>=?
                ORDER BY a.first_seen ASC LIMIT ?''',
            (*wallets, fresh, started, limit),
        )]


def _positions(db, wallet):
    return [json.loads(row[0]) for row in db.execute(
        'SELECT body FROM wallet_observation_positions WHERE wallet=?', (wallet,))]


def _record(db, wallet, key, now, reason, body):
    db.execute(
        'INSERT OR REPLACE INTO wallet_observation_events VALUES (?,?,?,?,?)',
        (wallet, key, now, reason, json.dumps(body)),
    )


async def apply_row(copier, row, meta):
    """One fresh signal. Writes only the observation tables."""
    wallet = row['wallet']
    key = row['event_key']
    event = json.loads(row['body'])
    now = copier.clock()

    def note(reason, extra=None):
        body = {'policy': OBSERVE_VERSION, 'paper_policy': POLICY, 'reason': reason, 'source_event': event}
        if extra:
            body.update(extra)
        with copier.store.connect() as db:
            ensure_schema(db)
            _record(db, wallet, key, now, reason, body)

    if row['source_ts'] < meta['started_at'] or now - row['source_ts'] > 90 or now - row['first_seen'] > 90:
        note('SOURCE_TOO_OLD')
        return
    if event.get('type') != 'TRADE' or event.get('side') not in ('BUY', 'SELL'):
        note('NOT_BUY_OR_SELL')
        return
    raw = await asyncio.to_thread(
        copier.fetch, 'https://gamma-api.polymarket.com/markets/slug/' + quote(str(event.get('slug', '')), safe=''))
    market = market_spec(raw, event, copier.clock())
    kind = event['side']
    with copier.store.connect() as db:
        ensure_schema(db)
        db.execute('INSERT OR IGNORE INTO wallet_observation_accounts VALUES (?,?)', (wallet, INITIAL))
        cash = db.execute('SELECT cash FROM wallet_observation_accounts WHERE wallet=?', (wallet,)).fetchone()[0]
        positions = _positions(db, wallet)
    open_trade = next((item for item in positions if item.get('token') == market['token'] and item.get('status') == 'OPEN'), None)
    decision = await copier.book(market['token'])
    await copier.sleep(0.25)
    arrival = dict(await copier.book(market['token']))
    arrival['token'] = market['token']
    arrival['fee_rate'] = market['fee_rate']
    consumed = copier._obs_consumed
    if kind == 'BUY':
        source, why = confirmed_source_price(event)
        if why:
            note(why)
            return
        why = band_reason(source)
        if why:
            note(why)
            return
        if any(item.get('market') == market['slug'] and item.get('status') in ('OPEN', 'RESOLVED') for item in positions):
            note('COPY_POSITION_ALREADY_OPEN')
            return
        if cash < 5_000_000:
            note('COPY_CASH_LIMIT')
            return
        why, fill = decide_buy(source, arrival, consumed)
        if why:
            note(why)
            return
        remember_fill(consumed, arrival, fill)
        trade = {
            'id': wallet + ':' + key, 'wallet': wallet, 'policy': OBSERVE_VERSION, 'paper_policy': POLICY,
            'market': market['slug'], 'token': market['token'], 'side': market['side'], 'end': market['end'],
            'status': 'OPEN', 'opened': copier.clock(), 'shares': fill['shares'], 'cost': fill['cost'],
            'fee': fill['fee'], 'exit_fee': 0, 'entry_fill': fill,
        }
        debit = -(fill['cost'] + fill['fee'])
        with copier.store.connect() as db:
            ensure_schema(db)
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT INTO wallet_observation_positions VALUES (?,?,?)', (trade['id'], wallet, json.dumps(trade)))
            db.execute('UPDATE wallet_observation_accounts SET cash=cash+? WHERE wallet=?', (debit, wallet))
            db.execute('INSERT INTO wallet_observation_ledger VALUES (?,?,?)', ('buy:' + trade['id'], wallet, debit))
            _record(db, wallet, key, copier.clock(), 'OBSERVED_BUY', {'policy': OBSERVE_VERSION, 'fill': fill})
        return
    if not open_trade:
        note('NO_COPIED_POSITION')
        return
    why, fill = decide_sell(arrival, open_trade['shares'], consumed)
    if why:
        note(why)
        return
    remember_fill(consumed, arrival, fill)
    pnl = fill['proceeds'] - fill['fee'] - open_trade['cost'] - open_trade['fee']
    open_trade.update(status='CLOSED', payout=fill['proceeds'], exit_fee=fill['fee'], closed_at=copier.clock(), pnl_micro=pnl)
    credit = fill['proceeds'] - fill['fee']
    with copier.store.connect() as db:
        ensure_schema(db)
        db.execute('BEGIN IMMEDIATE')
        db.execute('UPDATE wallet_observation_positions SET body=? WHERE id=?', (json.dumps(open_trade), open_trade['id']))
        db.execute('UPDATE wallet_observation_accounts SET cash=cash+? WHERE wallet=?', (credit, wallet))
        db.execute('INSERT INTO wallet_observation_ledger VALUES (?,?,?)', ('close:' + open_trade['id'], wallet, credit))
        _record(db, wallet, key, copier.clock(), 'OBSERVED_SELL', {'policy': OBSERVE_VERSION, 'fill': fill, 'pnl_micro': pnl})


async def observe_batch(copier):
    meta = ensure_meta(copier.store, copier.clock())
    if not hasattr(copier, '_obs_consumed'):
        copier._obs_consumed = {}
    rows = await asyncio.to_thread(due_rows, copier.store, meta, copier.clock())
    for row in rows:
        try:
            await apply_row(copier, row, meta)
        except Exception as error:
            with copier.store.connect() as db:
                ensure_schema(db)
                _record(db, row['wallet'], row['event_key'], copier.clock(), 'ERROR',
                        {'policy': OBSERVE_VERSION, 'error': str(error)[:200]})
    return len(rows)
