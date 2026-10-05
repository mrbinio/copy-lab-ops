"""Public, read-only activity polling; never signs or copies orders."""
import asyncio
import hashlib
import json
import math
import time
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
    return tuple(seen)


class WalletObserver:
    def __init__(self, store, fetch):
        self.store, self.fetch = store, fetch
        if not hasattr(store,"wallet_activity_ready"):store.wallet_activity_ready=asyncio.Event()
        with store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS wallet_activity (wallet TEXT, event_key TEXT, first_seen REAL, source_ts REAL, body TEXT, PRIMARY KEY(wallet,event_key))')
            db.execute('CREATE INDEX IF NOT EXISTS wallet_activity_seen ON wallet_activity(first_seen)')
        ensure_active_wallets_table(store)

    def ingest(self, wallet, rows, now):
        if not isinstance(rows, list): raise ValueError('activity response must be a list')
        inserted = 0
        with self.store.connect() as db:
            for row in rows:
                if not isinstance(row, dict): raise ValueError('invalid activity row')
                if str(row.get('proxyWallet','')).lower() != wallet: raise ValueError('wallet mismatch')
                ts = float(row['timestamp'])
                if not math.isfinite(ts) or not 0 < ts <= now+5: raise ValueError('invalid source timestamp')
                # API v1 has no log index. This fingerprint is NOT an execution ID.
                fields = {k:row.get(k) for k in ('transactionHash','type','asset','side')}
                if not fields['transactionHash']: raise ValueError('missing transaction hash')
                from .wallet_chain_monitor import _row_key
                key = _row_key(row)
                cur = db.execute('INSERT OR IGNORE INTO wallet_activity VALUES (?,?,?,?,?)',
                                 (wallet,key,now,ts,json.dumps(row,allow_nan=False)))
                inserted += cur.rowcount
        if inserted:self.store.wallet_activity_ready.set()
        return inserted

    def _poll_sync(self, wallet, previous):
        """Fetch and insert off the event loop.

        A page of 500 rows inserted on the loop froze the price feed and the
        chain socket long enough for both handshakes to time out.
        """
        key = 'wallet_observer:'+wallet
        end = int(time.time())
        start = max(0,int(previous.get('cursor',end-86400))-120)
        added = 0
        complete = False
        newest = previous.get('last_event_at')
        for page in range(4):
            query = urlencode(dict(user=wallet,start=start,end=end,limit=500,offset=page*500,sortBy='TIMESTAMP',sortDirection='DESC'))
            rows = self.fetch('https://data-api.polymarket.com/activity?'+query)
            for row in rows:
                ts = row.get('timestamp') if isinstance(row, dict) else None
                if isinstance(ts, (int, float)) and (newest is None or ts > newest):
                    newest = ts
            added += self.ingest(wallet,rows,time.time())
            if len(rows)<500:
                complete=True
                break
        count = int(previous.get('unique_fingerprints') or 0) + added
        self.store.set(key,dict(wallet=wallet,status='POLL_OK' if complete else 'INCOMPLETE_PAGE_LIMIT',
            checked_at=time.time(),last_event_at=newest,unique_fingerprints=count,new_rows=added,
            cursor=end if complete else previous.get('cursor',start+120),
            source='DATA_API_V1_INDEXED_ONCHAIN',poll_seconds=1,history_complete=False,
            identity_limitation='No log index; identical fills may collapse. Not a PnL ledger.',error=None))

    async def poll(self, wallet):
        key = 'wallet_observer:'+wallet
        previous = self.store.get(key,{})
        try:
            await asyncio.to_thread(self._poll_sync, wallet, previous)
        except Exception as error:
            self.store.set(key,{**previous,'wallet':wallet,'status':'ERROR','checked_at':time.time(),
                'error':str(error)[:300],'history_complete':False})

    async def run_wallet(self,wallet):
        failures=0
        while True:
            started=time.monotonic()
            await self.poll(wallet)
            status=self.store.get('wallet_observer:'+wallet,{})
            failures=failures+1 if status.get('status')=='ERROR' else 0
            interval=min(60,2**min(failures,6)) if failures else 1
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
