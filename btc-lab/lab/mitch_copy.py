"""PAPER copy of five Bitcoin 15-minute wallets. Separate from the qualifier book.

mitch-copy-wallets-v1 follows the sizing, window caps and one-sided 10 cent
rule Mitch wrote down. A late public-list copy is not his trade: new buys
need a chain fill or a matched print, and they must land inside one second.
A negative closed book pauses further buys. It never writes the qualifier
ledger and it never turns LIVE on.
"""
import asyncio
import json
import logging
import time
from datetime import datetime
from decimal import Decimal, ROUND_FLOOR
from zoneinfo import ZoneInfo

from .core import simulate_fill
from .profit_bank import (
    RESERVE_PCT, ensure_reserved_column, lock_profit, rebuild_high_water, reserved_of, tradable_cash,
)

log = logging.getLogger('lab.mitch')
SPEC = 'mitch-copy-wallets-v1'
MIHA_5M_VERDICT = (
    'Mitch, 7 Oct 2026: do not copy mihaXd on 5m at any size. '
    'Copying him 30d at 2c over his price lost. His 15m book stays as it is.'
)
STOCKHOLM = ZoneInfo('Europe/Stockholm')
PRICE_WORSE = Decimal('0.10')
MAX_BUY_AGE = 1.0
# clob_match: the exchange transaction read from the mempool right after the
# market channel printed the match. Its time is the match time in ms.
CHAIN_SOURCES = ('clob_match', 'order_filled', 'market_trade')
# v2: Damian, 9 Oct 2026 ~19:00, after a lifetime pause was put back on the
# release by another agent. The new period starts again from this deploy.
STINT = {
    'id': 'fast-match-v2',
    'note': 'Copies from the match print and the pending exchange transaction. '
            'The book since start keeps the losses of the late public-list path. '
            'Damian chose a new test period on 9 Oct 2026.',
}
PAUSE_REASON = 'mitch-copy-wallets-v1 pause: closed copy period is negative'
# Mitch did not name a paper bankroll. This only keeps the window caps
# from being confused with an empty account. It is not his rule.
CAPITAL_MICRO = 500_000_000
ASSUMPTIONS = (
    'A sell does not restore the buy budget already used in that window. Needs Mitch to confirm.',
    'The $20 and $5 caps include the buy cost and the entry fee. Exit fees are only in the net result. Needs Mitch to confirm.',
    'A partial sell uses source shares sold divided by source shares just before that sell. Needs Mitch to confirm.',
    'Paper capital is $500 per wallet because Mitch did not set it. The window caps are the binding limit.',
    'A new buy needs his fill from the exchange transaction or the chain, and it must land inside one second of the match. A late public-list copy is not his trade.',
    'A negative closed book, today or in the current test period, pauses further buys. There is no automatic retest. The book since start is kept and shown.',
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


ACTIVE = None


async def submit_fast(wallet, body, detected_at):
    """Sink for the fast lane. The running copier, also after a task restart."""
    if ACTIVE is not None:
        await ACTIVE.submit_fast(wallet, body, detected_at)


def fast_status():
    from . import fast_match
    current = getattr(fast_match, 'CURRENT', None)
    return current.status() if current is not None else None


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


def is_updown_5m(event):
    slug = str((event or {}).get('slug') or '')
    return '-updown-5m-' in slug


def describe_book(checked):
    """What the CLOB showed. Missing bids are not a hidden fill."""
    if not checked or checked.get('error'):
        return {
            'has_bid': False, 'has_ask': False,
            'error': (checked or {}).get('error') or 'NO_BOOK',
        }
    asks = list(checked.get('asks') or [])
    bids = list(checked.get('bids') or [])
    def best(levels, want_min):
        prices = []
        for price, _size in levels:
            try:
                prices.append(Decimal(str(price)))
            except Exception:
                continue
        if not prices:
            return None
        return format(min(prices) if want_min else max(prices), 'f')
    def depth(levels):
        total = Decimal('0')
        for _price, size in levels:
            try:
                total += Decimal(str(size))
            except Exception:
                continue
        return format(total, 'f')
    return {
        'has_ask': bool(asks),
        'has_bid': bool(bids),
        'best_ask': best(asks, True),
        'best_bid': best(bids, False),
        'ask_depth': depth(asks) if asks else '0',
        'bid_depth': depth(bids) if bids else '0',
        'error': None,
        'at': checked.get('received_at') or checked.get('source_ts'),
    }


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
    """Rows are stored timing objects from executed copies. Missing fields stay missing."""
    totals = [r['total_ms'] for r in rows if r.get('total_confirmed') and r.get('total_ms') is not None]
    detects = [r['detect_ms'] for r in rows if r.get('detect_ms') is not None]
    queues = [r['queue_ms'] for r in rows if r.get('queue_ms') is not None]
    books = [r['book_ms'] for r in rows if r.get('book_ms') is not None]
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
        'queue': pack(queues),
        'book': pack(books),
        'process': pack(local),
        'total': pack(totals),
        'total_confirmed': bool(totals),
        'note': (
            'Samples are executed copies that stored a timing block. '
            'A newer rejection without a measurement does not erase them. '
            'Total delay counts only when the source timestamp is finer than one second '
            'and the clock check is reliable. A one-second API stamp does not confirm under 1000 ms. '
            'Missing stage times stay missing.'
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
            ensure_reserved_column(db, 'mitch_accounts')
            rebuild_high_water(db, 'mitch_accounts', 'mitch_positions')
            self.refresh_pauses(db)
            for wallet in WALLETS:
                db.execute(
                    'INSERT OR IGNORE INTO mitch_accounts(wallet, cash) VALUES (?,?)',
                    (wallet, CAPITAL_MICRO),
                )
        if not self.store.get('mitch_copy_start'):
            self.store.set('mitch_copy_start', {'at': self.clock(), 'spec': SPEC})
        current = self.store.get('mitch_stint') or {}
        if current.get('id') != STINT['id']:
            self.store.set('mitch_stint', dict(STINT, at=self.clock()))
            with self.store.connect() as db:
                self.refresh_pauses(db)

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

    def _pause_state(self, db):
        row = db.execute("SELECT body FROM state WHERE key='mitch_pauses'").fetchone()
        if not row:
            return {'wallets': {}}
        try:
            return json.loads(row[0]) or {'wallets': {}}
        except (TypeError, ValueError):
            return {'wallets': {}}

    def _is_paused(self, db, wallet):
        return bool(((self._pause_state(db).get('wallets') or {}).get(wallet) or {}).get('paused'))

    def stint(self, db=None):
        """Start of the current test period, or None before the first one.

        The book since start stays as it is. A pause looks only at copies
        opened inside the period, so losses of an earlier copy path do not
        block a test of the new one. Inside the period a minus still pauses
        and nothing unpauses it.
        """
        if db is not None:
            row = db.execute("SELECT body FROM state WHERE key='mitch_stint'").fetchone()
            body = json.loads(row[0]) if row else None
        else:
            body = self.store.get('mitch_stint')
        if not isinstance(body, dict) or not body.get('at'):
            return None
        return body

    def refresh_pauses(self, db):
        """Stop new buys when the closed book, today or in this period, is negative."""
        now = self.clock()
        today = datetime.fromtimestamp(now, STOCKHOLM).date().isoformat()
        previous = (self._pause_state(db).get('wallets') or {})
        stint = self.stint(db)
        stint_at = float(stint['at']) if stint else None
        stint_id = stint.get('id') if stint else None
        wallets = {}
        for wallet in WALLETS:
            all_net = 0
            period_net = 0
            today_net = 0
            known = True
            for (body,) in db.execute('SELECT body FROM mitch_positions WHERE wallet=?', (wallet,)):
                trade = json.loads(body)
                if trade.get('status') not in ('CLOSED', 'SETTLED'):
                    continue
                inside = stint_at is None or float(trade.get('opened') or 0) >= stint_at
                if trade.get('pnl_micro') is None:
                    if inside:
                        known = False
                    continue
                pnl = int(trade['pnl_micro'])
                all_net += pnl
                if not inside:
                    continue
                period_net += pnl
                closed = trade.get('closed_at')
                if closed and datetime.fromtimestamp(float(closed), STOCKHOLM).date().isoformat() == today:
                    today_net += pnl
            should = known and (period_net < 0 or today_net < 0)
            old = previous.get(wallet) or {}
            if old.get('stint') != stint_id:
                old = {}
            # A pause carries the result that caused it. A held pause without a
            # negative trigger in this period was not made by this rule (on
            # 9 Oct a lifetime pause was written into the period from outside)
            # and does not hold.
            trigger = old.get('trigger') or {}
            justified = (trigger.get('period_net_usd') or 0) < 0 or (trigger.get('today_net_usd') or 0) < 0
            if old and not justified:
                old = {}
            if should:
                wallets[wallet] = {
                    'paused': True,
                    'since': old.get('since') or now,
                    'today_net_usd': today_net / 1e6,
                    'period_net_usd': period_net / 1e6,
                    'all_net_usd': all_net / 1e6,
                    'stint': stint_id,
                    'reason': PAUSE_REASON,
                    'trigger': old.get('trigger') or {
                        'at': now, 'period_net_usd': period_net / 1e6, 'today_net_usd': today_net / 1e6,
                    },
                }
            elif old.get('paused'):
                hold = dict(old)
                hold['paused'] = True
                hold['today_net_usd'] = today_net / 1e6
                hold['period_net_usd'] = period_net / 1e6
                hold['all_net_usd'] = all_net / 1e6
                wallets[wallet] = hold
        payload = {'updated_at': now, 'stint': stint, 'wallets': wallets}
        db.execute(
            "INSERT INTO state VALUES ('mitch_pauses', ?) ON CONFLICT(key) DO UPDATE SET body=excluded.body",
            (json.dumps(payload),),
        )
        return payload

    def stopped(self):
        """The same PAUSE file that stops the other copiers. Sells and settlement go on."""
        from pathlib import Path
        return (Path(self.store.path).parent / 'PAUSE').exists()

    def apply_buy(self, db, wallet, key, event, fill, timing):
        if self.stopped():
            self._mark(db, wallet, key, 'GLOBAL_STOP', self._case(None, event, {'timing': timing}))
            return 'GLOBAL_STOP'
        if self._is_paused(db, wallet):
            self._mark(db, wallet, key, 'MITCH_PAUSED', self._case(None, event, {
                'timing': timing, 'reason': PAUSE_REASON,
            }))
            return 'MITCH_PAUSED'
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
        reserved = reserved_of(db, 'mitch_accounts', wallet)
        if tradable_cash(cash, reserved) < debit:
            self._mark(db, wallet, key, 'PROFIT_RESERVED' if reserved else 'PAPER_CASH', {
                'timing': timing, 'cash': cash, 'reserved': reserved,
            })
            return 'PROFIT_RESERVED' if reserved else 'PAPER_CASH'
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
        source_ts = None if not row else row.get('source_ts')
        if source_ts is None and isinstance(event, dict) and event.get('_source') != 'chain_fast':
            try:
                stamp = float(event.get('timestamp') or 0)
            except (TypeError, ValueError):
                stamp = 0
            source_ts = stamp or None
        body = {
            'transactionHash': (event or {}).get('transactionHash'),
            'token': (event or {}).get('asset'),
            'market': (event or {}).get('slug'),
            'source_ts': source_ts,
            'side': (event or {}).get('side'),
        }
        if extra:
            body.update(extra)
        return body

    def apply_sell(self, db, wallet, key, event, bids, fraction, timing, delayed, fee_rate='0', fee_verified=True, reason='MITCH_SELL'):
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
        lock_profit(db, 'mitch_accounts', wallet, pnl)
        self.refresh_pauses(db)
        self._mark(db, wallet, key, reason, {
            'timing': timing, 'delayed': delayed, 'fraction': str(fraction),
            'source_price': str(source_price(event) or ''), 'copy_vwap': fill.get('vwap'),
            'pnl_micro': pnl,
            'price_basis': 'current_book' if reason == 'LATE_SELL_RECOVERED' else 'copy_book',
        })
        return reason

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

    def _unseen_sql(self, marks):
        return f'''SELECT a.* FROM wallet_activity a INDEXED BY wallet_activity_seen
                WHERE a.first_seen>=? AND a.wallet IN ({marks})
                AND NOT EXISTS (
                    SELECT 1 FROM mitch_events e
                    WHERE e.wallet=a.wallet AND e.event_key=a.event_key
                      AND e.reason != 'AWAITING_SOURCE_PRICE')'''

    def pending(self, db, now):
        """Fresh copyable trades first. History drains behind them, not in front.

        LIMIT here is one batch. backlog() is the length of the queue.
        """
        if not db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='wallet_activity'"
        ).fetchone():
            return []
        if not db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='index' AND name='wallet_activity_seen'"
        ).fetchone():
            db.execute('CREATE INDEX IF NOT EXISTS wallet_activity_seen ON wallet_activity(first_seen)')
        start = self.started()
        marks = ','.join('?' * len(WALLETS))
        base = self._unseen_sql(marks)
        fresh_cut = now - 90
        fresh = [dict(r) for r in db.execute(
            base + ' AND a.source_ts>=? ORDER BY a.source_ts ASC, a.first_seen ASC LIMIT 8',
            (start, *WALLETS, fresh_cut),
        )]
        history_limit = 2 if fresh else 12
        history = [dict(r) for r in db.execute(
            base + ' AND (a.source_ts IS NULL OR a.source_ts<?) ORDER BY a.first_seen ASC LIMIT ?',
            (start, *WALLETS, fresh_cut, history_limit),
        )]
        return fresh + history

    def backlog(self, db, now):
        """Real pending count and age. Not the batch limit."""
        if not db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='wallet_activity'"
        ).fetchone():
            return {'backlog': 0}
        start = self.started()
        marks = ','.join('?' * len(WALLETS))
        fresh_cut = now - 90
        row = db.execute(
            f'''SELECT COUNT(*) AS n,
                       SUM(CASE WHEN a.source_ts>=? THEN 1 ELSE 0 END) AS fresh,
                       SUM(CASE WHEN a.source_ts IS NULL OR a.source_ts<? THEN 1 ELSE 0 END) AS history,
                       SUM(CASE WHEN a.source_ts>=? AND json_extract(a.body,'$.side')='BUY' THEN 1 ELSE 0 END) AS buys,
                       SUM(CASE WHEN a.source_ts>=? AND json_extract(a.body,'$.side')='SELL' THEN 1 ELSE 0 END) AS sells,
                       MIN(a.first_seen) AS oldest,
                       MIN(CASE WHEN a.source_ts>=? THEN a.first_seen END) AS oldest_fresh
                FROM wallet_activity a
                WHERE a.first_seen>=? AND a.wallet IN ({marks})
                AND NOT EXISTS (
                    SELECT 1 FROM mitch_events e
                    WHERE e.wallet=a.wallet AND e.event_key=a.event_key
                      AND e.reason != 'AWAITING_SOURCE_PRICE')''',
            (fresh_cut, fresh_cut, fresh_cut, fresh_cut, fresh_cut, start, *WALLETS),
        ).fetchone()
        arrivals = db.execute(
            f'SELECT COUNT(*) FROM wallet_activity WHERE first_seen>=? AND wallet IN ({marks})',
            (now - 60, *WALLETS),
        ).fetchone()[0]
        decisions = db.execute(
            "SELECT COUNT(*) FROM mitch_events WHERE at>=? AND reason!='AWAITING_SOURCE_PRICE'",
            (now - 60,),
        ).fetchone()[0]
        expired = db.execute(
            "SELECT COUNT(*) FROM mitch_events WHERE reason='LATE_BUY_NOT_COPIED' AND at>=?",
            (now - 120,),
        ).fetchone()[0]
        oldest = row['oldest'] if hasattr(row, 'keys') else row[5]
        oldest_fresh = row['oldest_fresh'] if hasattr(row, 'keys') else row[6]
        count = int(row[0] or 0)
        def age(stamp):
            if stamp is None:
                return None
            return round(now - float(stamp), 1)
        return {
            'backlog': count,
            'fresh': int(row[1] or 0),
            'history': int(row[2] or 0),
            'buys': int(row[3] or 0),
            'sells': int(row[4] or 0),
            'oldest_age_s': age(oldest),
            'oldest_fresh_age_s': age(oldest_fresh),
            'arrivals_60s': int(arrivals or 0),
            'decisions_60s': int(decisions or 0),
            'expired_recent': int(expired or 0),
        }

    def _executed_timings(self, db):
        """Timings stored on fills. The latest journal page is not the sample."""
        rows = []
        missing = 0
        for (body,) in db.execute(
            """SELECT body FROM mitch_events
               WHERE reason IN ('MITCH_BUY','MITCH_ADD','MITCH_SELL','LATE_SELL_RECOVERED')"""
        ):
            timing = json.loads(body or '{}').get('timing') or {}
            if timing:
                rows.append(timing)
            else:
                missing += 1
        return rows, missing

    def _late_split(self, db, start):
        """History before activation versus a new buy this program did not copy."""
        has_activity = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='wallet_activity'"
        ).fetchone() is not None
        before = after = unstamped = 0
        if has_activity:
            query = '''SELECT e.body, a.source_ts
                       FROM mitch_events e
                       LEFT JOIN wallet_activity a
                         ON a.wallet=e.wallet AND a.event_key=e.event_key
                       WHERE e.reason='LATE_BUY_NOT_COPIED' '''
        else:
            query = "SELECT body, NULL FROM mitch_events WHERE reason='LATE_BUY_NOT_COPIED'"
        for body, activity_ts in db.execute(query):
            parsed = json.loads(body or '{}')
            src = activity_ts if activity_ts is not None else parsed.get('source_ts')
            if src is None:
                unstamped += 1
            elif float(src) < start:
                before += 1
            else:
                after += 1
        return before, after, unstamped

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
                limit_micro = int(Decimal(row['limit_usd']) * Decimal(1_000_000))
                windows = []
                for window, spent in db.execute(
                    'SELECT window, spent FROM mitch_windows WHERE wallet=?',
                    (row['wallet'],),
                ):
                    spent = int(spent)
                    open_now = False
                    try:
                        begin = int(str(window).rsplit('-', 1)[-1])
                        open_now = begin <= now < begin + 900
                    except ValueError:
                        begin = None
                    windows.append({
                        'window': window,
                        'spent_micro': spent,
                        'limit_micro': limit_micro,
                        'within_limit': spent <= limit_micro,
                        'open': open_now,
                    })
                row['windows'] = windows
                row['spent_since_start_micro'] = sum(item['spent_micro'] for item in windows)
                row['window_limit_breaks'] = sum(1 for item in windows if not item['within_limit'])
                cash_row = db.execute(
                    'SELECT cash, reserved FROM mitch_accounts WHERE wallet=?',
                    (row['wallet'],),
                ).fetchone()
                cash = int(cash_row[0]) if cash_row else CAPITAL_MICRO
                reserved = int(cash_row[1] or 0) if cash_row and len(cash_row) > 1 else 0
                row['cash_micro'] = cash
                row['reserved_micro'] = reserved
                row['tradable_micro'] = tradable_cash(cash, reserved)
            pauses = self.refresh_pauses(db)
            stint = self.stint(db)
            stint_at = float(stint['at']) if stint else None
            for row in wallets:
                hold = (pauses.get('wallets') or {}).get(row['wallet']) or {}
                row['paused'] = bool(hold.get('paused'))
                row['pause_reason'] = hold.get('reason')
                row['pause_today_net_usd'] = hold.get('today_net_usd')
                row['pause_all_net_usd'] = hold.get('all_net_usd')
                inside = [p for p in closed if p.get('wallet') == row['wallet']
                          and stint_at is not None and float(p.get('opened') or 0) >= stint_at]
                row['period_net_micro'] = sum(int(p['pnl_micro']) for p in inside)
                row['period_closed'] = len(inside)
                row['period_copies'] = db.execute(
                    "SELECT COUNT(*) FROM mitch_events WHERE wallet=? AND reason IN ('MITCH_BUY','MITCH_ADD') AND at>=?",
                    (row['wallet'], stint_at or now),
                ).fetchone()[0]
            period_events = []
            period_reasons = {}
            if stint_at is not None:
                for reason, count in db.execute(
                    "SELECT reason, COUNT(*) FROM mitch_events WHERE at>=? AND reason!='AWAITING_SOURCE_PRICE' GROUP BY reason",
                    (stint_at,),
                ):
                    period_reasons[reason] = int(count)
                for e in db.execute(
                    "SELECT wallet, reason, body, at FROM mitch_events WHERE at>=? AND reason NOT IN "
                    "('AWAITING_SOURCE_PRICE','NOT_BTC_15M','MITCH_SKIP_5M','HISTORICAL_BEFORE_START') "
                    "ORDER BY at DESC LIMIT 25",
                    (stint_at,),
                ):
                    body = json.loads(e[2] or '{}')
                    timing = body.get('timing') or {}
                    period_events.append({
                        'at': e[3], 'wallet': e[0], 'reason': e[1], 'side': body.get('side'),
                        'market': body.get('market'), 'total_ms': timing.get('total_ms'),
                        'detect_ms': timing.get('detect_ms'), 'book_ms': timing.get('book_ms'),
                        'source': body.get('source') or timing.get('source_precision'),
                    })
            from .profit_bank import bank_snapshot
            bank = bank_snapshot(db)
            latency_rows, missing_timing = self._executed_timings(db)
            late_before, late_after, late_unstamped = self._late_split(db, self.started())
        latency = latency_summary(latency_rows)
        latency['executed_without_timing'] = missing_timing
        payload = {
            'spec': SPEC,
            'assumptions': list(ASSUMPTIONS),
            'grouping': GROUPING,
            'capital_usd_per_wallet': CAPITAL_MICRO / 1e6,
            'capital_note': 'Mitch did not set the paper capital. $500 per wallet is a temporary assumption.',
            'reserve_pct': float(RESERVE_PCT),
            'reserve_note': '40% of each new closed win is reserved. That cash stays on the account and is not spent on the next buy. Past wins already in cash are not clawed back.',
            'profit_bank': bank,
            'miha_5m': {'copy': False, 'verdict_at': '2026-10-07', 'note': MIHA_5M_VERDICT},
            'book': getattr(self, '_last_book', None),
            'updated_at': now,
            'closed_today_micro': today_net,
            'closed_all_micro': all_net,
            'open_count': len(opens),
            'open_cost_micro': sum(int(p['cost']) + int(p['fee']) for p in opens),
            'open_mark_micro': None,
            'open_mark_note': 'No live mark is stored. Open cost is capital in use, not a result.',
            'wallets': wallets,
            'max_buy_age_s': MAX_BUY_AGE,
            'stint': self.stint(),
            'fast': fast_status(),
            'stop_active': self.stopped(),
            'period_reasons': period_reasons,
            'period_events': period_events,
            'journal': [{
                'at': p.get('closed_at'), 'wallet': p.get('wallet'),
                'slug': p.get('slug'), 'status': p.get('status'),
                'pnl_micro': p.get('pnl_micro'),
                'source_price': p.get('source_price'), 'copy_vwap': p.get('copy_vwap'),
                'cost': p.get('cost'), 'fee': p.get('fee'),
            } for p in sorted(
                closed, key=lambda item: float(item.get('closed_at') or 0), reverse=True,
            )[:40]],
            'recent': [{
                'at': e['at'], 'wallet': e['wallet'], 'reason': e['reason'],
                'detail': json.loads(e['body'] or '{}'),
            } for e in events],
            'latency': latency,
            'late': {
                'period_start': self.started(),
                'period_end': now,
                'before_activation': late_before,
                'after_activation_not_copied': late_after,
                'unstamped': late_unstamped,
                'note': 'A skipped buy is not a lost profit. Before activation is history. After activation is a signal this program did not copy.',
            },
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
        from .hot_path import COPY, DB
        loop = asyncio.get_running_loop()
        for wallet in WALLETS:
            try:
                from .data_api import fetch_rows
                raw, _cursor = await loop.run_in_executor(
                    COPY, lambda w=wallet: fetch_rows(self.fetch, 'positions', user=w, limit=500),
                )
            except Exception:
                continue
            await loop.run_in_executor(DB, self._apply_anchor, wallet, raw)

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

    async def submit_fast(self, wallet, body, detected_at):
        """A fill read from the pending exchange transaction. Decide now."""
        from .fast_match import insert_row
        from .hot_path import MITCH
        if wallet not in WALLETS:
            return
        loop = asyncio.get_running_loop()
        row = await loop.run_in_executor(MITCH, insert_row, self.store, wallet, body, detected_at)
        if row:
            await self.handle(row, pool=MITCH)

    async def run(self):
        from .hot_path import DB
        global ACTIVE
        ACTIVE = self
        loop = asyncio.get_running_loop()
        # Schema first, then the board, then decisions. Anchors must not hold the first step.
        await loop.run_in_executor(DB, self.ensure)
        await loop.run_in_executor(DB, self.publish)
        anchors = asyncio.create_task(self.ensure_anchors())
        last_publish = self.clock()
        while True:
            try:
                await self.step()
                if self.clock() - last_publish >= 2:
                    await loop.run_in_executor(DB, self.publish)
                    last_publish = self.clock()
                if anchors is not None and anchors.done():
                    failed = anchors.exception()
                    if failed:
                        log.warning('mitch anchors: %s', failed)
                    anchors = None
            except Exception as error:
                log.warning('mitch step: %s', error)
                try:
                    await asyncio.to_thread(
                        self.store.set, 'mitch_copy_error',
                        {'at': self.clock(), 'error': str(error)[:300]},
                    )
                except Exception:
                    pass
            ready = getattr(self.store, 'wallet_activity_ready', None)
            if ready is not None:
                try:
                    await asyncio.wait_for(ready.wait(), timeout=0.05)
                except asyncio.TimeoutError:
                    pass
                else:
                    ready.clear()
            else:
                await asyncio.sleep(0.05)

    def _load_pending(self):
        with self.store.connect() as db:
            return self.pending(db, self.clock())

    def _load_backlog(self):
        with self.store.connect() as db:
            return self.backlog(db, self.clock())

    async def step(self):
        from .hot_path import READ, DB, latest_stage, snapshot
        loop = asyncio.get_running_loop()
        rows = await loop.run_in_executor(READ, self._load_pending)
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
        if self.clock() - getattr(self, '_depth_at', 0) >= 2:
            self._depth = await loop.run_in_executor(READ, self._load_backlog)
            self._depth_at = self.clock()
        await loop.run_in_executor(
            DB, self._progress, len(rows), getattr(self, '_depth', None), latest_stage(), snapshot(),
        )
        return len(rows)

    def _progress(self, batch, depth, stage, pools):
        depth = depth or {}
        stage = stage or {}
        pools = pools or {}
        # queue is the real pending count. batch is only what this step took.
        self.store.set('mitch_progress', {
            'at': self.clock(),
            'batch': batch,
            'queue': depth.get('backlog', batch),
            'backlog': depth.get('backlog'),
            'fresh': depth.get('fresh'),
            'history': depth.get('history'),
            'buys': depth.get('buys'),
            'sells': depth.get('sells'),
            'oldest_age_s': depth.get('oldest_age_s'),
            'oldest_fresh_age_s': depth.get('oldest_fresh_age_s'),
            'arrivals_60s': depth.get('arrivals_60s'),
            'decisions_60s': depth.get('decisions_60s'),
            'expired_recent': depth.get('expired_recent'),
            'book_pool_ms': stage.get('pool_ms'),
            'book_http_ms': stage.get('http_ms'),
            'book_tries': stage.get('tries'),
            'book_cache': stage.get('cache'),
            'db_wait_ms': stage.get('db_wait_ms'),
            'db_write_ms': stage.get('db_write_ms'),
            'loop_lag_ms': pools.get('loop_lag_ms'),
            'copy_queued': pools.get('copy_queued'),
            'io_queued': pools.get('io_queued'),
            'db_queued': pools.get('db_queued'),
            'status': 'running',
        })

    def _prefilter(self, row, queued):
        """Marks that need no book. Runs on the database thread."""
        wallet = row['wallet']
        key = row['event_key']
        event = json.loads(row['body']) if isinstance(row['body'], str) else row['body']
        if wallet not in WALLETS:
            return {'stop': True}
        if float(row.get('source_ts') or 0) < self.started() and event.get('_source') != 'chain_fast':
            with self.store.connect() as db:
                if not self._seen(db, wallet, key):
                    self._mark(db, wallet, key, 'HISTORICAL_BEFORE_START', self._case(row, event))
            return {'stop': True}
        source = event.get('_source')
        if source == 'chain_fast':
            age = self.clock() - float(row['first_seen'])
            if age > MAX_BUY_AGE:
                with self.store.connect() as db:
                    self._mark(db, wallet, key, 'MITCH_NEED_CHAIN', self._case(row, event, {
                        'timing': self._timing(row, queued, self.clock(), self.clock(), 'local_detect', False),
                    }))
                return {'stop': True}
            # The transfer is known. Warm the book. Do not copy a quote as his price.
            return {
                'stop': True, 'prefetch': True, 'row': row, 'event': event,
            }
        if is_updown_5m(event):
            with self.store.connect() as db:
                self._mark(db, wallet, key, 'MITCH_SKIP_5M', self._case(row, event, {
                    'note': MIHA_5M_VERDICT,
                }))
            return {'stop': True}
        if not is_btc_15m(event) or event.get('type') != 'TRADE' or event.get('side') not in ('BUY', 'SELL'):
            with self.store.connect() as db:
                self._mark(db, wallet, key, 'NOT_BTC_15M', self._case(row, event))
            return {'stop': True}
        if source in ('market_trade', 'clob_match'):
            basis = 'source_subsecond'
        elif source == 'order_filled':
            basis = 'chain_fill'
        else:
            basis = 'source_second'
        clock = self.store.get('clock_status') or {}
        age = self.clock() - float(row['source_ts'])
        if event['side'] == 'BUY' and event.get('_ts_basis') == 'local_detect':
            with self.store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                self._record_source(db, wallet, str(event.get('asset') or ''), key, event, buy=True)
                self._mark(db, wallet, key, 'SOURCE_TIME_UNKNOWN', self._case(row, event, {
                    'source': source,
                }))
            return {'stop': True}
        if event['side'] == 'BUY' and source not in CHAIN_SOURCES:
            with self.store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                self._record_source(db, wallet, str(event.get('asset') or ''), key, event, buy=True)
                self._mark(db, wallet, key, 'MITCH_NEED_CHAIN', self._case(row, event, {
                    'source': source, 'age_s': round(age, 3),
                }))
            return {'stop': True}
        if event['side'] == 'BUY' and age > MAX_BUY_AGE:
            with self.store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                self._record_source(db, wallet, str(event.get('asset') or ''), key, event, buy=True)
                self._mark(db, wallet, key, 'LATE_BUY_NOT_COPIED', self._case(row, event, {
                    'class': 'historical' if float(row['source_ts']) < self.started() else 'queue',
                }))
            return {'stop': True}
        if event['side'] == 'SELL' and age > 90:
            # Do not fill this at the historical price. The current book decides
            # a recovery, or the open position stays until settlement.
            return {
                'stop': False, 'late_sell': True, 'row': row, 'event': event, 'queued': queued,
                'basis': basis, 'clock': clock, 'clock_ok': clock.get('status') == 'synced', 'age': age,
            }
        return {
            'stop': False, 'row': row, 'event': event, 'queued': queued,
            'basis': basis, 'clock': clock, 'clock_ok': clock.get('status') == 'synced', 'age': age,
        }

    def _recover_late_sell(self, db, row, event, checked, terms, timing, book_started, book_done):
        """A sell we received too late. Current bids, or the position stays open.

        The source trade is recorded either way. His old price is not our fill.
        """
        wallet = row['wallet']
        key = row['event_key']
        token = str(event.get('asset') or '')
        open_trade = None
        for (body,) in db.execute('SELECT body FROM mitch_positions WHERE wallet=?', (wallet,)):
            current = json.loads(body)
            if current.get('status') == 'OPEN' and current.get('token') == token:
                open_trade = current
                break
        fraction = self.fraction_for(db, wallet, event)
        self._record_source(db, wallet, token, key, event, buy=False)
        if not open_trade:
            self._mark(db, wallet, key, 'LATE_SELL_RECONCILED', self._case(row, event, {
                'timing': timing, 'position': 'none',
            }))
            return
        slow = (book_done - book_started) > 3
        book_bad = (not checked) or checked.get('error') or (not terms) or (not terms.get('fee_verified'))
        detail = {
            'timing': timing,
            'position': 'open_until_settlement',
            'price_basis': 'current_book',
            'source_price': str(source_price(event) or ''),
        }
        if slow or book_bad or fraction is None:
            detail['fraction'] = None if fraction is None else str(fraction)
            self._mark(db, wallet, key, 'LATE_SELL_EXPOSED', self._case(row, event, detail))
            return
        cut = our_sell_shares(open_trade['shares'], fraction)
        fill = self._sell_fill(
            checked, cut, terms.get('fee_rate') or '0', terms.get('fee_verified') is True,
        )
        if not cut or not fill:
            self._mark(db, wallet, key, 'LATE_SELL_EXPOSED', self._case(row, event, detail))
            return
        self.apply_sell(
            db, wallet, key, event, checked, fraction, timing, True,
            fee_rate=terms['fee_rate'], fee_verified=True, reason='LATE_SELL_RECOVERED',
        )

    def _finish(self, pre, checked, terms, book_started, book_done, stage=None, db_submitted=None):
        row = pre['row']
        event = pre['event']
        wallet = row['wallet']
        key = row['event_key']
        stage = dict(stage or {})
        if db_submitted is not None:
            stage['db_wait_ms'] = round((time.perf_counter() - db_submitted) * 1000, 1)
        write_started = time.perf_counter()
        decided = pre.get('decided_at') or self.clock()
        timing = self._timing(
            row, pre['queued'], decided, decided, pre['basis'], pre['clock_ok'],
            book_started, book_done, pre['clock'], stage,
        )
        from .hot_path import note_stage
        class _Write:
            def __enter__(_self):
                _self._ctx = self.store.connect()
                return _self._ctx.__enter__()
            def __exit__(_self, *exc):
                try:
                    return _self._ctx.__exit__(*exc)
                finally:
                    stage['db_write_ms'] = round((time.perf_counter() - write_started) * 1000, 1)
                    note_stage(stage)
        with _Write() as db:
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
            if pre.get('late_sell'):
                self._recover_late_sell(
                    db, row, event, checked, terms, timing, book_started, book_done,
                )
                return
            if event.get('_source') == 'chain_fast' or source_price(event) is None and event['side'] == 'BUY':
                self._mark(db, wallet, key, 'MITCH_NEED_CHAIN', self._case(row, event, {'timing': timing}))
                return
            if event['side'] == 'BUY' and event.get('_source') not in CHAIN_SOURCES:
                self._record_source(db, wallet, str(event.get('asset') or ''), key, event, buy=True)
                self._mark(db, wallet, key, 'MITCH_NEED_CHAIN', self._case(row, event, {'timing': timing}))
                return
            if float(row['source_ts']) < self.started():
                self._mark(db, wallet, key, 'HISTORICAL_BEFORE_START', self._case(row, event, {'timing': timing}))
                return
            # The decision is taken when the book is in. Waiting for the database
            # writer afterwards is bookkeeping, not a later trade.
            decided = pre.get('decided_at') or self.clock()
            if event['side'] == 'BUY' and decided - float(row['source_ts']) > MAX_BUY_AGE:
                self._record_source(db, wallet, str(event.get('asset') or ''), key, event, buy=True)
                self._mark(db, wallet, key, 'LATE_BUY_NOT_COPIED', self._case(row, event, {'timing': timing}))
                return
            if event['side'] == 'BUY' and book_done - book_started > MAX_BUY_AGE:
                self._mark(db, wallet, key, 'BOOK_WAIT_TOO_LONG', self._case(row, event, {'timing': timing}))
                return
            if event['side'] != 'BUY' and book_done - book_started > 3:
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
                db, wallet, key, event, checked, fraction, timing, pre['age'] > 2,
                fee_rate=terms['fee_rate'], fee_verified=True,
            )

    async def handle(self, row, pool=None):
        from .hot_path import DB
        pool = pool or DB
        queued = time.monotonic()
        pre = await asyncio.get_running_loop().run_in_executor(pool, self._prefilter, row, queued)
        if not pre or pre.get('stop'):
            if pre and pre.get('prefetch'):
                await self._book(str(pre['event'].get('asset') or ''))
            return
        book_started = time.monotonic()
        checked, terms = await asyncio.gather(
            self._book(str(pre['event'].get('asset') or '')),
            self._terms(pre['event']),
        )
        self._note_book(pre, checked)
        book_done = time.monotonic()
        stage = {}
        if isinstance(checked, dict):
            stage = checked.pop('_stage', None) or {}
        pre['decided_at'] = self.clock()
        db_submitted = time.perf_counter()
        await asyncio.get_running_loop().run_in_executor(
            pool, self._finish, pre, checked, terms, book_started, book_done, stage, db_submitted,
        )

    def _note_book(self, pre, checked):
        view = describe_book(checked if isinstance(checked, dict) else None)
        event = pre.get('event') or {}
        side = event.get('side')
        if side == 'BUY':
            state = 'ask jest — kopia jeszcze wymaga ceny źródła, limitu okna i 10 centów' if view.get('has_ask') else 'brak ask — kopia nie wejdzie'
        elif side == 'SELL':
            state = 'bid jest — sprzedaż idzie po arkuszu' if view.get('has_bid') else 'brak bid — sprzedaż nie wejdzie'
        else:
            state = 'brak strony zlecenia'
        view.update(
            wallet=str((pre.get('row') or {}).get('wallet') or '')[-8:],
            token=str(event.get('asset') or ''),
            slug=str(event.get('slug') or ''),
            side=side,
            copy_state=state,
            seen_at=self.clock(),
        )
        self._last_book = view

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

    def _timing(self, row, received_mono, decision_at, finished_at, basis, clock_ok, exec_started=None, exec_done=None, clock=None, stage=None):
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
        if basis in ('source_subsecond', 'chain_fill') and clock_ok:
            total = (finished_at - source_ts) * 1000
            confirmed = True
        clock = clock or {}
        stage = stage or {}
        provider = None
        try:
            body = json.loads(row['body']) if isinstance(row.get('body'), str) else (row.get('body') or {})
            if isinstance(body, dict) and body.get('_provider_delay_s') is not None:
                provider = round(float(body['_provider_delay_s']) * 1000, 1)
        except (TypeError, ValueError, json.JSONDecodeError):
            provider = None
        return {
            'source_ts': source_ts,
            'source_precision': basis,
            'source_limit': 'one_second_api' if basis == 'source_second' else basis,
            'received_at': first_seen,
            'decision_at': decision_at,
            'exec_finished_at': finished_at,
            'queue_ms': round(queue_ms, 1),
            'detect_ms': None if detect is None else round(detect, 1),
            # Wall time around the book task, including the wait for a free thread.
            'book_ms': None if book_ms is None else round(book_ms, 1),
            'book_pool_ms': stage.get('pool_ms'),
            'book_http_ms': stage.get('http_ms'),
            'book_tries': stage.get('tries'),
            'book_cache': stage.get('cache'),
            'db_wait_ms': stage.get('db_wait_ms'),
            'process_ms': None if book_ms is None else round(book_ms, 1),
            'provider_delay_ms': provider,
            'total_ms': None if total is None else round(total, 1),
            'total_confirmed': confirmed,
            'clock_status': clock.get('status'),
            'clock_offset_ms': clock.get('offset_ms'),
            'clock_uncertainty_ms': clock.get('uncertainty_ms'),
            'mono_book_start': exec_started,
            'mono_book_done': exec_done,
        }

    async def _book(self, token):
        stage = {'pool_ms': 0, 'http_ms': 0, 'tries': 0, 'cache': False}
        if not token or self.fetch is None:
            return {'error': 'NO_BOOK', '_stage': stage}
        from .hot_path import COPY, cached_book, remember_book, measured_call, note_stage
        raw = cached_book(token, 1.0, self.clock())
        if raw is not None:
            stage = {'pool_ms': 0, 'http_ms': 0, 'tries': 0, 'cache': True}
            note_stage(stage)
        else:
            import urllib.parse
            url = 'https://clob.polymarket.com/book?token_id=' + urllib.parse.quote(token, safe='')
            submitted = time.perf_counter()
            try:
                raw, stage = await asyncio.get_running_loop().run_in_executor(
                    COPY, measured_call, self.fetch, url, submitted,
                )
            except Exception:
                return {'error': 'NO_BOOK', '_stage': stage}
            remember_book(token, raw, self.clock())
        from .worker import normalize_book
        try:
            checked = normalize_book(raw, token, self.clock(), max_age=3)
        except ValueError as error:
            text = str(error)
            code = 'BOOK_TOKEN_MISMATCH' if 'token' in text else 'BOOK_STALE'
            return {'error': code, '_stage': stage}
        checked['_stage'] = stage
        return checked

    async def _terms(self, event):
        slug = str((event or {}).get('slug') or '')
        if self.fetch is None or not slug.startswith('btc-updown-15m-'):
            return None
        from .hot_path import COPY, cached_terms, remember_terms
        raw = cached_terms(slug, 30.0, self.clock())
        if raw is None:
            try:
                raw = await asyncio.get_running_loop().run_in_executor(
                    COPY, self.fetch, 'https://gamma-api.polymarket.com/markets/slug/' + slug,
                )
            except Exception:
                return None
            remember_terms(slug, raw, self.clock())
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
            lock_profit(db, 'mitch_accounts', current['wallet'], pnl)
            current.update(
                status='SETTLED', payout=payout, exit_fee=0, closed_at=self.clock(),
                pnl_micro=pnl, official_winner=str(winners[0].get('token_id')),
                official_seen_at=self.clock(),
            )
            db.execute('UPDATE mitch_positions SET body=? WHERE id=?', (json.dumps(current), current['id']))
            self.refresh_pauses(db)

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
