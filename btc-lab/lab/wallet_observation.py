"""Versioned PAPER observation of the live copy policy.

This is not the independent hold-to-settlement study and it is not the
PAPER account. History starts at an explicit time. Older signals are not
repriced against today's book.
"""
import asyncio
import json
from urllib.parse import quote

from .copy_policy import POLICY, band_reason, confirmed_source_price, decide_buy, decide_sell, remember_fill
from .wallet_copy import (
    INITIAL, _event_size, exposure_block, market_spec, note_source_event, sell_cut,
)

OBSERVE_VERSION = 'copy-observe-v2'
PREVIOUS_OBSERVE_VERSION = 'copy-observe-v1'
META_KEY = 'wallet_observation_meta'


def ensure_schema(db):
    db.executescript('''
      CREATE TABLE IF NOT EXISTS wallet_observation_accounts(wallet TEXT PRIMARY KEY, cash INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS wallet_observation_positions(id TEXT PRIMARY KEY, wallet TEXT, body TEXT);
      CREATE TABLE IF NOT EXISTS wallet_observation_events(wallet TEXT, event_key TEXT, ts REAL, reason TEXT, body TEXT, PRIMARY KEY(wallet, event_key));
      CREATE TABLE IF NOT EXISTS wallet_observation_ledger(id TEXT PRIMARY KEY, wallet TEXT, amount INTEGER NOT NULL);
    ''')


