"""Public, read-only activity polling; never signs or copies orders."""
import asyncio
import hashlib
import json
import math
import time
from decimal import Decimal
from urllib.parse import urlencode

SEED_WALLETS = (
 '0x16217458b59b3458149918058754cd234096b159',
 '0xeda9247a2b3c99a9e0bf46cdac6e1974365cf589',
 '0x943cea746e701823b6902a6f4eaeed58207e77c2',
 '0xeebde7a0e019a63e6b476eb425505b7b3e6eba30',
)

# Paper picks from the 30-day 5m/15m screen. Not live. Not auto-promoted.
PAPER_EXTRA = (
 '0x84389cfc4a652ea14d8d8be969769b1f69de3680',
 '0xce50c96b976203b53342a0a801067d2cdcfcf46e',
)

WALLET_LABELS = {
    '0x84389cfc4a652ea14d8d8be969769b1f69de3680': 'Atomforge',
    '0xce50c96b976203b53342a0a801067d2cdcfcf46e': 'honey-spot',
}

# Backward compatibility — existing imports of WALLETS keep working.
WALLETS = SEED_WALLETS


def wallet_label(wallet):
    return WALLET_LABELS.get(wallet) or wallet[-8:]


def ensure_active_wallets_table(store):
    """Create the active_wallets table and seed it once.

    A later read must not take the write lock. The dashboard and the copy
    loop call this on the event loop.
    """
    if getattr(store, '_active_wallets_ready', False):
        return
    with store.connect() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS active_wallets (
            wallet TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            added_at REAL NOT NULL,
            score REAL DEFAULT 0,
            copy_enabled INTEGER DEFAULT 0
        )''')
        for w in SEED_WALLETS:
            db.execute('INSERT OR IGNORE INTO active_wallets VALUES (?,?,?,?,?)',
                       (w, 'seed', time.time(), 0, 0))
            db.execute("UPDATE active_wallets SET source='seed' WHERE wallet=?", (w,))
        for w in PAPER_EXTRA:
            db.execute('INSERT OR IGNORE INTO active_wallets VALUES (?,?,?,?,?)',
                       (w, 'paper_pick', time.time(), 0, 1))
            db.execute("UPDATE active_wallets SET source='paper_pick', copy_enabled=1 WHERE wallet=?", (w,))
    store._active_wallets_ready = True


def get_active_wallets(store):
    """Seeds, paper picks, and roster wallets we still watch.

    `observed` is watched with copy buys paused. Discovery rows in
    active_wallets are not a second list.
    """
    ensure_active_wallets_table(store)
    seen=[]
    for w in SEED_WALLETS + PAPER_EXTRA:
        if w not in seen: seen.append(w)
    roster = store.get('wallet_roster', {})
    for w, row in (roster.get('wallets') or {}).items():
        if row.get('state') in ('paper_test', 'paper_active', 'paused', 'observed') and w not in seen:
            seen.append(w)
    from .mitch_copy import WALLETS as MITCH_WALLETS
    for w in MITCH_WALLETS:
        if w not in seen:
            seen.append(w)
    return tuple(seen)


def _fill_id(row):
    """Stable id of one execution. Size and price are not an id."""
    if not isinstance(row, dict):
        return None
    for key in ('id', 'tradeId', 'tradeID', 'fillId'):
        if row.get(key) not in (None, ''):
            return 'id:' + str(row[key])
    if row.get('logIndex') not in (None, ''):
        return 'log:' + str(row.get('transactionHash') or '') + ':' + str(row['logIndex'])
    return None


def _fill_sig(row):
    found = _fill_id(row)
    if found:
        return found
    return 'anon:' + '|'.join(str(row.get(k) if row.get(k) is not None else '') for k in ('size', 'usdcSize', 'price'))


def _money(value):
    if value in (None, ''):
        return None
    try:
        number = Decimal(str(value))
    except Exception:
        return None
    if not number.is_finite():
        return None
    return number


def _as_fill(row, fallback):
    return {
        'id': _fill_id(row) or fallback,
        'size': str(row.get('size') if row.get('size') is not None else ''),
        'usdcSize': str(row.get('usdcSize') if row.get('usdcSize') is not None else ''),
        'price': str(row.get('price') if row.get('price') is not None else ''),
    }


def _sum_fills(fills):
    size = Decimal(0)
    usdc = Decimal(0)
    for fill in fills:
        part = _money(fill.get('size'))
        paid = _money(fill.get('usdcSize'))
        if part is None or paid is None or part < 0 or paid < 0:
            return None
        size += part
        usdc += paid
    if size <= 0 or usdc <= 0:
        return None
    return size, usdc


def merge_activity_body(existing_body, row):
    """Combine executions of one trade without depending on arrival order.

    A fill id that arrives again replaces that fill. A new id is added.
    Two executions with the same size are not the same fill. A chain-fast
    book quote is replaced and is never added to the price he paid.
    """
    existing = json.loads(existing_body)
    if existing.get('_source') in ('clob_match', 'order_filled'):
        # The exchange transaction is the execution. A later public row does
        # not replace it, and the source stays on the row for the audit.
        return existing_body, False
    if existing.get('_source') == 'chain_fast':
        merged = dict(row)
        merged.pop('_source', None)
        merged['_fills'] = [_as_fill(row, 'anon:0')]
        return json.dumps(merged, allow_nan=False), True
    fills = [dict(item) for item in (existing.get('_fills') or []) if isinstance(item, dict)]
    if not fills:
        fills = [_as_fill(existing, 'anon:0')]
    incoming_id = _fill_id(row)
    if incoming_id is None:
        if len(fills) == 1 and str(fills[0].get('id', '')).startswith('anon:'):
            replacement = _as_fill(row, 'anon:0')
            if replacement['size'] == fills[0].get('size') and replacement['usdcSize'] == fills[0].get('usdcSize'):
                return existing_body, False
            fills = [replacement]
        else:
            return existing_body, False
    else:
        replaced = False
        for fill in fills:
            if fill.get('id') == incoming_id:
                fill.update(_as_fill(row, incoming_id))
                replaced = True
                break
        if not replaced:
            fills.append(_as_fill(row, incoming_id))
    summed = _sum_fills(fills)
    if summed is None:
        return existing_body, False
    size, usdc = summed
    merged = dict(existing)
    merged['size'] = format(size, 'f')
    merged['usdcSize'] = format(usdc, 'f')
    merged['price'] = format(usdc / size, 'f')
    merged['_fills'] = fills
    merged.pop('_source', None)
    body = json.dumps(merged, allow_nan=False)
    if body == existing_body:
        return existing_body, False
    return body, True


MERGE_WINDOW_S = 600
STATUS_EVERY_S = 30
POLL_OVERLAP_S = 60
COPY_POLL_S = 2


class WalletObserver:
    def __init__(self, store, fetch):
        self.store, self.fetch = store, fetch
        if not hasattr(store,"wallet_activity_ready"):store.wallet_activity_ready=asyncio.Event()
        with store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS wallet_activity (wallet TEXT, event_key TEXT, first_seen REAL, source_ts REAL, body TEXT, PRIMARY KEY(wallet,event_key))')
            db.execute('CREATE INDEX IF NOT EXISTS wallet_activity_seen ON wallet_activity(first_seen)')
            # Per-wallet time range (missed-sell lookup). Built live on 13 Oct 2026.
            db.execute('CREATE INDEX IF NOT EXISTS wallet_activity_wallet_seen ON wallet_activity(wallet, first_seen)')
        ensure_active_wallets_table(store)

    def ingest(self, wallet, rows, now):
        """Store new fills and merge changed ones.

        11 Oct 2026: a page of up to 500 mostly known rows went through
        INSERT OR IGNORE one by one, so the write lock was held for the whole
        page on every poll of ~120 wallets (hold p90 2 s, up to 15 s), and
        Mitch's writes waited. Known rows are now compared without the lock;
        only new or changed rows are written, in one short transaction.
        """
        if not isinstance(rows, list): raise ValueError('activity response must be a list')
        from .wallet_chain_monitor import _row_key
        prepared = {}
        for row in rows:
            if not isinstance(row, dict): raise ValueError('invalid activity row')
            if str(row.get('proxyWallet','')).lower() != wallet: raise ValueError('wallet mismatch')
            ts = float(row['timestamp'])
            if not math.isfinite(ts) or not 0 < ts <= now+5: raise ValueError('invalid source timestamp')
            # API v1 has no log index. This fingerprint is NOT an execution ID.
            if not row.get('transactionHash'): raise ValueError('missing transaction hash')
            key = _row_key(row)
            prepared.setdefault(key, []).append((ts, row))
        if not prepared:
            return 0
        keys = list(prepared)
        known = {}
        # A fill older than ten minutes no longer changes: only its presence is
        # read. Reading and parsing every stored body was most of the CPU.
        recent = {k for k, items in prepared.items() if max(ts for ts, _ in items) >= now - MERGE_WINDOW_S}
        with self.store.connect() as db:
            for i in range(0, len(keys), 500):
                part = keys[i:i + 500]
                marks = ','.join('?' * len(part))
                for key, body in db.execute(
                        f'SELECT event_key, CASE WHEN event_key IN ({marks}) THEN body END FROM wallet_activity '
                        f'WHERE wallet=? AND event_key IN ({marks})',
                        (*[k if k in recent else '' for k in part], wallet, *part)):
                    known[key] = body
        fresh = []
        changed = []
        for key, items in prepared.items():
            if key not in known:
                fresh.append(key)
                continue
            body = known[key]
            if body is None:
                continue
            dirty = False
            for ts, row in items:
                if row.get('_source') == 'chain_fast':
                    continue
                merged, did_change = merge_activity_body(body, row)
                if did_change:
                    body, dirty = merged, True
            if dirty:
                changed.append(key)
        if not fresh and not changed:
            return 0
        inserted = 0
        updated = 0
        with self.store.connect() as db:
            for key in fresh:
                for ts, row in prepared[key]:
                    stored = dict(row)
                    if row.get('_source') != 'chain_fast':
                        stored['_fills'] = [_as_fill(row, 'anon:0')]
                    cur = db.execute('INSERT OR IGNORE INTO wallet_activity VALUES (?,?,?,?,?)',
                                     (wallet, key, now, ts, json.dumps(stored, allow_nan=False)))
                    if cur.rowcount:
                        inserted += 1
                        continue
                    if row.get('_source') == 'chain_fast':
                        continue
                    # Same hash can carry several fills. Sum them once.
                    changed.append(key)
                    break
            for key in dict.fromkeys(changed):
                # Re-read under the lock: the chain or the fast lane may have
                # written this row since the read above.
                existing = db.execute(
                    'SELECT body FROM wallet_activity WHERE wallet=? AND event_key=?', (wallet, key),
                ).fetchone()
                if not existing:
                    continue
                body, dirty, ts_new = existing[0], False, None
                for ts, row in prepared[key]:
                    if row.get('_source') == 'chain_fast':
                        continue
                    merged, did_change = merge_activity_body(body, row)
                    if did_change:
                        body, dirty, ts_new = merged, True, ts
                if dirty:
                    db.execute('UPDATE wallet_activity SET source_ts=?, body=? WHERE wallet=? AND event_key=?',
                               (ts_new, body, wallet, key))
                    updated += 1
        if inserted or updated:
            self.store.wallet_activity_ready.set()
        return inserted

    def _poll_sync(self, wallet, previous):
        """Fetch and insert off the event loop.

        A page of 500 rows inserted on the loop froze the price feed and the
        chain socket long enough for both handshakes to time out.
        """
        key = 'wallet_observer:'+wallet
        end = int(time.time())
        # 60 s of overlap covers the public list's indexing delay; 120 s made
        # every 1 s poll re-read two minutes of fills (12 Oct 2026).
        start = max(0,int(previous.get('cursor',end-86400))-POLL_OVERLAP_S)
        added = 0
        complete = False
        newest = previous.get('last_event_at')
        oldest = None
        from .data_api import fetch_rows
        cursor = None
        # v2 pages by cursor and has no 10,000-row offset wall. Twenty pages
        # of 500 cover a busy seed for a day; more waits for the next poll.
        for page in range(20):
            rows, cursor = fetch_rows(self.fetch, 'activity', user=wallet, start=start, end=end, limit=500,
                                      sortBy='TIMESTAMP', sortDirection='DESC', cursor=cursor)
            for row in rows:
                ts = row.get('timestamp') if isinstance(row, dict) else None
                if isinstance(ts, (int, float)) and (newest is None or ts > newest):
                    newest = ts
                if isinstance(ts, (int, float)) and (oldest is None or ts < oldest):
                    oldest = ts
            added += self.ingest(wallet,rows,time.time())
            if not cursor:
                complete=True
                break
        count = int(previous.get('unique_fingerprints') or 0) + added
        # 11 Oct 2026: 38 busy wallets never finished twenty pages, kept their
        # cursor 265 hours back and fetched 10,000 rows on every poll (most of
        # the qualifier's 200-350% CPU). The pages run newest first, so after
        # one pass the cursor moves to now; the older gap is recorded.
        gap = None if complete else {'before': oldest, 'since': start}
        status = 'POLL_OK' if complete else 'INCOMPLETE_PAGE_LIMIT'
        # A status write per poll of every wallet was most of the qualifier's
        # writes. It is written when something changed, or every 30 s so the
        # freshness checks (120 s) still see it.
        last = self.__dict__.setdefault('_status_written', {}).get(wallet)
        if not added and last and last[1]==status and time.time()-last[0]<STATUS_EVERY_S:
            return
        self._status_written[wallet] = (time.time(), status)
        self.store.set(key,dict(wallet=wallet,status=status,
            checked_at=time.time(),last_event_at=newest,unique_fingerprints=count,new_rows=added,
            cursor=end, history_gap=gap or previous.get('history_gap'),
            source='DATA_API_V2_INDEXED_ONCHAIN',poll_seconds=1,history_complete=False,
            identity_limitation='No log index; identical fills may collapse. Not a PnL ledger.',error=None))

    async def poll(self, wallet):
        key = 'wallet_observer:'+wallet
        previous = self.store.get(key,{})
        try:
            await asyncio.to_thread(self._poll_sync, wallet, previous)
        except Exception as error:
            self.store.set(key,{**previous,'wallet':wallet,'status':'ERROR','checked_at':time.time(),
                'error':str(error)[:300],'history_complete':False})

    def poll_every(self,wallet):
        """Seconds between polls. 11 Oct 2026: ~120 wallets every second kept the
        qualifier process at 200-350% CPU. Copied wallets and Mitch's keep 1 s
        (the fast lane already has their fills in ~0.4 s); paused ones, whose
        results decide a return, 5 s; observed ones 15 s."""
        from .mitch_copy import WALLETS as MITCH
        # Their buys come on the fast lane (~0.3 s); this poll is the backup
        # for public-list rows and sells.
        if wallet in MITCH:
            return COPY_POLL_S
        state=((self.store.get('wallet_roster') or {}).get('wallets') or {}).get(wallet,{}).get('state')
        if state in ('paper_test','paper_active'):
            return COPY_POLL_S
        # 11 Oct 2026 night: the fan kept Damian awake; 5/15 s still cost
        # 3 cores. Paused 15 s, observed 60 s (no copies come from either).
        return 15 if state=='paused' else 60

    async def run_wallet(self,wallet):
        failures=0
        while True:
            started=time.monotonic()
            await self.poll(wallet)
            status=await asyncio.to_thread(self.store.get, 'wallet_observer:'+wallet, {})
            failures=failures+1 if status.get('status')=='ERROR' else 0
            every=await asyncio.to_thread(self.poll_every, wallet)
            interval=min(60,2**min(failures,6)) if failures else every
            await asyncio.sleep(max(.1,interval-(time.monotonic()-started)))

    async def run(self):
        active = set()
        tasks = {}
        while True:
            current = set(get_active_wallets(self.store))
            # Start tasks for new wallets
            for w in current - active:
                tasks[w] = asyncio.create_task(self.run_wallet(w))
            active = current
            # Check every 60s for new wallets from discovery
            await asyncio.sleep(60)
