"""PAPER copy of five Bitcoin 15-minute wallets. Separate from the qualifier book.

mitch-copy-wallets-v1 follows the sizing, window caps and one-sided 10 cent
rule Mitch wrote down. It does not use the other project's profit gate,
loss pause, price band or single-position rule. It never writes that ledger.
"""
import asyncio
import json
import logging
import time
from decimal import Decimal, ROUND_FLOOR
from zoneinfo import ZoneInfo

from .core import simulate_fill

log = logging.getLogger('lab.mitch')
SPEC = 'mitch-copy-wallets-v1'
STOCKHOLM = ZoneInfo('Europe/Stockholm')
PRICE_WORSE = Decimal('0.10')
# Mitch did not name a paper bankroll. This only keeps the window caps
# from being confused with an empty account. It is not his rule.
CAPITAL_MICRO = 500_000_000
ASSUMPTIONS = (
    'A sell does not restore the buy budget already used in that window. Needs Mitch to confirm.',
    'The $20 and $5 caps include the buy cost and the entry fee. Exit fees are only in the net result. Needs Mitch to confirm.',
    'A partial sell uses source shares sold divided by source shares just before that sell. Needs Mitch to confirm.',
    'Paper capital is $500 per wallet because Mitch did not set it. The window caps are the binding limit.',
)
GROUPING = (
    'One activity row is one buy. The shared collector key is transaction hash, '
    'type, token and side, without size or log index, so several fills of one '
    'transaction collapse before this project sees them. D is price times shares '
    'on that single stored row. A repeated event, or the same transaction, token '
    'and side, is not a second buy.'
)

WALLETS = {
    '0x16217458b59b3458149918058754cd234096b159': {'label': '096b159', 'limit_usd': Decimal('20')},
    '0xeda9247a2b3c99a9e0bf46cdac6e1974365cf589': {'label': '0x9f672c31', 'limit_usd': Decimal('20')},
    '0x943cea746e701823b6902a6f4eaeed58207e77c2': {'label': '0xdc27', 'limit_usd': Decimal('20')},
    '0x454c48b436e5dda7a186cc7e0ebeee2a1d1865cf': {'label': 'checkr3', 'limit_usd': Decimal('20')},
    '0xa82365c8e854728c472812fba6202ca125386215': {'label': 'mihaXd', 'limit_usd': Decimal('5')},
}


def copy_notional_usd(source_usd):
    """min(D, 15) + 5% of anything above 15. The window cap is applied later."""
    d = Decimal(str(source_usd))
    if d < 0:
        raise ValueError('negative source dollars')
    return min(d, Decimal('15')) + Decimal('0.05') * max(d - Decimal('15'), Decimal('0'))


def price_allows(copy_price, source_price):
    """One-sided. A better price is allowed. Exactly 10 cents worse is allowed."""
    return Decimal(str(copy_price)) <= Decimal(str(source_price)) + PRICE_WORSE


def sell_fraction(sold_shares, shares_before):
    """Unknown history is not a guessed fraction."""
    if shares_before is None:
        return None
    before = Decimal(str(shares_before))
    sold = Decimal(str(sold_shares))
    if before <= 0 or sold <= 0 or sold > before:
        return None
    return sold / before


def our_sell_shares(our_shares, fraction):
    if fraction is None:
        return None
    whole = int(our_shares)
    cut = int((Decimal(whole) * Decimal(str(fraction))).to_integral_value(rounding=ROUND_FLOOR))
    if cut <= 0:
        return None
    return min(cut, whole)


def source_dollars(event):
    """Dollars the source spent. A chain-fast book quote is not his price."""
    if not isinstance(event, dict):
        return None
    if event.get('_source') == 'chain_fast':
        return None
    try:
        if event.get('usdcSize') not in (None, ''):
            dollars = Decimal(str(event['usdcSize']))
        else:
            dollars = Decimal(str(event['price'])) * Decimal(str(event['size']))
    except Exception:
        return None
    if not dollars.is_finite() or dollars <= 0:
        return None
    return dollars


