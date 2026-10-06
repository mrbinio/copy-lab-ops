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
                CREATE TABLE IF NOT EXISTS mitch_source_events (
                    wallet TEXT, event_key TEXT, token TEXT, source_ts REAL,
                    size TEXT, buy INTEGER,
                    PRIMARY KEY (wallet, event_key));
            ''')
            columns = [row[1] for row in db.execute('PRAGMA table_info(mitch_source)')]
            if 'as_of' not in columns:
                db.execute('ALTER TABLE mitch_source ADD COLUMN as_of REAL')
            columns = [row[1] for row in db.execute('PRAGMA table_info(mitch_source)')]
            if 'baseline' not in columns:
                db.execute('ALTER TABLE mitch_source ADD COLUMN baseline TEXT')
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

    def plan_buy(self, event, asks, fee_rate, tick, min_shares, remaining_micro, fee_verified=True):
        if fee_verified is not True:
            return 'FEE_UNCONFIRMED', None
        try:
            rate = Decimal(str(fee_rate))
        except Exception:
            return 'FEE_UNCONFIRMED', None
        if not rate.is_finite() or rate < 0 or rate > 1:
            return 'FEE_UNCONFIRMED', None
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
            fill = simulate_fill(asks, str(budget), str(limit), str(rate), str(min_shares), str(tick))
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

    def _held(self, db, wallet):
        row = db.execute("SELECT body FROM state WHERE key='mitch_buy_hold'").fetchone()
        if not row:
            return False
        try:
            held = json.loads(row[0]).get('wallets') or {}
        except (TypeError, ValueError):
            return False
        return wallet in held

    def apply_buy(self, db, wallet, key, event, fill, timing):
        if self._held(db, wallet):
            self._mark(db, wallet, key, 'MITCH_LEDGER_HOLD', self._case(None, event, {'timing': timing}))
            return 'MITCH_LEDGER_HOLD'
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
        self._record_source(db, wallet, token, key, event, buy=True)
        self._mark(db, wallet, key, reason, self._case(None, event, {
            'timing': timing, 'source_price': str(source_price(event)), 'copy_vwap': fill['vwap'],
            'cost': fill['cost'], 'fee': fill['fee'], 'shares': fill['shares'],
            'source_ts': event.get('timestamp'),
        }))
        return reason

    def _record_source(self, db, wallet, token, key, event, buy):
        """Remember the source trade once, then rebuild the book from the anchor."""
        size = event.get('size') if isinstance(event, dict) else event
        source_ts = None
        if isinstance(event, dict):
            try:
                source_ts = float(event.get('timestamp') or 0) or None
            except (TypeError, ValueError):
                source_ts = None
        db.execute(
            'INSERT OR IGNORE INTO mitch_source_events VALUES (?,?,?,?,?,?)',
            (wallet, key, token, source_ts, str(size or ''), 1 if buy else 0),
        )
        self._recompute_source(db, wallet, token)

    def _add_source(self, db, wallet, token, size, buy):
        self._record_source(db, wallet, token, 'legacy:' + token + ':' + str(size) + ':' + str(buy), {'size': size, 'timestamp': 0}, buy)

    def _recompute_source(self, db, wallet, token):
        row = db.execute(
            'SELECT baseline, known, as_of FROM mitch_source WHERE wallet=? AND token=?',
            (wallet, token),
        ).fetchone()
        if not row or not row[1] or row[0] in (None, ''):
            return
        total = Decimal(row[0])
        as_of = float(row[2] or 0)
        for source_ts, size, is_buy in db.execute(
            'SELECT source_ts, size, buy FROM mitch_source_events WHERE wallet=? AND token=? ORDER BY source_ts, event_key',
            (wallet, token),
        ):
            if source_ts is not None and float(source_ts) <= as_of:
                continue
            delta = Decimal(str(size or '0'))
            if delta <= 0:
                continue
            total = total + delta if is_buy else total - delta
        if total < 0:
            db.execute(
                'UPDATE mitch_source SET known=0, shares=? WHERE wallet=? AND token=?',
                ('', wallet, token),
            )
            return
        db.execute(
            'UPDATE mitch_source SET shares=? WHERE wallet=? AND token=?',
            (format(total, 'f'), wallet, token),
        )

    def _case(self, row, event, extra=None):
        body = {
            'transactionHash': (event or {}).get('transactionHash'),
            'token': (event or {}).get('asset'),
            'market': (event or {}).get('slug'),
            'source_ts': None if not row else row.get('source_ts'),
            'side': (event or {}).get('side'),
        }
        if extra:
            body.update(extra)
        return body

    def apply_sell(self, db, wallet, key, event, bids, fraction, timing, delayed, fee_rate='0', fee_verified=True):
        token = str(event.get('asset') or '')
        self._record_source(db, wallet, token, key, event, buy=False)
        open_trade = None
        for (pid, body) in db.execute('SELECT id, body FROM mitch_positions WHERE wallet=?', (wallet,)):
            current = json.loads(body)
            if current.get('status') == 'OPEN' and current.get('token') == token:
                open_trade = current
                break
        if fraction is None:
            self._mark(db, wallet, key, 'SOURCE_PROPORTION_UNKNOWN', self._case(None, event, {'timing': timing, 'delayed': delayed}))
            return 'SOURCE_PROPORTION_UNKNOWN'
        if not open_trade:
            self._mark(db, wallet, key, 'NO_MITCH_POSITION', self._case(None, event, {'timing': timing}))
            return 'NO_MITCH_POSITION'
        cut = our_sell_shares(open_trade['shares'], fraction)
        fill = self._sell_fill(bids, cut, fee_rate, fee_verified)
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

    def anchor_source(self, db, wallet, token, shares, as_of=0):
        baseline = format(Decimal(str(shares)), 'f')
        db.execute(
            '''INSERT INTO mitch_source (wallet, token, shares, known, as_of, baseline)
               VALUES (?,?,?,1,?,?)
               ON CONFLICT(wallet, token) DO UPDATE SET
                 shares=excluded.shares, known=1, as_of=excluded.as_of, baseline=excluded.baseline''',
            (wallet, token, baseline, float(as_of or 0), baseline),
        )
        self._recompute_source(db, wallet, token)

    def pending(self, db, now):
        start = self.started()
        marks = ','.join('?' * len(WALLETS))
        return [dict(r) for r in db.execute(
            f'''SELECT a.* FROM wallet_activity a INDEXED BY wallet_activity_seen
                WHERE a.first_seen>=? AND a.wallet IN ({marks})
                AND NOT EXISTS (
                    SELECT 1 FROM mitch_events e
                    WHERE e.wallet=a.wallet AND e.event_key=a.event_key
                      AND e.reason != 'AWAITING_SOURCE_PRICE')
                ORDER BY a.first_seen ASC LIMIT 10''',
            (start, *WALLETS),
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
        closed = [p for p in positions if p.get('status') in ('CLOSED', 'SETTLED') and p.get('pnl_micro') is not None]
        unknown_closed = [p for p in positions if p.get('status') in ('CLOSED', 'SETTLED') and p.get('pnl_micro') is None]
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
            missing = any(p.get('wallet') == wallet and p.get('pnl_micro') is None for p in positions if p.get('status') in ('CLOSED', 'SETTLED'))
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
            'open_positions': [{
                'wallet': p.get('wallet'), 'token': p.get('token'), 'slug': p.get('slug'),
                'shares': p.get('shares'), 'cost': p.get('cost'), 'fee': p.get('fee'),
                'end': p.get('end'), 'status': p.get('status'),
            } for p in opens],
        }
        with self.store.connect() as db:
            breaks = self._ledger_breaks(db)
            held = {item['wallet']: item for item in breaks}
            db.execute(
                "INSERT INTO state VALUES ('mitch_buy_hold', ?) ON CONFLICT(key) DO UPDATE SET body=excluded.body",
                (json.dumps({'wallets': held, 'at': now}),),
            )
            reasons = {
                reason: int(count) for reason, count in db.execute(
                    'SELECT reason, COUNT(*) FROM mitch_events GROUP BY reason'
                )
            }
            awaiting = int(reasons.get('AWAITING_SOURCE_PRICE') or 0)
        payload['health'] = 'mismatch' if breaks else 'ok'
        payload['breaks'] = breaks
        payload['reasons'] = reasons
        payload['awaiting_price'] = awaiting
        for row in wallets:
            row['buy_hold'] = row['wallet'] in held
        self.store.set('mitch_copy', payload)
        return payload

    async def ensure_anchors(self):
        """One confirmed data-api size per token. Later source trades move that baseline."""
        if self.fetch is None:
            return
        for wallet in WALLETS:
            try:
                raw = await asyncio.to_thread(
                    self.fetch, 'https://data-api.polymarket.com/positions?user=' + wallet,
                )
            except Exception:
                continue
            if isinstance(raw, list):
                await asyncio.to_thread(self._apply_anchor, wallet, raw)

    def _apply_anchor(self, wallet, rows):
        now = self.clock()
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            for row in rows:
                if not isinstance(row, dict):
                    continue
                token = str(row.get('asset') or row.get('token') or '')
                size = row.get('size')
                if not token or size is None:
                    continue
                existing = db.execute(
                    'SELECT known, baseline FROM mitch_source WHERE wallet=? AND token=?',
                    (wallet, token),
                ).fetchone()
                if existing and existing[0] and existing[1] not in (None, ''):
                    continue
                self.anchor_source(db, wallet, token, size, as_of=now)

    async def run(self):
        self.ensure()
        await self.ensure_anchors()
        self.publish()
        last_publish = self.clock()
        while True:
            try:
                await self.step()
                if self.clock() - last_publish >= 2:
                    await asyncio.to_thread(self.publish)
                    last_publish = self.clock()
            except Exception as error:
                log.warning('mitch step: %s', error)
                try:
                    await asyncio.to_thread(
                        self.store.set, 'mitch_copy_error',
                        {'at': self.clock(), 'error': str(error)[:300]},
                    )
                except Exception:
                    pass
            await asyncio.sleep(0.2)

    def _load_pending(self):
        with self.store.connect() as db:
            return self.pending(db, self.clock())

    async def step(self):
        rows = await asyncio.to_thread(self._load_pending)
        grouped = {}
        for row in rows:
            grouped.setdefault(row['wallet'], []).append(row)
        async def drain(wallet_rows):
            for row in wallet_rows:
                await self.handle(row)
        await asyncio.gather(*(drain(wallet_rows) for wallet_rows in grouped.values()))
        try:
            await self.settle_open()
        except Exception as error:
            log.warning('mitch settle: %s', error)
        await asyncio.to_thread(self._progress, len(rows))
        return len(rows)

    def _progress(self, queue):
        self.store.set('mitch_progress', {
            'at': self.clock(), 'queue': queue, 'status': 'running',
        })

    async def handle(self, row):
        wallet = row['wallet']
        key = row['event_key']
        event = json.loads(row['body']) if isinstance(row['body'], str) else row['body']
        queued = time.monotonic()
        if wallet not in WALLETS:
            return
        if float(row.get('source_ts') or 0) < self.started() and event.get('_source') != 'chain_fast':
            with self.store.connect() as db:
                if not self._seen(db, wallet, key):
                    self._mark(db, wallet, key, 'HISTORICAL_BEFORE_START', self._case(row, event))
            return
        source = event.get('_source')
        if source == 'chain_fast' and self.clock() - float(row['first_seen']) < 3:
            return
        if source == 'chain_fast':
            with self.store.connect() as db:
                self._mark(db, wallet, key, 'AWAITING_SOURCE_PRICE', self._case(row, event, {
                    'timing': self._timing(row, queued, self.clock(), self.clock(), 'local_detect', False),
                }))
            return
        if not is_btc_15m(event) or event.get('type') != 'TRADE' or event.get('side') not in ('BUY', 'SELL'):
            with self.store.connect() as db:
                self._mark(db, wallet, key, 'NOT_BTC_15M', self._case(row, event))
            return
        basis = 'source_subsecond' if source == 'market_trade' else 'source_second'
        clock = self.store.get('clock_status') or {}
        clock_ok = clock.get('status') == 'synced'
        age = self.clock() - float(row['source_ts'])
        if event['side'] == 'BUY' and age > 90:
            with self.store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                self._record_source(db, wallet, str(event.get('asset') or ''), key, event, buy=True)
                self._mark(db, wallet, key, 'LATE_BUY_NOT_COPIED', self._case(row, event, {
                    'class': 'historical' if float(row['source_ts']) < self.started() else 'queue',
                }))
            return
        if event['side'] == 'SELL' and age > 90:
            with self.store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                self._record_source(db, wallet, str(event.get('asset') or ''), key, event, buy=False)
                self._mark(db, wallet, key, 'LATE_SELL_RECONCILED', self._case(row, event))
            return
        book_started = time.monotonic()
        checked = await self._book(str(event.get('asset') or ''))
        terms = await self._terms(event)
        book_done = time.monotonic()
        timing = self._timing(row, queued, self.clock(), self.clock(), basis, clock_ok, book_started, book_done, clock)
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if self._seen(db, wallet, key):
                fresh = db.execute(
                    'SELECT reason FROM mitch_events WHERE wallet=? AND event_key=?',
                    (wallet, key),
                ).fetchone()
                if not fresh or fresh[0] != 'AWAITING_SOURCE_PRICE':
                    return
            current = db.execute(
                'SELECT body, source_ts FROM wallet_activity WHERE wallet=? AND event_key=?',
                (wallet, key),
            ).fetchone()
            if current:
                event = json.loads(current[0])
                row = dict(row, body=current[0], source_ts=current[1])
            if event.get('_source') == 'chain_fast' or source_price(event) is None and event['side'] == 'BUY':
                self._mark(db, wallet, key, 'AWAITING_SOURCE_PRICE', self._case(row, event, {'timing': timing}))
                return
            if float(row['source_ts']) < self.started():
                self._mark(db, wallet, key, 'HISTORICAL_BEFORE_START', self._case(row, event, {'timing': timing}))
                return
            if event['side'] == 'BUY' and self.clock() - float(row['source_ts']) > 90:
                self._record_source(db, wallet, str(event.get('asset') or ''), key, event, buy=True)
                self._mark(db, wallet, key, 'LATE_BUY_NOT_COPIED', self._case(row, event, {'timing': timing}))
                return
            if book_done - book_started > 3:
                self._mark(db, wallet, key, 'BOOK_WAIT_TOO_LONG', self._case(row, event, {'timing': timing}))
                return
            if not checked or checked.get('error'):
                self._mark(db, wallet, key, checked.get('error') if checked else 'NO_BOOK', self._case(row, event, {'timing': timing}))
                return
            if not terms or not terms.get('fee_verified'):
                self._record_source(db, wallet, str(event.get('asset') or ''), key, event, buy=(event['side'] == 'BUY'))
                self._mark(db, wallet, key, 'FEE_UNCONFIRMED', self._case(row, event, {'timing': timing}))
                return
            if event['side'] == 'BUY' and not terms.get('accepting'):
                self._record_source(db, wallet, str(event.get('asset') or ''), key, event, buy=True)
                self._mark(db, wallet, key, 'MARKET_CLOSED', self._case(row, event, {'timing': timing}))
                return
            if event['side'] == 'BUY':
                limit = int(WALLETS[wallet]['limit_usd'] * 1_000_000)
                remaining = limit - self._window_spent(db, wallet, str(event.get('slug')))
                why, fill = self.plan_buy(
                    event, checked['asks'], terms['fee_rate'], checked['tick'], checked['min_shares'],
                    remaining, fee_verified=True,
                )
                if why:
                    self._record_source(db, wallet, str(event.get('asset') or ''), key, event, buy=True)
                    self._mark(db, wallet, key, why, self._case(row, event, {
                        'timing': timing, 'source_price': str(source_price(event) or ''),
                    }))
                    return
                self.apply_buy(db, wallet, key, event, fill, timing)
                return
            fraction = self.fraction_for(db, wallet, event)
            self.apply_sell(
                db, wallet, key, event, checked, fraction, timing, age > 2,
                fee_rate=terms['fee_rate'], fee_verified=True,
            )

    def _sell_fill(self, bids, shares_micro, fee_rate='0', fee_verified=True):
        if fee_verified is not True or not shares_micro:
            return None
        if isinstance(bids, dict) and 'bids' in bids:
            book = bids
        else:
            book = {'bids': list(bids or []), 'tick': '0.01', 'min_shares': '0.000001'}
        from .mid_window import simulate_sale
        try:
            fill = simulate_sale(book, shares_micro, fee_rate)
        except ValueError:
            return None
        if not fill:
            return None
        fill['vwap'] = float(Decimal(fill['proceeds']) / Decimal(int(shares_micro))) if int(shares_micro) else None
        return fill

    def _timing(self, row, received_mono, decision_at, finished_at, basis, clock_ok, exec_started=None, exec_done=None, clock=None):
        source_ts = float(row['source_ts'])
        first_seen = float(row['first_seen'])
        detect = None if basis == 'local_detect' else (first_seen - source_ts) * 1000
        book_ms = None
        if exec_started is not None and exec_done is not None:
            book_ms = (exec_done - exec_started) * 1000
        queue_ms = (decision_at - first_seen) * 1000
        total = None
        confirmed = False
        # One wall-clock span. Stage medians are not added together.
        if basis == 'source_subsecond' and clock_ok:
            total = (finished_at - source_ts) * 1000
            confirmed = True
        clock = clock or {}
        return {
            'source_ts': source_ts,
            'source_precision': basis,
            'source_limit': 'one_second_api' if basis == 'source_second' else basis,
            'received_at': first_seen,
            'decision_at': decision_at,
            'exec_finished_at': finished_at,
            'queue_ms': round(queue_ms, 1),
            'detect_ms': None if detect is None else round(detect, 1),
            'book_ms': None if book_ms is None else round(book_ms, 1),
            'process_ms': None if book_ms is None else round(book_ms, 1),
            'total_ms': None if total is None else round(total, 1),
            'total_confirmed': confirmed,
            'clock_status': clock.get('status'),
            'clock_offset_ms': clock.get('offset_ms'),
            'clock_uncertainty_ms': clock.get('uncertainty_ms'),
            'mono_book_start': exec_started,
            'mono_book_done': exec_done,
        }

    async def _book(self, token):
        if not token or self.fetch is None:
            return {'error': 'NO_BOOK'}
        import urllib.parse
        url = 'https://clob.polymarket.com/book?token_id=' + urllib.parse.quote(token, safe='')
        try:
            raw = await asyncio.to_thread(self.fetch, url)
        except Exception:
            return {'error': 'NO_BOOK'}
        from .worker import normalize_book
        try:
            return normalize_book(raw, token, self.clock(), max_age=3)
        except ValueError as error:
            text = str(error)
            if 'token' in text:
                return {'error': 'BOOK_TOKEN_MISMATCH'}
            return {'error': 'BOOK_STALE'}

    async def _terms(self, event):
        slug = str((event or {}).get('slug') or '')
        if self.fetch is None or not slug.startswith('btc-updown-15m-'):
            return None
        try:
            raw = await asyncio.to_thread(
                self.fetch, 'https://gamma-api.polymarket.com/markets/slug/' + slug,
            )
        except Exception:
            return None
        if not isinstance(raw, dict):
            return None
        from .worker import normalize_market
        try:
            market = normalize_market(raw, int(slug.rsplit('-', 1)[-1]), 'BTC')
        except (ValueError, KeyError, TypeError):
            return None
        if str(event.get('asset') or '') not in set(map(str, market['tokens'].values())):
            return {'fee_verified': False, 'error': 'TOKEN_MISMATCH'}
        return market

    def _due_open(self):
        now = self.clock()
        found = []
        with self.store.connect() as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name='mitch_positions'").fetchone():
                return found
            for body in db.execute('SELECT body FROM mitch_positions'):
                trade = json.loads(body[0])
                end = trade.get('end')
                if trade.get('status') == 'OPEN' and end and now >= float(end) and trade.get('condition'):
                    found.append(trade)
        return found

    async def settle_open(self):
        if self.fetch is None:
            return
        for trade in await asyncio.to_thread(self._due_open):
            try:
                raw = await asyncio.to_thread(
                    self.fetch, 'https://clob.polymarket.com/markets/' + str(trade['condition']),
                )
            except Exception:
                continue
            await asyncio.to_thread(self._settle_one, trade['id'], raw)

    def _settle_one(self, trade_id, raw):
        if not isinstance(raw, dict) or raw.get('closed') is not True:
            return
        winners = [token for token in raw.get('tokens') or [] if token.get('winner') is True]
        if len(winners) != 1:
            return
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT body FROM mitch_positions WHERE id=?', (trade_id,)).fetchone()
            if not row:
                return
            current = json.loads(row[0])
            if current.get('status') != 'OPEN':
                return
            if raw.get('condition_id') != current.get('condition'):
                return
            known = {str(token.get('token_id')) for token in raw.get('tokens') or []}
            if str(current.get('token')) not in known:
                return
            won = str(winners[0].get('token_id')) == str(current.get('token'))
            shares = int(current['shares'])
            payout = shares if won else 0
            ledger_id = 'settle:' + current['id']
            inserted = db.execute(
                'INSERT OR IGNORE INTO mitch_ledger VALUES (?,?,?)',
                (ledger_id, current['wallet'], payout),
            ).rowcount
            if not inserted:
                return
            db.execute(
                'UPDATE mitch_accounts SET cash=cash+? WHERE wallet=?',
                (payout, current['wallet']),
            )
            pnl = payout - int(current['cost']) - int(current['fee'])
            current.update(
                status='SETTLED', payout=payout, exit_fee=0, closed_at=self.clock(),
                pnl_micro=pnl, official_winner=str(winners[0].get('token_id')),
                official_seen_at=self.clock(),
            )
            db.execute('UPDATE mitch_positions SET body=? WHERE id=?', (json.dumps(current), current['id']))

    def _ledger_breaks(self, db):
        breaks = []
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='mitch_accounts'").fetchone():
            return breaks
        for wallet in WALLETS:
            cash_row = db.execute('SELECT cash FROM mitch_accounts WHERE wallet=?', (wallet,)).fetchone()
            if not cash_row:
                continue
            cash = int(cash_row[0])
            ledger = int(db.execute(
                'SELECT COALESCE(SUM(amount),0) FROM mitch_ledger WHERE wallet=?', (wallet,),
            ).fetchone()[0])
            bodies = [
                json.loads(body) for (body,) in db.execute(
                    'SELECT body FROM mitch_positions WHERE wallet=?', (wallet,),
                )
            ]
            exposure = sum(int(t['cost']) + int(t['fee']) for t in bodies if t.get('status') == 'OPEN')
            closed = [t for t in bodies if t.get('status') in ('CLOSED', 'SETTLED') and t.get('pnl_micro') is not None]
            pnl = sum(int(t['pnl_micro']) for t in closed)
            cash_delta = cash - (CAPITAL_MICRO + ledger)
            book_delta = cash + exposure - (CAPITAL_MICRO + pnl)
            if cash < 0 or cash_delta != 0 or book_delta != 0:
                breaks.append({
                    'wallet': wallet, 'cash': cash, 'ledger': ledger,
                    'exposure': exposure, 'pnl': pnl,
                    'cash_minus_capital_ledger': cash_delta,
                    'book_minus_capital_pnl': book_delta,
                })
        return breaks