def ensure_meta(store, now):
    """Set the start once. A later process must not move it backward.

    Moving the stored version forward does not turn older rows into evidence
    for the new rules, and it does not replay signals as new buys.
    """
    meta = store.get(META_KEY) or {}
    if meta.get('started_at'):
        meta.setdefault('paper_policy', POLICY)
        if meta.get('version') != OBSERVE_VERSION:
            meta['previous_version'] = meta.get('version') or PREVIOUS_OBSERVE_VERSION
            meta['version'] = OBSERVE_VERSION
            store.set(META_KEY, meta)
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
                ORDER BY a.first_seen DESC LIMIT ?''',
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

    with copier.store.connect() as db:
        ensure_schema(db)
        source_note = note_source_event(
            db, wallet, key, event, float(meta['started_at']), row['source_ts'], row['first_seen'])
    if row['source_ts'] < meta['started_at'] or now - row['source_ts'] > 90 or now - row['first_seen'] > 90:
        note('SOURCE_TOO_OLD')
        return
    if event.get('type') != 'TRADE' or event.get('side') not in ('BUY', 'SELL'):
        note('NOT_BUY_OR_SELL')
        return
    kind = event['side']
    source = None
    if kind == 'BUY':
        source, why = confirmed_source_price(event)
        if why:
            note(why)
            return
        why = band_reason(source)
        if why:
            note(why)
            return
    raw = await asyncio.to_thread(
        copier.fetch, 'https://gamma-api.polymarket.com/markets/slug/' + quote(str(event.get('slug', '')), safe=''))
    market = market_spec(raw, event, copier.clock())
    with copier.store.connect() as db:
        ensure_schema(db)
        db.execute('INSERT OR IGNORE INTO wallet_observation_accounts VALUES (?,?)', (wallet, INITIAL))
        cash = db.execute('SELECT cash FROM wallet_observation_accounts WHERE wallet=?', (wallet,)).fetchone()[0]
        positions = _positions(db, wallet)
    open_trade = next((item for item in positions if item.get('token') == market['token'] and item.get('status') == 'OPEN'), None)
    adding = kind == 'BUY' and open_trade is not None
    decision = await copier.book(market['token'])
    await copier.sleep(0.25)
    arrival = dict(await copier.book(market['token']))
    arrival['token'] = market['token']
    arrival['fee_rate'] = market['fee_rate']
    consumed = copier._obs_consumed
    if kind == 'BUY':
        if not adding and any(item.get('market') == market['slug'] and item.get('status') in ('OPEN', 'RESOLVED') for item in positions):
            note('COPY_POSITION_ALREADY_OPEN')
            return
        if not adding and cash < 5_000_000:
            note('COPY_CASH_LIMIT')
            return
        why, fill = decide_buy(source, arrival, consumed)
        if why:
            note(why)
            return
        remember_fill(consumed, arrival, fill)
        debit = int(fill['cost']) + int(fill['fee'])
        with copier.store.connect() as db:
            ensure_schema(db)
            db.execute('BEGIN IMMEDIATE')
            fresh = _positions(db, wallet)
            cash = db.execute('SELECT cash FROM wallet_observation_accounts WHERE wallet=?', (wallet,)).fetchone()[0]
            current = next((item for item in fresh if item.get('id') == (open_trade or {}).get('id')), None) if adding else None
            blocked = exposure_block(fresh, market['slug'], debit, not adding, cash)
            if blocked or (adding and (not current or current.get('status') != 'OPEN')):
                _record(db, wallet, key, copier.clock(), blocked or 'COPY_EXPOSURE_LIMIT',
                        {'policy': OBSERVE_VERSION, 'source_copy': 'skipped'})
                return
            if adding:
                current['shares'] = int(current['shares']) + int(fill['shares'])
                current['cost'] = int(current['cost']) + int(fill['cost'])
                current['fee'] = int(current['fee']) + int(fill['fee'])
                db.execute('UPDATE wallet_observation_positions SET body=? WHERE id=?', (json.dumps(current), current['id']))
                ledger_id = 'buy:' + current['id'] + ':' + key
            else:
                current = {
                    'id': wallet + ':' + key, 'wallet': wallet, 'policy': OBSERVE_VERSION, 'paper_policy': POLICY,
                    'market': market['slug'], 'condition': market['condition'], 'token': market['token'],
                    'side': market['side'], 'end': market['end'],
                    'status': 'OPEN', 'opened': copier.clock(), 'shares': fill['shares'], 'cost': fill['cost'],
                    'fee': fill['fee'], 'exit_fee': 0, 'entry_fill': fill,
                }
                db.execute('INSERT INTO wallet_observation_positions VALUES (?,?,?)', (current['id'], wallet, json.dumps(current)))
                ledger_id = 'buy:' + current['id']
            db.execute('UPDATE wallet_observation_accounts SET cash=cash+? WHERE wallet=?', (-debit, wallet))
            db.execute('INSERT INTO wallet_observation_ledger VALUES (?,?,?)', (ledger_id, wallet, -debit))
            _record(db, wallet, key, copier.clock(), 'OBSERVED_BUY', {'policy': OBSERVE_VERSION, 'fill': fill})
        return
    if not open_trade:
        note('NO_COPIED_POSITION')
        return
    if _event_size(event) is None:
        note('SOURCE_SIZE_MISSING', {'source_copy': 'unknown'})
        return
    proportion = None if not source_note else source_note.get('proportion')
    if proportion is None:
        note('SOURCE_PROPORTION_UNKNOWN', {'source_copy': 'unknown'})
        return
    sold, why = sell_cut(open_trade['shares'], proportion)
    if why:
        note(why, {'source_copy': 'unknown'})
        return
    why, fill = decide_sell(arrival, sold, consumed)
    if why:
        note(why)
        return
    remember_fill(consumed, arrival, fill)
    whole = int(open_trade['shares'])
    if int(sold) >= whole:
        pnl = fill['proceeds'] - fill['fee'] - open_trade['cost'] - open_trade['fee']
        open_trade.update(status='CLOSED', payout=fill['proceeds'], exit_fee=fill['fee'], closed_at=copier.clock(), pnl_micro=pnl)
        credit = fill['proceeds'] - fill['fee']
        with copier.store.connect() as db:
            ensure_schema(db)
            db.execute('BEGIN IMMEDIATE')
            db.execute('UPDATE wallet_observation_positions SET body=? WHERE id=?', (json.dumps(open_trade), open_trade['id']))
            db.execute('UPDATE wallet_observation_accounts SET cash=cash+? WHERE wallet=?', (credit, wallet))
            db.execute('INSERT INTO wallet_observation_ledger VALUES (?,?,?)', ('close:' + open_trade['id'], wallet, credit))
            _record(db, wallet, key, copier.clock(), 'OBSERVED_SELL', {
                'policy': OBSERVE_VERSION, 'fill': fill, 'pnl_micro': pnl, 'source_copy': 'matched',
                'source_proportion': format(proportion, 'f'),
            })
        return
    alloc_cost = int(open_trade['cost']) * int(sold) // whole
    alloc_fee = int(open_trade['fee']) * int(sold) // whole
    pnl = fill['proceeds'] - fill['fee'] - alloc_cost - alloc_fee
    slice_id = open_trade['id'] + ':sell:' + key
    closed = dict(open_trade)
    closed.update(id=slice_id, status='CLOSED', shares=int(sold), cost=alloc_cost, fee=alloc_fee,
                  payout=fill['proceeds'], exit_fee=fill['fee'], closed_at=copier.clock(), pnl_micro=pnl)
    open_trade['shares'] = whole - int(sold)
    open_trade['cost'] = int(open_trade['cost']) - alloc_cost
    open_trade['fee'] = int(open_trade['fee']) - alloc_fee
    credit = fill['proceeds'] - fill['fee']
    with copier.store.connect() as db:
        ensure_schema(db)
        db.execute('BEGIN IMMEDIATE')
        db.execute('INSERT INTO wallet_observation_positions VALUES (?,?,?)', (slice_id, wallet, json.dumps(closed)))
        db.execute('UPDATE wallet_observation_positions SET body=? WHERE id=?', (json.dumps(open_trade), open_trade['id']))
        db.execute('UPDATE wallet_observation_accounts SET cash=cash+? WHERE wallet=?', (credit, wallet))
        db.execute('INSERT INTO wallet_observation_ledger VALUES (?,?,?)', ('close:' + slice_id, wallet, credit))
        _record(db, wallet, key, copier.clock(), 'OBSERVED_SELL', {
            'policy': OBSERVE_VERSION, 'fill': fill, 'pnl_micro': pnl, 'partial': True,
            'source_copy': 'matched', 'source_proportion': format(proportion, 'f'),
        })


def _needs_book(row, meta, now):
    """A price or age reject does not need a book. Those stay off the slow slots."""
    event = json.loads(row['body'])
    if row['source_ts'] < meta['started_at'] or now - row['source_ts'] > 90 or now - row['first_seen'] > 90:
        return False
    if event.get('type') != 'TRADE' or event.get('side') not in ('BUY', 'SELL'):
        return False
    if event.get('side') == 'BUY':
        price, why = confirmed_source_price(event)
        if why or band_reason(price):
            return False
    return True


async def settle_batch(copier, limit=8):
    """Official settlement for observation positions. A missing result stays open.

    The same 300 second wait the PAPER book uses. This does not invent a sell.
    """
    now = copier.clock()
    with copier.store.connect() as db:
        ensure_schema(db)
        rows = [json.loads(body) for (body,) in db.execute('SELECT body FROM wallet_observation_positions')]
    closed = 0
    for trade in rows:
        if trade.get('status') == 'RESOLVED' and now >= float(trade.get('official_seen_at') or 0) + 300:
            _settle_close(copier.store, trade, now)
            closed += 1
    fetched = 0
    for trade in rows:
        if fetched >= limit:
            break
        if trade.get('status') != 'OPEN' or now < float(trade.get('end') or now + 1):
            continue
        fetched += 1
        try:
            condition = trade.get('condition')
            if not condition:
                raw = await asyncio.to_thread(
                    copier.fetch, 'https://gamma-api.polymarket.com/markets/slug/' + quote(str(trade.get('market') or ''), safe=''))
                condition = raw.get('conditionId')
                trade['condition'] = condition
            if not condition:
                continue
            raw = await asyncio.to_thread(copier.fetch, 'https://clob.polymarket.com/markets/' + quote(str(condition), safe=''))
            if raw.get('condition_id') != condition:
                continue
            winners = [item for item in raw.get('tokens', []) if item.get('winner') is True]
            if raw.get('closed') is not True or len(winners) != 1:
                continue
            tokens = {str(item.get('token_id')) for item in raw.get('tokens', [])}
            if str(trade.get('token')) not in tokens:
                continue
            trade.update(status='RESOLVED', official_seen_at=copier.clock(), condition=condition,
                         official_payout=trade['shares'] if str(winners[0]['token_id']) == str(trade.get('token')) else 0)
            with copier.store.connect() as db:
                ensure_schema(db)
                current = db.execute('SELECT body FROM wallet_observation_positions WHERE id=?', (trade['id'],)).fetchone()
                if not current or json.loads(current[0]).get('status') != 'OPEN':
                    continue
                db.execute('UPDATE wallet_observation_positions SET body=? WHERE id=?', (json.dumps(trade), trade['id']))
        except Exception:
            continue
    return closed


def _settle_close(store, trade, now):
    payout = int(trade.get('official_payout') or 0)
    pnl = payout - int(trade.get('cost') or 0) - int(trade.get('fee') or 0)
    trade = dict(trade)
    trade.update(status='SETTLED', payout=payout, exit_fee=0, closed_at=now, resolved=now, pnl_micro=pnl)
    with store.connect() as db:
        ensure_schema(db)
        db.execute('BEGIN IMMEDIATE')
        current = db.execute('SELECT body FROM wallet_observation_positions WHERE id=?', (trade['id'],)).fetchone()
        if not current or json.loads(current[0]).get('status') != 'RESOLVED':
            return
        db.execute('INSERT OR IGNORE INTO wallet_observation_accounts VALUES (?,?)', (trade['wallet'], INITIAL))
        db.execute('UPDATE wallet_observation_positions SET body=? WHERE id=?', (json.dumps(trade), trade['id']))
        db.execute('UPDATE wallet_observation_accounts SET cash=cash+? WHERE wallet=?', (payout, trade['wallet']))
        db.execute('INSERT OR IGNORE INTO wallet_observation_ledger VALUES (?,?,?)', ('close:' + trade['id'], trade['wallet'], payout))


async def observe_batch(copier):
    meta = ensure_meta(copier.store, copier.clock())
    if not hasattr(copier, '_obs_consumed'):
        copier._obs_consumed = {}
    rows = await asyncio.to_thread(due_rows, copier.store, meta, copier.clock(), 40)
    slow = 0
    now = copier.clock()
    for row in rows:
        if _needs_book(row, meta, now):
            if slow >= 6:
                continue
            slow += 1
        try:
            await apply_row(copier, row, meta)
        except Exception as error:
            with copier.store.connect() as db:
                ensure_schema(db)
                _record(db, row['wallet'], row['event_key'], copier.clock(), 'ERROR',
                        {'policy': OBSERVE_VERSION, 'error': str(error)[:200]})
    await settle_batch(copier)
    return len(rows)
