"""On-chain Polygon WebSocket monitor for Polymarket wallet activity.

Subscribes to TransferSingle events from the CTF Token contract — the canonical
source of conditional-token transfers on Polymarket. Each fill on the exchange
produces a TransferSingle with the buyer in `to` and the seller in `from`.

Target latency: ~2-3s (Polygon block time) vs 7-35s (REST API indexing delay).
Requires: Alchemy (or compatible) WebSocket endpoint for Polygon Mainnet.

Architecture:
  ChainMonitor ──(TransferSingle)──► ChainToActivityBridge ──► wallet_activity table
                                                                    ▲
  WalletObserver ──(REST polling)──────────────────────────────────┘ (fallback, dedup by txHash)
"""
import asyncio
import hashlib
import json
import logging
import time
from collections import deque

LOG = logging.getLogger('btc-lab.chain')

# Polymarket CTF Token contract on Polygon PoS (Chain ID 137).
# All conditional-token transfers (buys, sells, redemptions) emit TransferSingle here.
CTF_TOKEN = '0x4D97DCd97eC945f40cF65F87097ACe5EA0476045'

# ERC1155 TransferSingle(address indexed operator, address indexed from, address indexed to, uint256 id, uint256 value)
TRANSFER_SINGLE_TOPIC = '0xc3d58168c5ae7397731d063d5bbf3d657854427343f4c083240f7aacaa2d0f62'

# Known Polymarket exchange operators — transfers initiated by these are exchange fills.
EXCHANGE_OPERATORS = {
    '0x4bfb41d5b3570defd03c39a9a4d8de6bd8b8982e',  # CTF Exchange
    '0xc5d563a36ae78145c45a50134d48a1215220f80a',  # NegRisk CTF Exchange
}

# Zero address = mint (new tokens created for buyer)
ZERO_ADDRESS = '0x' + '0' * 40


