"""On-chain detection + aggressive Data API poll for source execution price.

Non-blocking, bounded task queue, per-row dedup (not per-txHash).
"""
import asyncio
import hashlib
import json
import logging
import time
import urllib.parse

LOG = logging.getLogger('btc-lab.chain')

CTF_TOKEN = '0x4D97DCd97eC945f40cF65F87097ACe5EA0476045'
TRANSFER_SINGLE_TOPIC = '0xc3d58168c5ae7397731d063d5bbf3d657854427343f4c083240f7aacaa2d0f62'
DATA_API = 'https://data-api.polymarket.com'

EXCHANGE_OPERATORS = {
    '0x4bfb41d5b3570defd03c39a9a4d8de6bd8b8982e',
    '0xc5d563a36ae78145c45a50134d48a1215220f80a',
}
ZERO_ADDRESS = '0x' + '0' * 40

POLL_TIMEOUT = 60
POLL_INTERVAL = 2
MAX_PENDING_TASKS = 10


def parse_transfer_single(log):
    topics = log.get('topics', [])
    data = log.get('data', '0x')
    if len(topics) != 4 or topics[0] != TRANSFER_SINGLE_TOPIC:
        return None
    if len(data) < 2 + 64 * 2:
        return None
    try:
        d = data[2:]
        return {
            'type': 'TRANSFER_SINGLE',
            'block_number': int(log.get('blockNumber', '0x0'), 16),
            'tx_hash': log.get('transactionHash'),
            'log_index': int(log.get('logIndex', '0x0'), 16),
            'removed': log.get('removed', False),
            'operator': '0x' + topics[1][26:].lower(),
            'from': '0x' + topics[2][26:].lower(),
            'to': '0x' + topics[3][26:].lower(),
            'token_id': int(d[0:64], 16),
            'value': int(d[64:128], 16),
        }
    except (ValueError, IndexError):
        return None


def classify_transfer(event, wallets_lower):
    if event['operator'] not in EXCHANGE_OPERATORS:
        return None, None
    if event['to'] in wallets_lower and event['from'] != event['to']:
        return event['to'], 'BUY'
    if event['from'] in wallets_lower and event['from'] != ZERO_ADDRESS:
        return event['from'], 'SELL'
    return None, None


def _row_key(source_row):
    """Same key format as REST wallet_observer — true dedup."""
    fields = {k: source_row.get(k) for k in (
        'transactionHash', 'type', 'asset', 'side', 'size', 'usdcSize',
        'price', 'timestamp', 'conditionId', 'outcomeIndex')}
    return hashlib.sha256(json.dumps(fields, sort_keys=True, allow_nan=False).encode()).hexdigest()


class ChainMonitor:
    """Non-blocking WebSocket monitor with bounded task queue."""

    def __init__(self, wss_url, wallets, on_event, clock=time.time):
        self.wss_url = wss_url
        self.wallets = {w.lower() for w in wallets}
        self.on_event = on_event
        self.clock = clock
        self.events_seen = 0
        self.events_matched = 0
        self.events_dropped = 0
        self.errors = 0
        self.connected_at = None
        self.last_block = 0
        self._tasks = set()

    def status(self):
        return {'mode': 'CHAIN_DETECT_REST_PRICE', 'connected': self.connected_at is not None,
                'last_block': self.last_block, 'events_seen': self.events_seen,
                'events_matched': self.events_matched, 'errors': self.errors,
                'events_dropped': self.events_dropped, 'pending_tasks': len(self._tasks)}

    def update_wallets(self, new_set):
        """Update the set of monitored wallets at runtime."""
        self.wallets = {w.lower() for w in new_set}

    async def run(self):
        import websockets
        while True:
            self.connected_at = None
            try:
                async with websockets.connect(self.wss_url, open_timeout=10, close_timeout=5,
                                               max_size=5_000_000, ping_interval=20, ping_timeout=10) as ws:
                    self.connected_at = self.clock()
                    LOG.info('chain monitor connected')
                    sub = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'eth_subscribe',
                                      'params': ['logs', {'address': CTF_TOKEN, 'topics': [TRANSFER_SINGLE_TOPIC]}]})
                    await ws.send(sub)
                    resp = json.loads(await ws.recv())
                    if 'result' not in resp:
                        await asyncio.sleep(5); continue
                    async for message in ws:
                        if isinstance(message, bytes): message = message.decode()
                        try: data = json.loads(message)
                        except json.JSONDecodeError: continue
                        if data.get('method') != 'eth_subscription': continue
                        result = data.get('params', {}).get('result')
                        if not isinstance(result, dict): continue
                        event = parse_transfer_single(result)
                        if event is None or event.get('removed'): continue
                        self.events_seen += 1
                        self.last_block = max(self.last_block, event['block_number'])
                        wallet, side = classify_transfer(event, self.wallets)
                        if wallet is None: continue
                        self.events_matched += 1
                        event.update(wallet=wallet, side=side, detected_at=self.clock())
                        # Bounded queue: drop if too many pending
                        if len(self._tasks) >= MAX_PENDING_TASKS:
                            self.events_dropped += 1
                            LOG.warning('queue full (%d), dropping %s', len(self._tasks), event['tx_hash'][:12])
                            continue
                        task = asyncio.create_task(self._safe_handle(event))
                        self._tasks.add(task)
                        task.add_done_callback(self._tasks.discard)
            except asyncio.CancelledError:
                for t in self._tasks: t.cancel()
                raise
            except Exception as e:
                self.errors += 1; self.connected_at = None
                LOG.warning('chain disconnected: %s', str(e)[:200])
                await asyncio.sleep(5)

    async def _safe_handle(self, event):
        try:
            await self.on_event(event)
        except Exception as e:
            self.errors += 1
            LOG.warning('handler: %s', str(e)[:200])


