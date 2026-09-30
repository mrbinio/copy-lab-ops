"""On-chain Polygon monitor: detect trade (~2s) → CLOB book price → wallet_activity.

FAST-PATH ARCHITECTURE (like Mitch):
  1. Chain WebSocket detects TransferSingle on CTF Token contract (~2s block time)
  2. TokenResolver maps token_id → slug/conditionId/side via Gamma API (cached)
  3. Fetch CLOB orderbook for the token → get current ask price (~0.5s)
  4. Insert into wallet_activity with real book price → wallet_copy processes

  Total latency: ~3s from on-chain trade to wallet_activity entry.
  No dependency on Data API indexing (which adds 5-30s).

  Chain ──(2s)──► resolve token ──(cache)──► fetch CLOB book ──(0.5s)──► wallet_activity
                                                                              ↓
                                                                         wallet_copy

Requires: ALCHEMY_WSS environment variable with Polygon WebSocket endpoint.
REST WalletObserver continues as fallback; dedup by txHash prevents doubles.
"""
import asyncio
import hashlib
import json
import logging
import time
import urllib.parse
import urllib.request

LOG = logging.getLogger('btc-lab.chain')

CTF_TOKEN = '0x4D97DCd97eC945f40cF65F87097ACe5EA0476045'
TRANSFER_SINGLE_TOPIC = '0xc3d58168c5ae7397731d063d5bbf3d657854427343f4c083240f7aacaa2d0f62'
CLOB = 'https://clob.polymarket.com'

EXCHANGE_OPERATORS = {
    '0x4bfb41d5b3570defd03c39a9a4d8de6bd8b8982e',
    '0xc5d563a36ae78145c45a50134d48a1215220f80a',
}
ZERO_ADDRESS = '0x' + '0' * 40


def parse_transfer_single(log):
    """Parse ERC1155 TransferSingle from raw Polygon log.
    4 topics (sig, operator, from, to), 2 data words (token_id, value).
    """
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
            'contract': log.get('address', '').lower(),
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
    """BUY = wallet in 'to', SELL = wallet in 'from'. Exchange operator only."""
    if event['operator'] not in EXCHANGE_OPERATORS:
        return None, None
    if event['to'] in wallets_lower and event['from'] != event['to']:
        return event['to'], 'BUY'
    if event['from'] in wallets_lower and event['from'] != ZERO_ADDRESS:
        return event['from'], 'SELL'
    return None, None


def fetch_book_price(token_id, side, fetch):
    """Fetch current CLOB book and return best ask (for BUY) or best bid (for SELL)."""
    url = f'{CLOB}/book?token_id={urllib.parse.quote(str(token_id), safe="")}'
    raw = fetch(url)
    if side == 'BUY' and raw.get('asks'):
        return min(float(a['price']) for a in raw['asks'])
    if side == 'SELL' and raw.get('bids'):
        return max(float(b['price']) for b in raw['bids'])
    return None


class ChainMonitor:
    """WebSocket subscription to TransferSingle → fast-path wallet_activity insert."""

    def __init__(self, wss_url, wallets, on_event, clock=time.time):
        self.wss_url = wss_url
        self.wallets = {w.lower() for w in wallets}
        self.on_event = on_event
        self.clock = clock
        self.subscription_id = None
        self.last_block = 0
        self.events_seen = 0
        self.events_matched = 0
        self.errors = 0
        self.connected_at = None

    def status(self):
        return {
            'mode': 'FAST_PATH_CLOB_PRICE',
            'connected': self.connected_at is not None,
            'connected_at': self.connected_at,
            'last_block': self.last_block,
            'events_seen': self.events_seen,
            'events_matched': self.events_matched,
            'errors': self.errors,
            'subscription_id': self.subscription_id,
        }

    async def run(self):
        import websockets
        while True:
            self.connected_at = None
            self.subscription_id = None
            try:
                async with websockets.connect(self.wss_url, open_timeout=10, close_timeout=5,
                                               max_size=5_000_000, ping_interval=20, ping_timeout=10) as ws:
                    self.connected_at = self.clock()
                    LOG.info('chain monitor connected (fast-path mode)')
                    sub = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'eth_subscribe',
                                      'params': ['logs', {'address': CTF_TOKEN, 'topics': [TRANSFER_SINGLE_TOPIC]}]})
                    await ws.send(sub)
                    resp = json.loads(await ws.recv())
                    if 'result' in resp:
                        self.subscription_id = resp['result']
                    else:
                        LOG.warning('subscribe failed: %s', resp.get('error'))
                        await asyncio.sleep(5)
                        continue
                    async for message in ws:
                        if isinstance(message, bytes):
                            message = message.decode('utf-8')
                        try:
                            data = json.loads(message)
                        except json.JSONDecodeError:
                            continue
                        if data.get('method') != 'eth_subscription':
                            continue
                        result = data.get('params', {}).get('result')
                        if not isinstance(result, dict):
                            continue
                        event = parse_transfer_single(result)
                        if event is None or event.get('removed'):
                            continue
                        self.events_seen += 1
                        self.last_block = max(self.last_block, event['block_number'])
                        wallet, side = classify_transfer(event, self.wallets)
                        if wallet is None:
                            continue
                        self.events_matched += 1
                        event['wallet'] = wallet
                        event['side'] = side
                        event['detected_at'] = self.clock()
                        try:
                            await self.on_event(event)
                        except Exception as e:
                            LOG.warning('event handler: %s', str(e)[:200])
                            self.errors += 1
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.errors += 1
                self.connected_at = None
                LOG.warning('chain monitor disconnected: %s', str(e)[:200])
                await asyncio.sleep(5)


