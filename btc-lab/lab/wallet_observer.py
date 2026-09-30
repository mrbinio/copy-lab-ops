"""Public, read-only activity polling; never signs or copies orders."""
import asyncio
import hashlib
import json
import logging
import math
import time
from urllib.parse import urlencode

LOG = logging.getLogger('btc-lab.observer')

WALLETS = (
 '0x16217458b59b3458149918058754cd234096b159',
 '0xeda9247a2b3c99a9e0bf46cdac6e1974365cf589',
 '0x943cea746e701823b6902a6f4eaeed58207e77c2',
)

class WalletObserver:
    def __init__(self, store, fetch):
        self.store, self.fetch = store, fetch
        if not hasattr(store,"wallet_activity_ready"):store.wallet_activity_ready=asyncio.Event()
        self.chain_alerts = {}  # wallet → asyncio.Event, set by chain monitor
        with store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS wallet_activity (wallet TEXT, event_key TEXT, first_seen REAL, source_ts REAL, body TEXT, PRIMARY KEY(wallet,event_key))')

    def trigger_poll(self, wallet):
        """Called by chain monitor when on-chain trade detected. Wakes up REST poll immediately."""
        alert = self.chain_alerts.get(wallet.lower())
        if alert is not None:
            alert.set()

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
                fields = {k:row.get(k) for k in ('transactionHash','type','asset','side','size','usdcSize','price','timestamp','conditionId','outcomeIndex')}
                if not fields['transactionHash']: raise ValueError('missing transaction hash')
                body = json.dumps(fields,sort_keys=True,allow_nan=False)
                key = hashlib.sha256(body.encode()).hexdigest()
                cur = db.execute('INSERT OR IGNORE INTO wallet_activity VALUES (?,?,?,?,?)',
                                 (wallet,key,now,ts,json.dumps(row,allow_nan=False)))
                inserted += cur.rowcount
        if inserted:self.store.wallet_activity_ready.set()
        return inserted

    async def poll(self, wallet):
        key = 'wallet_observer:'+wallet
        previous = self.store.get(key,{})
        end = int(time.time())
        start = max(0,int(previous.get('cursor',end-86400))-120)
        added = 0
        try:
            complete = False
            for page in range(4):
                query = urlencode(dict(user=wallet,start=start,end=end,limit=500,offset=page*500,sortBy='TIMESTAMP',sortDirection='DESC'))
                rows = await asyncio.to_thread(self.fetch,'https://data-api.polymarket.com/activity?'+query)
                added += self.ingest(wallet,rows,time.time())
                if len(rows)<500:
                    complete=True
                    break
            with self.store.connect() as db:
                count,last = db.execute('SELECT COUNT(*),MAX(source_ts) FROM wallet_activity WHERE wallet=?',(wallet,)).fetchone()
            self.store.set(key,dict(wallet=wallet,status='POLL_OK' if complete else 'INCOMPLETE_PAGE_LIMIT',
                checked_at=time.time(),last_event_at=last,unique_fingerprints=count,new_rows=added,
                cursor=end if complete else previous.get('cursor',start+120),
                source='DATA_API_V1_INDEXED_ONCHAIN',poll_seconds=1,history_complete=False,
                identity_limitation='No log index; identical fills may collapse. Not a PnL ledger.',error=None))
        except Exception as error:
            self.store.set(key,{**previous,'wallet':wallet,'status':'ERROR','checked_at':time.time(),
                'error':str(error)[:300],'history_complete':False})

    async def run_wallet(self,wallet):
        failures=0
        if not hasattr(self,'chain_alerts'):self.chain_alerts={}
        alert=asyncio.Event()
        self.chain_alerts[wallet]=alert
        while True:
            started=time.monotonic()
            await self.poll(wallet)
            status=self.store.get('wallet_observer:'+wallet,{})
            failures=failures+1 if status.get('status')=='ERROR' else 0
            interval=min(60,2**min(failures,6)) if failures else 1
            # Chain monitor can set alert to request immediate re-poll.
            # We check after a short sleep instead of waiting full interval.
            step=min(interval,0.5) if alert.is_set() else interval
            alert.clear()
            await asyncio.sleep(max(.1,step-(time.monotonic()-started)))

    async def run(self):
        await asyncio.gather(*(self.run_wallet(w) for w in WALLETS))