def source_price(event):
    if not isinstance(event, dict) or event.get('_source') == 'chain_fast':
        return None
    try:
        price = Decimal(str(event.get('price')))
    except Exception:
        return None
    if not price.is_finite() or not 0 < price < 1:
        return None
    return price


def is_btc_15m(event):
    slug = str((event or {}).get('slug') or '')
    return slug.startswith('btc-updown-15m-')


def _percentile(values, p):
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * p
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    weight = rank - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


def latency_summary(rows):
    totals = [r['total_ms'] for r in rows if r.get('total_confirmed') and r.get('total_ms') is not None]
    detects = [r['detect_ms'] for r in rows if r.get('detect_ms') is not None]
    local = [r['process_ms'] for r in rows if r.get('process_ms') is not None]
    def pack(values):
        if not values:
            return {'n': 0, 'median_ms': None, 'p95_ms': None, 'max_ms': None, 'under_1000_pct': None}
        under = sum(1 for v in values if v < 1000)
        return {
            'n': len(values),
            'median_ms': round(_percentile(values, 0.5), 1),
            'p95_ms': round(_percentile(values, 0.95), 1),
            'max_ms': round(max(values), 1),
            'under_1000_pct': round(100 * under / len(values), 1),
        }
    return {
        'samples': len(rows),
        'detect': pack(detects),
        'process': pack(local),
        'total': pack(totals),
        'total_confirmed': bool(totals),
        'note': (
            'Total delay counts only when the source timestamp is finer than one second '
            'and the clock check is reliable. A one-second API stamp or a local detection '
            'clock does not confirm under 1000 ms.'
        ),
    }