class ChainBridge:
    """Resolve token, fetch CLOB book price, insert into wallet_activity.

    Fast path: ~3s total (chain 2s + resolve cache + book fetch 0.5s).
    Dedup with REST observer by checking txHash before insert.
    """

    def __init__(self, store, fetch, clock=time.time):
        from .token_resolver import TokenResolver
        self.store = store
        self.fetch = fetch
        self.clock = clock
        self.resolver = TokenResolver(store, fetch, clock)
        self.bridged = 0
        self.skipped = 0
        self.unresolved = 0
        self.no_price = 0

    async def on_event(self, event):
        """Chain monitor callback: resolve → book price → wallet_activity."""
        wallet = event['wallet']
        side = event['side']
        tx_hash = event.get('tx_hash', '')
        token_id = event.get('token_id')

        if not token_id or not tx_hash:
            self.skipped += 1
            return

        # 1. Resolve token_id → slug, conditionId
        info = await self.resolver.resolve(token_id)
        if info is None:
            self.unresolved += 1
            return

        # 2. Fetch CLOB book price (the key difference from hybrid approach)
        try:
            price = await asyncio.to_thread(fetch_book_price, str(token_id), side, self.fetch)
        except Exception as e:
            LOG.warning('book fetch failed for %s: %s', token_id, str(e)[:100])
            price = None

        if price is None or not 0 < price < 1:
            self.no_price += 1
            self.store.record('chain_no_price', {
                'wallet': wallet, 'tx': tx_hash, 'token': str(token_id),
                'side': side, 'slug': info['slug']}, self.clock())
            return

        now = self.clock()

        # 3. Build wallet_activity-compatible body with REAL book price
        body = {
            'transactionHash': tx_hash,
            'type': 'TRADE',
            'side': side,
            'proxyWallet': wallet,
            'timestamp': now,
            'slug': info['slug'],
            'conditionId': info['conditionId'],
            'asset': info['asset'],
            'price': price,  # from CLOB book, not Data API
            'size': event.get('value', 0) / 1e6,
            'usdcSize': price * event.get('value', 0) / 1e6,
            'outcomeIndex': 0 if info['side'] == 'Up' else 1,
            '_source': 'chain_monitor',
            '_block_number': event.get('block_number'),
            '_log_index': event.get('log_index'),
            '_detected_at': event.get('detected_at'),
            '_book_price': price,
        }

        # 4. Dedup: check txHash in existing wallet_activity
        key = hashlib.sha256(f"chain:{tx_hash}:{event.get('log_index', 0)}".encode()).hexdigest()

        with self.store.connect() as db:
            # Check if REST observer already has this txHash
            for pattern in (f'%"transactionHash": "{tx_hash}"%', f'%"transactionHash":"{tx_hash}"%'):
                if db.execute("SELECT 1 FROM wallet_activity WHERE wallet=? AND body LIKE ?",
                              (wallet, pattern)).fetchone():
                    self.skipped += 1
                    return
            cur = db.execute('INSERT OR IGNORE INTO wallet_activity VALUES (?,?,?,?,?)',
                             (wallet, key, now, now, json.dumps(body, allow_nan=False)))
            if cur.rowcount:
                self.bridged += 1
                LOG.info('chain fast-path: %s %s %s @ %.2f (%s)',
                         side, wallet[-8:], info['slug'], price, tx_hash[:12])
                ready = getattr(self.store, 'wallet_activity_ready', None)
                if ready is not None and hasattr(ready, 'set'):
                    ready.set()
            else:
                self.skipped += 1

    def status(self):
        return {'bridged': self.bridged, 'skipped': self.skipped,
                'unresolved': self.unresolved, 'no_price': self.no_price}