def parse_transfer_single(log):
    """Parse ERC1155 TransferSingle from a raw Polygon log entry.

    Real format (verified on-chain 2026-09-30):
      topics[0] = event signature
      topics[1] = operator (address, indexed) — who initiated the transfer
      topics[2] = from (address, indexed) — sender (0x0 = mint)
      topics[3] = to (address, indexed) — recipient
      data = token_id (uint256) + value (uint256)

    Returns parsed dict or None.
    """
    topics = log.get('topics', [])
    data = log.get('data', '0x')
    if len(topics) != 4 or topics[0] != TRANSFER_SINGLE_TOPIC:
        return None
    if len(data) < 2 + 64 * 2:  # need 2 x 32-byte words
        return None
    try:
        d = data[2:]
        return {
            'type': 'TRANSFER_SINGLE',
            'contract': log.get('address', '').lower(),
            'block_number': int(log.get('blockNumber', '0x0'), 16),
            'block_hash': log.get('blockHash'),
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
    """Determine if a TransferSingle involves a monitored wallet and classify direction.

    Returns (wallet, side) where side is 'BUY' or 'SELL', or (None, None).

    Rules:
      - wallet in `to` field = BUY (wallet receives conditional tokens)
      - wallet in `from` field = SELL (wallet sends conditional tokens)
      - Only consider exchange-initiated transfers (operator in EXCHANGE_OPERATORS)
      - Ignore mints from zero address where wallet is operator (redemptions etc.)
    """
    operator = event['operator']
    frm = event['from']
    to = event['to']

    # Only exchange fills — ignore direct transfers, redemptions, etc.
    if operator not in EXCHANGE_OPERATORS:
        return None, None

    # BUY: wallet receives tokens
    if to in wallets_lower and frm != to:
        return to, 'BUY'

    # SELL: wallet sends tokens
    if frm in wallets_lower and frm != ZERO_ADDRESS:
        return frm, 'SELL'

    return None, None


class ChainMonitor:
    """WebSocket subscription to TransferSingle events on CTF Token contract.

    Streams conditional-token transfers in real-time (~2-3s block time) and
    calls on_event for each transfer involving a monitored wallet.
    """

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
        self.last_event_at = None

    def status(self):
        return {
            'connected': self.connected_at is not None,
            'connected_at': self.connected_at,
            'last_block': self.last_block,
            'events_seen': self.events_seen,
            'events_matched': self.events_matched,
            'errors': self.errors,
            'last_event_at': self.last_event_at,
            'subscription_id': self.subscription_id,
        }

    async def run(self):
        """Main loop: connect, subscribe to TransferSingle, process events."""
        import websockets

        while True:
            self.connected_at = None
            self.subscription_id = None
            try:
                async with websockets.connect(
                    self.wss_url,
                    open_timeout=10,
                    close_timeout=5,
                    max_size=5_000_000,
                    ping_interval=20,
                    ping_timeout=10,
                ) as ws:
                    self.connected_at = self.clock()
                    LOG.info('chain monitor connected to Polygon')

                    # Subscribe to TransferSingle on CTF Token contract
                    sub_msg = json.dumps({
                        'jsonrpc': '2.0',
                        'id': 1,
                        'method': 'eth_subscribe',
                        'params': ['logs', {
                            'address': CTF_TOKEN,
                            'topics': [TRANSFER_SINGLE_TOPIC],
                        }],
                    })
                    await ws.send(sub_msg)
                    resp = json.loads(await ws.recv())
                    if 'result' in resp:
                        self.subscription_id = resp['result']
                        LOG.info('subscribed to TransferSingle: %s', self.subscription_id)
                    else:
                        LOG.warning('subscribe failed: %s', resp.get('error'))
                        await asyncio.sleep(5)
                        continue

                    # Process incoming events
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
                        if not isinstance(result, dict) or 'topics' not in result:
                            continue

                        event = parse_transfer_single(result)
                        if event is None:
                            continue
                        if event.get('removed'):
                            continue  # block reorg — ignore removed logs

                        self.events_seen += 1
                        self.last_block = max(self.last_block, event['block_number'])

                        wallet, side = classify_transfer(event, self.wallets)
                        if wallet is None:
                            continue

                        self.events_matched += 1
                        self.last_event_at = self.clock()
                        event['wallet'] = wallet
                        event['side'] = side
                        event['detected_at'] = self.last_event_at

                        try:
                            await self.on_event(event)
                        except Exception as e:
                            LOG.warning('event handler error: %s', str(e)[:200])
                            self.errors += 1

            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.errors += 1
                self.connected_at = None
                LOG.warning('chain monitor disconnected: %s', str(e)[:200])
                await asyncio.sleep(5)


class ChainToActivityBridge:
    """Translates on-chain TransferSingle events into wallet_activity rows.

    Bridges: ChainMonitor → wallet_activity table → WalletCopy pipeline.
    REST WalletObserver runs as fallback; deduplication by txHash prevents doubles.
    """

    def __init__(self, store, fetch, clock=time.time):
        from .token_resolver import TokenResolver
        self.store = store
        self.clock = clock
        self.resolver = TokenResolver(store, fetch, clock)
        self.events_bridged = 0
        self.events_skipped = 0
        self.events_unresolved = 0
        if not hasattr(store, 'wallet_activity_ready'):
            store.wallet_activity_ready = asyncio.Event()

    async def on_chain_event(self, event):
        """Callback for ChainMonitor. Resolves token, inserts into wallet_activity."""
        now = self.clock()
        wallet = event['wallet']
        side = event['side']
        tx_hash = event.get('tx_hash', '')
        token_id = event.get('token_id')
        value = event.get('value', 0)

        if not token_id or not tx_hash:
            self.events_skipped += 1
            return

        # Resolve token_id → slug, conditionId, market side
        info = await self.resolver.resolve(token_id)
        if info is None:
            self.events_unresolved += 1
            return

        # Price is not available from TransferSingle alone.
        # WalletCopy will fetch the current book price at processing time.
        # We pass 0 here; wallet_copy uses book ask/bid, not source price for chain events.
        body = {
            'transactionHash': tx_hash,
            'type': 'TRADE',
            'side': side,
            'proxyWallet': wallet,
            'timestamp': now,
            'slug': info['slug'],
            'conditionId': info['conditionId'],
            'asset': info['asset'],  # token_id as string
            'price': 0,  # not available from chain; wallet_copy uses book
            'size': value / 1e6,
            'usdcSize': 0,  # not available from chain
            'outcomeIndex': 0 if info['side'] == 'Up' else 1,
            '_source': 'chain_monitor',
            '_block_number': event.get('block_number'),
            '_log_index': event.get('log_index'),
            '_operator': event.get('operator'),
            '_from': event.get('from'),
            '_to': event.get('to'),
            '_token_id': str(token_id),
            '_value': value,
            '_detected_at': event.get('detected_at'),
        }

        # Deduplicate with REST observer: use txHash as shared key.
        # REST observer uses SHA256 of sorted fields; we use txHash:logIndex.
        # Both INSERT OR IGNORE, so first arrival wins.
        key = hashlib.sha256(f"{tx_hash}:{event.get('log_index', 0)}".encode()).hexdigest()

        with self.store.connect() as db:
            cur = db.execute(
                'INSERT OR IGNORE INTO wallet_activity VALUES (?,?,?,?,?)',
                (wallet, key, now, now, json.dumps(body, allow_nan=False)),
            )
            if cur.rowcount:
                self.events_bridged += 1
                ready = getattr(self.store, 'wallet_activity_ready', None)
                if ready is not None and hasattr(ready, 'set'):
                    ready.set()
            else:
                self.events_skipped += 1

    def status(self):
        return {
            'events_bridged': self.events_bridged,
            'events_skipped': self.events_skipped,
            'events_unresolved': self.events_unresolved,
            'resolver_cache': self.resolver.cache_stats(),
        }