class MitchCopy:
    def __init__(self, store, fetch, clock=None):
        self.store = store
        self.fetch = fetch
        self.clock = clock or time.time
        self._task = None

    def ensure(self):
        with self.store.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS mitch_events (
                    wallet TEXT, event_key TEXT, reason TEXT, body TEXT, at REAL,
                    PRIMARY KEY (wallet, event_key));
                CREATE TABLE IF NOT EXISTS mitch_positions (
                    id TEXT PRIMARY KEY, wallet TEXT, body TEXT);
                CREATE TABLE IF NOT EXISTS mitch_accounts (
                    wallet TEXT PRIMARY KEY, cash INTEGER);
                CREATE TABLE IF NOT EXISTS mitch_ledger (
                    id TEXT PRIMARY KEY, wallet TEXT, amount INTEGER);
                CREATE TABLE IF NOT EXISTS mitch_windows (
                    wallet TEXT, window TEXT, spent INTEGER, PRIMARY KEY (wallet, window));
                CREATE TABLE IF NOT EXISTS mitch_source (
                    wallet TEXT, token TEXT, shares TEXT, known INTEGER,
                    PRIMARY KEY (wallet, token));
                CREATE TABLE IF NOT EXISTS mitch_seen_tx (
                    wallet TEXT, tx TEXT, side TEXT, token TEXT,
                    PRIMARY KEY (wallet, tx, side, token));
            ''')
            for wallet in WALLETS:
                db.execute(
                    'INSERT OR IGNORE INTO mitch_accounts VALUES (?,?)',
                    (wallet, CAPITAL_MICRO),
                )
        if not self.store.get('mitch_copy_start'):
            self.store.set('mitch_copy_start', {'at': self.clock(), 'spec': SPEC})

    def started(self):
        row = self.store.get('mitch_copy_start') or {}
        return float(row.get('at') or self.clock())

    def _seen(self, db, wallet, key):
        return db.execute(
            'SELECT 1 FROM mitch_events WHERE wallet=? AND event_key=?',
            (wallet, key),
        ).fetchone() is not None

    def _mark(self, db, wallet, key, reason, body):
        db.execute(
            'INSERT OR REPLACE INTO mitch_events VALUES (?,?,?,?,?)',
            (wallet, key, reason, json.dumps(body, default=str), self.clock()),
        )

    def _window_spent(self, db, wallet, window):
        row = db.execute(
            'SELECT spent FROM mitch_windows WHERE wallet=? AND window=?',
            (wallet, window),
        ).fetchone()
        return int(row[0]) if row else 0

    def plan_buy(self, event, asks, fee_rate, tick, min_shares, remaining_micro):
        dollars = source_dollars(event)
        paid = source_price(event)
        if dollars is None or paid is None:
            return 'SOURCE_PRICE_UNCONFIRMED', None
        wanted = copy_notional_usd(dollars)
        room = Decimal(remaining_micro) / Decimal(1_000_000)
        budget = min(wanted, room)
        if budget <= Decimal('0.01'):
            return 'WINDOW_LIMIT', None
        if not asks:
            return 'NO_ASK', None
        best = min(Decimal(str(price)) for price, _size in asks)
        if not price_allows(best, paid):
            return 'PRICE_WORSE_THAN_10C', None
        limit = min(Decimal('0.999999'), paid + PRICE_WORSE)
        try:
            fill = simulate_fill(asks, str(budget), str(limit), str(fee_rate), str(min_shares), str(tick))
        except ValueError:
            return 'NO_LIQUIDITY', None
        if not fill:
            return 'NO_LIQUIDITY', None
        if not price_allows(fill['vwap'], paid):
            return 'PRICE_WORSE_THAN_10C', None
        debit = int(fill['cost']) + int(fill['fee'])
        if debit > remaining_micro:
            return 'WINDOW_LIMIT', None
        return None, fill

    def apply_buy(self, db, wallet, key, event, fill, timing):
        slug = str(event.get('slug'))
        debit = int(fill['cost']) + int(fill['fee'])
        limit = int(WALLETS[wallet]['limit_usd'] * 1_000_000)
        spent = self._window_spent(db, wallet, slug)
        if spent + debit > limit:
            self._mark(db, wallet, key, 'WINDOW_LIMIT', {'timing': timing, 'source': event.get('price')})
            return 'WINDOW_LIMIT'
        tx = str(event.get('transactionHash') or '')
        token = str(event.get('asset') or '')
        if tx and db.execute(
            'SELECT 1 FROM mitch_seen_tx WHERE wallet=? AND tx=? AND side=? AND token=?',
            (wallet, tx, 'BUY', token),
        ).fetchone():
            self._mark(db, wallet, key, 'DUPLICATE', {'timing': timing})
            return 'DUPLICATE'
        cash = db.execute('SELECT cash FROM mitch_accounts WHERE wallet=?', (wallet,)).fetchone()[0]
        if cash < debit:
            self._mark(db, wallet, key, 'PAPER_CASH', {'timing': timing})
            return 'PAPER_CASH'
        trade_id = 'mitch:' + wallet[-8:] + ':' + key[:16]
        adding = None
        for (body,) in db.execute('SELECT body FROM mitch_positions WHERE wallet=?', (wallet,)):
            current = json.loads(body)
            if current.get('status') == 'OPEN' and current.get('token') == token:
                adding = current
                break
        now = self.clock()
        if adding:
            adding['shares'] = int(adding['shares']) + int(fill['shares'])
            adding['cost'] = int(adding['cost']) + int(fill['cost'])
            adding['fee'] = int(adding['fee']) + int(fill['fee'])
            adding.setdefault('lots', []).append({'key': key, 'cost': fill['cost'], 'fee': fill['fee'], 'at': now})
            db.execute('UPDATE mitch_positions SET body=? WHERE id=?', (json.dumps(adding), adding['id']))
            reason = 'MITCH_ADD'
        else:
            trade = {
                'id': trade_id, 'wallet': wallet, 'market': slug, 'token': token,
                'side': event.get('outcome') or event.get('side'), 'shares': fill['shares'],
                'cost': fill['cost'], 'fee': fill['fee'], 'opened': now, 'status': 'OPEN',
                'source_price': str(source_price(event)), 'copy_vwap': fill['vwap'],
                'condition': event.get('conditionId'), 'end': self._end(slug),
            }
            db.execute('INSERT INTO mitch_positions VALUES (?,?,?)', (trade_id, wallet, json.dumps(trade)))
            reason = 'MITCH_BUY'
        db.execute('UPDATE mitch_accounts SET cash=cash-? WHERE wallet=?', (debit, wallet))
        db.execute('INSERT INTO mitch_ledger VALUES (?,?,?)', ('buy:' + key, wallet, -debit))
        db.execute(
            'INSERT INTO mitch_windows VALUES (?,?,?) ON CONFLICT(wallet, window) DO UPDATE SET spent=spent+?',
            (wallet, slug, debit, debit),
        )
        if tx:
            db.execute('INSERT OR IGNORE INTO mitch_seen_tx VALUES (?,?,?,?)', (wallet, tx, 'BUY', token))
        self._add_source(db, wallet, token, event.get('size'), buy=True)
        self._mark(db, wallet, key, reason, {
            'timing': timing, 'source_price': str(source_price(event)), 'copy_vwap': fill['vwap'],
            'cost': fill['cost'], 'fee': fill['fee'], 'shares': fill['shares'],
        })
        return reason

    def _add_source(self, db, wallet, token, size, buy):
        row = db.execute(
            'SELECT shares, known FROM mitch_source WHERE wallet=? AND token=?',
            (wallet, token),
        ).fetchone()
        if not row or not row[1]:
            return
        shares = Decimal(row[0] or '0')
        delta = Decimal(str(size or 0))
        shares = shares + delta if buy else shares - delta
        if shares < 0:
            db.execute(
                'UPDATE mitch_source SET known=0, shares=? WHERE wallet=? AND token=?',
                ('', wallet, token),
            )
            return
        db.execute(
            'UPDATE mitch_source SET shares=? WHERE wallet=? AND token=?',
            (format(shares, 'f'), wallet, token),
        )

    def apply_sell(self, db, wallet, key, event, bids, fraction, timing, delayed):
        token = str(event.get('asset') or '')
        open_trade = None
        for (pid, body) in db.execute('SELECT id, body FROM mitch_positions WHERE wallet=?', (wallet,)):
            current = json.loads(body)
            if current.get('status') == 'OPEN' and current.get('token') == token:
                open_trade = current
                break
        if fraction is None:
            self._mark(db, wallet, key, 'SOURCE_PROPORTION_UNKNOWN', {'timing': timing, 'delayed': delayed})
            return 'SOURCE_PROPORTION_UNKNOWN'
        if not open_trade:
            self._add_source(db, wallet, token, event.get('size'), buy=False)
            self._mark(db, wallet, key, 'NO_MITCH_POSITION', {'timing': timing})
            return 'NO_MITCH_POSITION'
        cut = our_sell_shares(open_trade['shares'], fraction)
        fill = self._sell_fill(bids, cut)
        if not cut or not fill:
            self._mark(db, wallet, key, 'NO_LIQUIDITY' if fraction is not None else 'SOURCE_PROPORTION_UNKNOWN', {'timing': timing})
            return 'NO_LIQUIDITY'
        whole = int(open_trade['shares'])
        sold = min(cut, whole)
        alloc_cost = int(open_trade['cost']) * sold // whole
        alloc_fee = int(open_trade['fee']) * sold // whole
        payout = int(fill['proceeds'])
        exit_fee = int(fill['fee'])
        credit = payout - exit_fee
        pnl = credit - alloc_cost - alloc_fee
        if sold >= whole:
            open_trade.update(status='CLOSED', payout=payout, exit_fee=exit_fee, closed_at=self.clock(),
                              pnl_micro=pnl, delayed_sell=delayed)
            db.execute('UPDATE mitch_positions SET body=? WHERE id=?', (json.dumps(open_trade), open_trade['id']))
        else:
            closed = dict(open_trade)
            closed.update(id=open_trade['id'] + ':sell:' + key[:12], status='CLOSED', shares=sold,
                          cost=alloc_cost, fee=alloc_fee, payout=payout, exit_fee=exit_fee,
                          closed_at=self.clock(), pnl_micro=pnl, delayed_sell=delayed)
            open_trade['shares'] = whole - sold
            open_trade['cost'] = int(open_trade['cost']) - alloc_cost
            open_trade['fee'] = int(open_trade['fee']) - alloc_fee
            db.execute('INSERT INTO mitch_positions VALUES (?,?,?)', (closed['id'], wallet, json.dumps(closed)))
            db.execute('UPDATE mitch_positions SET body=? WHERE id=?', (json.dumps(open_trade), open_trade['id']))
        db.execute('UPDATE mitch_accounts SET cash=cash+? WHERE wallet=?', (credit, wallet))
        db.execute('INSERT OR IGNORE INTO mitch_ledger VALUES (?,?,?)', ('sell:' + key, wallet, credit))
        self._add_source(db, wallet, token, event.get('size'), buy=False)
        self._mark(db, wallet, key, 'MITCH_SELL', {
            'timing': timing, 'delayed': delayed, 'fraction': str(fraction),
            'source_price': str(source_price(event) or ''), 'copy_vwap': fill.get('vwap'),
            'pnl_micro': pnl,
        })
        return 'MITCH_SELL'

    @staticmethod
    def _end(slug):
        try:
            return int(str(slug).rsplit('-', 1)[-1]) + 900
        except ValueError:
            return None

    def fraction_for(self, db, wallet, event):
        token = str(event.get('asset') or '')
        row = db.execute(
            'SELECT shares, known FROM mitch_source WHERE wallet=? AND token=?',
            (wallet, token),
        ).fetchone()
        if not row or not row[1] or not row[0]:
            return None
        try:
            sold = Decimal(str(event.get('size')))
        except Exception:
            return None
        return sell_fraction(sold, row[0])

    def note_source_buy(self, db, wallet, event):
        """A skipped buy still changes the source book when that book is known."""
        token = str(event.get('asset') or '')
        self._add_source(db, wallet, token, event.get('size'), buy=True)

    def anchor_source(self, db, wallet, token, shares):
        db.execute(
            'INSERT INTO mitch_source VALUES (?,?,?,1) ON CONFLICT(wallet, token) DO UPDATE SET shares=?, known=1',
            (wallet, token, format(Decimal(str(shares)), 'f'), format(Decimal(str(shares)), 'f')),
        )

    def pending(self, db, now):
        start = self.started()
        marks = ','.join('?' * len(WALLETS))
        return [dict(r) for r in db.execute(
            f'''SELECT a.* FROM wallet_activity a
                LEFT JOIN mitch_events e ON a.wallet=e.wallet AND a.event_key=e.event_key
                WHERE e.event_key IS NULL AND a.wallet IN ({marks}) AND a.first_seen>=?
                ORDER BY a.first_seen ASC LIMIT 10''',
            (*WALLETS, start),
        )]

    def publish(self):
        now = self.clock()
        today = time.strftime('%Y-%m-%d', time.gmtime(now))
        # Stockholm date, not UTC date.
        from datetime import datetime, timezone
        today = datetime.fromtimestamp(now, STOCKHOLM).date().isoformat()
        with self.store.connect() as db:
            positions = [json.loads(body) for (body,) in db.execute('SELECT body FROM mitch_positions')]
            events = [dict(r) for r in db.execute(
                'SELECT wallet, event_key, reason, body, at FROM mitch_events ORDER BY at DESC LIMIT 40'
            )]
            windows = {
                (r[0], r[1]): int(r[2])
                for r in db.execute('SELECT wallet, window, spent FROM mitch_windows')
            }
        closed = [p for p in positions if p.get('status') == 'CLOSED' and p.get('pnl_micro') is not None]
        unknown_closed = [p for p in positions if p.get('status') == 'CLOSED' and p.get('pnl_micro') is None]
        opens = [p for p in positions if p.get('status') == 'OPEN']
        def day_of(ts):
            if not ts:
                return None
            return datetime.fromtimestamp(float(ts), STOCKHOLM).date().isoformat()
        all_net = None if unknown_closed else sum(int(p['pnl_micro']) for p in closed)
        today_rows = [p for p in closed if day_of(p.get('closed_at')) == today]
        today_net = None if unknown_closed else sum(int(p['pnl_micro']) for p in today_rows)
        wallets = []
        for wallet, meta in WALLETS.items():
            mine = [p for p in closed if p.get('wallet') == wallet]
            missing = any(p.get('wallet') == wallet and p.get('pnl_micro') is None for p in positions if p.get('status') == 'CLOSED')
            net = None if missing else sum(int(p['pnl_micro']) for p in mine)
            copies = sum(1 for e in events if e['wallet'] == wallet and e['reason'] in ('MITCH_BUY', 'MITCH_ADD'))
            # counts from the full table, not the 40-row preview
            wallets.append({
                'wallet': wallet, 'label': meta['label'], 'limit_usd': str(meta['limit_usd']),
                'net_micro': net, 'open': sum(1 for p in opens if p.get('wallet') == wallet),
                'open_cost_micro': sum(int(p['cost']) + int(p['fee']) for p in opens if p.get('wallet') == wallet),
                'copies_preview': copies,
            })
        with self.store.connect() as db:
            for row in wallets:
                count = db.execute(
                    "SELECT COUNT(*) FROM mitch_events WHERE wallet=? AND reason IN ('MITCH_BUY','MITCH_ADD')",
                    (row['wallet'],),
                ).fetchone()[0]
                row['copies'] = int(count)
                spent = db.execute(
                    'SELECT COALESCE(SUM(spent),0) FROM mitch_windows WHERE wallet=?',
                    (row['wallet'],),
                ).fetchone()[0]
                row['spent_micro'] = int(spent)
        latency_rows = []
        for event in events:
            body = json.loads(event['body'] or '{}')
            timing = body.get('timing') or {}
            if timing:
                latency_rows.append(timing)
        payload = {
            'spec': SPEC,
            'assumptions': list(ASSUMPTIONS),
            'grouping': GROUPING,
            'capital_usd_per_wallet': CAPITAL_MICRO / 1e6,
            'capital_note': 'Mitch did not set the paper capital. $500 per wallet is a temporary assumption.',
            'updated_at': now,
            'closed_today_micro': today_net,
            'closed_all_micro': all_net,
            'open_count': len(opens),
            'open_cost_micro': sum(int(p['cost']) + int(p['fee']) for p in opens),
            'open_mark_micro': None,
            'open_mark_note': 'No live mark is stored. Open cost is capital in use, not a result.',
            'wallets': wallets,
            'recent': [{
                'at': e['at'], 'wallet': e['wallet'], 'reason': e['reason'],
                'detail': json.loads(e['body'] or '{}'),
            } for e in events],
            'latency': latency_summary(latency_rows),
            'clock': self.store.get('clock_status') or {'status': 'not_checked'},
            'sum_matches': all_net is None or all_net == sum(
                (w['net_micro'] or 0) for w in wallets if w['net_micro'] is not None
            ) and all(w['net_micro'] is not None for w in wallets),
        }
        self.store.set('mitch_copy', payload)
        return payload

    async def run(self):
        self.ensure()
        self.publish()
        last_publish = self.clock()
        while True:
            try:
                await self.step()
                if self.clock() - last_publish >= 2:
                    self.publish()
                    last_publish = self.clock()
            except Exception as error:
                log.warning('mitch step: %s', error)
                self.store.set('mitch_copy_error', {'at': self.clock(), 'error': str(error)[:300]})
            await asyncio.sleep(0.2)

    async def step(self):
        now = self.clock()
        with self.store.connect() as db:
            rows = self.pending(db, now)
        for row in rows:
            await self.handle(row)

    async def handle(self, row):
        wallet = row['wallet']
        key = row['event_key']
        event = json.loads(row['body']) if isinstance(row['body'], str) else row['body']
        received = time.monotonic()
        if wallet not in WALLETS:
            return
        if float(row['first_seen']) < self.started():
            return
        with self.store.connect() as db:
            if self._seen(db, wallet, key):
                return
        if not is_btc_15m(event) or event.get('type') != 'TRADE' or event.get('side') not in ('BUY', 'SELL'):
            with self.store.connect() as db:
                self._mark(db, wallet, key, 'NOT_BTC_15M', {})
            return
        source_basis = 'local_detect' if event.get('_source') == 'chain_fast' else 'source_second'
        clock = self.store.get('clock_status') or {}
        clock_ok = clock.get('status') == 'synced'
        decision_at = self.clock()
        if event.get('_source') == 'chain_fast' and self.clock() - float(row['first_seen']) < 3:
            return
        if event['side'] == 'BUY' and source_basis == 'local_detect':
            with self.store.connect() as db:
                self._mark(db, wallet, key, 'SOURCE_PRICE_UNCONFIRMED', {
                    'timing': self._timing(row, received, decision_at, decision_at, source_basis, clock_ok),
                })
            return
        age = self.clock() - float(row['source_ts'])
        delayed = age > 2
        if event['side'] == 'BUY' and (age > 90 or float(row['first_seen']) < self.started()):
            with self.store.connect() as db:
                self._mark(db, wallet, key, 'LATE_BUY_NOT_COPIED', {})
            return
        exec_started = time.monotonic()
        book = await self._book(str(event.get('asset') or ''))
        exec_done = time.monotonic()
        timing = self._timing(row, received, decision_at, self.clock(), source_basis, clock_ok, exec_started, exec_done)
        asks = [(level.get('price'), level.get('size')) for level in (book or {}).get('asks') or [] if isinstance(level, dict)]
        bids = [(level.get('price'), level.get('size')) for level in (book or {}).get('bids') or [] if isinstance(level, dict)]
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if self._seen(db, wallet, key):
                return
            if event['side'] == 'BUY':
                limit = int(WALLETS[wallet]['limit_usd'] * 1_000_000)
                remaining = limit - self._window_spent(db, wallet, str(event.get('slug')))
                minimum = str((book or {}).get('min_order_size') or '5')
                tick = str((book or {}).get('tick_size') or '0.01')
                why, fill = self.plan_buy(event, asks, '0', tick, minimum, remaining)
                if why:
                    if event.get('size'):
                        self.note_source_buy(db, wallet, event)
                    self._mark(db, wallet, key, why, {'timing': timing, 'source_price': str(source_price(event) or '')})
                    return
                self.apply_buy(db, wallet, key, event, fill, timing)
                return
            fraction = self.fraction_for(db, wallet, event)
            self.apply_sell(db, wallet, key, event, bids, fraction, timing, delayed)

    def _sell_fill(self, bids, shares_micro):
        if not bids or not shares_micro:
            return None
        try:
            price = max(Decimal(str(p)) for p, _s in bids)
        except Exception:
            return None
        if price <= 0:
            return None
        proceeds = int((price * Decimal(int(shares_micro))).to_integral_value(rounding=ROUND_FLOOR))
        return {'proceeds': proceeds, 'fee': 0, 'vwap': float(price)}

    def _timing(self, row, received_mono, decision_at, finished_at, basis, clock_ok, exec_started=None, exec_done=None):
        source_ts = float(row['source_ts'])
        first_seen = float(row['first_seen'])
        detect = None if basis == 'local_detect' else (first_seen - source_ts) * 1000
        process = None
        if exec_started is not None and exec_done is not None:
            process = (exec_done - exec_started) * 1000
        total = None
        confirmed = False
        if basis == 'source_subsecond' and clock_ok and detect is not None and process is not None:
            total = detect + process
            confirmed = True
        return {
            'source_ts': source_ts,
            'source_precision': basis,
            'received_at': first_seen,
            'decision_at': decision_at,
            'exec_finished_at': finished_at,
            'detect_ms': None if detect is None else round(detect, 1),
            'process_ms': None if process is None else round(process, 1),
            'total_ms': None if total is None else round(total, 1),
            'total_confirmed': confirmed,
        }

    async def _book(self, token):
        if not token or self.fetch is None:
            return None
        import urllib.parse
        url = 'https://clob.polymarket.com/book?token_id=' + urllib.parse.quote(token, safe='')
        try:
            return await asyncio.to_thread(self.fetch, url)
        except Exception:
            return None