class ChainBridge:
    """Poll Data API for confirmed source price. Per-row dedup, not per-txHash.

    Does NOT skip entire txHash — always polls API and inserts any new rows.
    Dedup is per individual fill (same key as REST observer).
    """

    def __init__(self, store, fetch, clock=time.time, sleep=asyncio.sleep):
        self.store = store
        self.fetch = fetch
        self.clock = clock
        self.sleep = sleep
        self.bridged = 0
        self.skipped = 0
        self.timeouts = 0

    async def on_event(self, event):
        wallet = event['wallet']
        tx_hash = event.get('tx_hash', '')
        if not tx_hash:
            self.skipped += 1; return

        detected_at = event.get('detected_at', self.clock())
        deadline = detected_at + POLL_TIMEOUT
        source_rows = None

        # Poll until trade appears in Data API
        while self.clock() < deadline:
            try:
                api_rows = await asyncio.to_thread(self._poll_activity, wallet, detected_at)
                source_rows = [r for r in (api_rows or [])
                               if isinstance(r, dict) and r.get('transactionHash') == tx_hash]
                if source_rows:
                    break
            except Exception as e:
                LOG.debug('poll retry: %s', str(e)[:100])
            await self.sleep(POLL_INTERVAL)

        if not source_rows:
            self.timeouts += 1
            self.store.record('chain_timeout', {'wallet': wallet, 'tx': tx_hash,
                              'side': event['side'], 'block': event.get('block_number')})
            return

        # Insert each fill — dedup per individual row, not per txHash
        now = self.clock()
        for source_row in source_rows:
            ts = float(source_row.get('timestamp', now))
            key = _row_key(source_row)
            source_row['_source'] = 'chain_accelerated'
            source_row['_detected_at'] = detected_at
            source_row['_chain_to_api_seconds'] = now - detected_at

            with self.store.connect() as db:
                cur = db.execute('INSERT OR IGNORE INTO wallet_activity VALUES (?,?,?,?,?)',
                                 (wallet, key, now, ts, json.dumps(source_row, allow_nan=False)))
                if cur.rowcount:
                    self.bridged += 1
                    LOG.info('chain→api: %s %s @ %s (%.1fs)', source_row.get('side', '?'),
                             wallet[-8:], source_row.get('price'), now - detected_at)
                    ready = getattr(self.store, 'wallet_activity_ready', None)
                    if ready is not None and hasattr(ready, 'set'):
                        ready.set()

    def _poll_activity(self, wallet, since):
        start = max(0, int(since) - 30)
        end = int(self.clock()) + 5
        query = urllib.parse.urlencode(dict(user=wallet, start=start, end=end,
                                            limit=100, sortBy='TIMESTAMP', sortDirection='DESC'))
        return self.fetch(f'{DATA_API}/activity?{query}')

    def status(self):
        return {'bridged': self.bridged, 'skipped': self.skipped, 'timeouts': self.timeouts}
