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

# Seen operating real seed fills. Informational only: the relayer address
# rotates, so matching must never depend on this set.
EXCHANGE_OPERATORS = {
    '0x4bfb41d5b3570defd03c39a9a4d8de6bd8b8982e',
    '0xc5d563a36ae78145c45a50134d48a1215220f80a',
    '0xe111180000d2663c0091e4f400237545b87b996b',
}
ZERO_ADDRESS = '0x' + '0' * 40

POLL_TIMEOUT = 60
POLL_INTERVAL = 0.5
# A seed can fill ten times inside one block. Off-market events now return at
# once, so the queue only holds short book lookups.
MAX_PENDING_TASKS = 30


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
    """Classify on who receives or sends the token.

    The operator is not a gate. Polymarket routes fills through rotating
    relayer addresses, so an allowlist silently dropped every seed fill.
    ChainBridge gates on the open market window instead.
    """
    if event['to'] in wallets_lower and event['from'] != event['to']:
        return event['to'], 'BUY'
    if event['from'] in wallets_lower and event['from'] != ZERO_ADDRESS:
        return event['from'], 'SELL'
    return None, None


def _row_key(source_row):
    """Dedup by trade identity, not price. Chain can insert before Data API."""
    fields = {k: source_row.get(k) for k in (
        'transactionHash', 'type', 'asset', 'side')}
    return hashlib.sha256(json.dumps(fields, sort_keys=True, allow_nan=False).encode()).hexdigest()


class ChainMonitor:
    """Non-blocking WebSocket monitor with bounded task queue."""

    def __init__(self, wss_url, wallets, on_event, clock=time.time):
        self.urls = [wss_url] if isinstance(wss_url, str) else [u for u in wss_url if u]
        if not self.urls:
            self.urls = ['wss://rpc-polygon.blockmachine.io']
        self.wss_url = self.urls[0]
        self._url_i = 0
        self._backoff = 1
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
        return {'mode': 'CHAIN_FAST', 'connected': self.connected_at is not None,
                'last_block': self.last_block, 'events_seen': self.events_seen,
                'events_matched': self.events_matched, 'errors': self.errors,
                'events_dropped': self.events_dropped, 'pending_tasks': len(self._tasks),
                'wss_host': self.wss_url.split('://',1)[-1].split('/',1)[0]}

    def update_wallets(self, new_set):
        """Update the set of monitored wallets at runtime."""
        self.wallets = {w.lower() for w in new_set}

    async def run(self):
        import websockets
        while True:
            self.connected_at = None
            self.wss_url = self.urls[self._url_i % len(self.urls)]
            try:
                async with websockets.connect(self.wss_url, open_timeout=8, close_timeout=3,
                                               max_size=5_000_000, ping_interval=20, ping_timeout=10) as ws:
                    self.connected_at = self.clock()
                    self._backoff = 1
                    LOG.info('chain monitor connected %s', self.wss_url.split('://',1)[-1].split('/',1)[0])
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
                self._url_i += 1
                LOG.warning('chain disconnected: %s', str(e)[:200])
                await asyncio.sleep(self._backoff)
                from .feed_watchdog import next_backoff
                self._backoff = next_backoff(self._backoff)

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
        self.off_market = 0
        self._windows = []
        self._windows_at = 0

    def _current_windows(self):
        now = self.clock()
        if now - self._windows_at < 15 and self._windows:
            return self._windows
        found = []
        for asset in ('btc', 'eth'):
            for interval, dur in (('5m', 300), ('15m', 900)):
                start = int(now) // dur * dur
                slug = f'{asset}-updown-{interval}-{start}'
                try:
                    raw = self.fetch(f'https://gamma-api.polymarket.com/markets/slug/{slug}')
                except Exception:
                    continue
                if not isinstance(raw, dict):
                    continue
                tokens = raw.get('clobTokenIds')
                if isinstance(tokens, str):
                    try:
                        tokens = json.loads(tokens)
                    except json.JSONDecodeError:
                        continue
                if not tokens:
                    continue
                found.append({'slug': slug, 'conditionId': raw.get('conditionId'),
                              'tokens': {str(t) for t in tokens}})
        if found:
            self._windows = found
            self._windows_at = now
            return found
        return self._windows  # keep the last good set through a gamma hiccup

    def _window_for(self, token):
        if not token:
            return None
        return next((m for m in self._current_windows() if token in m['tokens']), None)

    def _insert(self, wallet, source_row, detected_at, label):
        now = self.clock()
        ts = float(source_row.get('timestamp', now))
        key = _row_key(source_row)
        source_row['_detected_at'] = detected_at
        with self.store.connect() as db:
            cur = db.execute('INSERT OR IGNORE INTO wallet_activity VALUES (?,?,?,?,?)',
                             (wallet, key, now, ts, json.dumps(source_row, allow_nan=False)))
            if cur.rowcount:
                self.bridged += 1
                LOG.info('%s: %s %s @ %s', label, source_row.get('side', '?'),
                         wallet[-8:], source_row.get('price'))
                ready = getattr(self.store, 'wallet_activity_ready', None)
                if ready is not None and hasattr(ready, 'set'):
                    ready.set()
                return True
        return False

    def _fast_row(self, event, meta):
        token = str(event.get('token_id') or '')
        try:
            book = self.fetch('https://clob.polymarket.com/book?token_id=' + urllib.parse.quote(token, safe=''))
        except Exception:
            return None
        if not isinstance(book, dict):
            return None
        asks = book.get('asks') or []
        if not asks:
            return None
        try:
            price = min(float(a['price']) for a in asks if isinstance(a, dict) and a.get('price') is not None)
        except ValueError:
            return None
        detected_at = event.get('detected_at', self.clock())
        return {
            'transactionHash': event['tx_hash'],
            'type': 'TRADE',
            'side': event['side'],
            'proxyWallet': event['wallet'],
            'timestamp': detected_at,
            'slug': meta['slug'],
            'conditionId': meta['conditionId'],
            'asset': token,
            'price': price,
            'size': event.get('value', 0) / 1e6,
            '_source': 'chain_fast',
        }

    async def on_event(self, event):
        wallet = event['wallet']
        tx_hash = event.get('tx_hash', '')
        if not tx_hash:
            self.skipped += 1; return

        detected_at = event.get('detected_at', self.clock())

        # Only trades on an open 5m/15m window can be copied. Everything else
        # (hourly markets, share transfers) must not occupy the poll queue.
        meta = await asyncio.to_thread(self._window_for, str(event.get('token_id') or ''))
        if meta is None:
            self.off_market += 1
            return

        try:
            fast = await asyncio.to_thread(self._fast_row, event, meta)
            if fast and self._insert(wallet, fast, detected_at, 'chain-fast'):
                return
        except Exception as e:
            LOG.debug('fast path miss: %s', str(e)[:120])

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

        now = self.clock()
        for source_row in source_rows:
            source_row['_source'] = 'chain_accelerated'
            source_row['_chain_to_api_seconds'] = now - detected_at
            self._insert(wallet, source_row, detected_at, 'chain→api')

    def _poll_activity(self, wallet, since):
        start = max(0, int(since) - 30)
        end = int(self.clock()) + 5
        query = urllib.parse.urlencode(dict(user=wallet, start=start, end=end,
                                            limit=100, sortBy='TIMESTAMP', sortDirection='DESC'))
        return self.fetch(f'{DATA_API}/activity?{query}')

    def status(self):
        return {'bridged': self.bridged, 'skipped': self.skipped, 'timeouts': self.timeouts,
                'off_market': self.off_market}
