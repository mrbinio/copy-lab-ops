"""On-chain Polygon WebSocket monitor for Polymarket wallet activity.

Replaces REST polling of indexed Data API with direct blockchain event streaming.
Target latency: ~2-3s (Polygon block time) vs 7-35s (REST API indexing delay).

Requires: Alchemy (or compatible) WebSocket endpoint for Polygon Mainnet.
"""
import asyncio
import json
import logging
import time
from collections import deque

LOG = logging.getLogger('btc-lab.chain')

# Polymarket contracts on Polygon PoS (Chain ID 137)
# Both exchanges emit OrderFilled events when trades execute.
CTF_EXCHANGE = '0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E'
NEG_RISK_CTF_EXCHANGE = '0xC5d563A36AE78145C45a50134d48A1215220f80a'

# Event signature: OrderFilled(bytes32 orderHash, address maker, address taker,
#   uint256 makerAssetId, uint256 takerAssetId, uint256 makerAmountFilled,
#   uint256 takerAmountFilled, uint256 fee)
# keccak256 of the signature:
ORDER_FILLED_TOPIC = '0xd0a08e8c493f9c94f29311604c9de1d4e1f89571a99b3e4b4c8e6ec2d06da17a'

# ERC1155 TransferSingle — emitted by CTF token contract on fills
# TransferSingle(address operator, address from, address to, uint256 id, uint256 value)
TRANSFER_SINGLE_TOPIC = '0xc3d58168c5ae7397731d063d5bbf3d657854427343f4c083240f7aacaa2d0f62'

# Polymarket CTF token contract (conditional tokens)
CTF_TOKEN = '0x4D97DCd97eC945f40cF65F87097ACe5EA0476045'


def parse_order_filled(log):
    """Parse OrderFilled event from CTF/NegRisk exchange log entry.

    Returns dict with maker, taker, asset IDs, amounts, fee — or None if not parseable.
    """
    topics = log.get('topics', [])
    data = log.get('data', '0x')
    if len(topics) < 1 or topics[0] != ORDER_FILLED_TOPIC:
        return None
    if len(data) < 2 + 64 * 8:  # 8 fields × 32 bytes each
        return None
    try:
        d = data[2:]  # strip 0x
        return {
            'type': 'ORDER_FILLED',
            'contract': log.get('address', '').lower(),
            'block_number': int(log.get('blockNumber', '0x0'), 16),
            'block_hash': log.get('blockHash'),
            'tx_hash': log.get('transactionHash'),
            'log_index': int(log.get('logIndex', '0x0'), 16),
            'order_hash': '0x' + d[0:64],
            'maker': '0x' + d[64+24:128],       # address is right-padded in 32 bytes
            'taker': '0x' + d[128+24:192],
            'maker_asset_id': int(d[192:256], 16),
            'taker_asset_id': int(d[256:320], 16),
            'maker_amount': int(d[320:384], 16),
            'taker_amount': int(d[384:448], 16),
            'fee': int(d[448:512], 16),
        }
    except (ValueError, IndexError):
        return None


def parse_transfer_single(log):
    """Parse ERC1155 TransferSingle from CTF token contract.

    Returns dict with operator, from, to, token_id, value — or None.
    """
    topics = log.get('topics', [])
    data = log.get('data', '0x')
    if len(topics) < 4 or topics[0] != TRANSFER_SINGLE_TOPIC:
        return None
    try:
        d = data[2:]
        return {
            'type': 'TRANSFER_SINGLE',
            'contract': log.get('address', '').lower(),
            'block_number': int(log.get('blockNumber', '0x0'), 16),
            'tx_hash': log.get('transactionHash'),
            'log_index': int(log.get('logIndex', '0x0'), 16),
            'operator': '0x' + topics[1][26:],    # address from indexed topic
            'from': '0x' + topics[2][26:],
            'to': '0x' + topics[3][26:],
            'token_id': int(d[0:64], 16),
            'value': int(d[64:128], 16),
        }
    except (ValueError, IndexError):
        return None


def matches_wallet(event, wallets):
    """Check if an on-chain event involves one of the monitored wallets.

    For OrderFilled: check maker and taker addresses.
    For TransferSingle: check from and to addresses.
    Returns (wallet_address, role) or (None, None).
    """
    wallets_lower = {w.lower() for w in wallets}
    if event['type'] == 'ORDER_FILLED':
        if event['maker'].lower() in wallets_lower:
            return event['maker'].lower(), 'maker'
        if event['taker'].lower() in wallets_lower:
            return event['taker'].lower(), 'taker'
    elif event['type'] == 'TRANSFER_SINGLE':
        if event['to'].lower() in wallets_lower:
            return event['to'].lower(), 'recipient'
        if event['from'].lower() in wallets_lower:
            return event['from'].lower(), 'sender'
    return None, None


class ChainMonitor:
    """WebSocket subscription to Polymarket exchange events on Polygon.

    Streams OrderFilled events in real-time (~2-3s block time) and notifies
    wallet_copy when a monitored wallet has activity.
    """

    def __init__(self, wss_url, wallets, on_event, clock=time.time):
        """
        Args:
            wss_url: Alchemy WSS endpoint (wss://polygon-mainnet.g.alchemy.com/v2/...)
            wallets: list of wallet addresses to monitor (lowercase hex)
            on_event: async callback(event_dict) called for each matching event
            clock: time source (for testing)
        """
        self.wss_url = wss_url
        self.wallets = [w.lower() for w in wallets]
        self.on_event = on_event
        self.clock = clock
        self.subscription_ids = {}
        self.last_block = 0
        self.events_seen = 0
        self.events_matched = 0
        self.errors = 0
        self.connected_at = None
        self.last_event_at = None
        self.recent_latencies = deque(maxlen=100)

    def status(self):
        return {
            'connected': self.connected_at is not None,
            'connected_at': self.connected_at,
            'last_block': self.last_block,
            'events_seen': self.events_seen,
            'events_matched': self.events_matched,
            'errors': self.errors,
            'last_event_at': self.last_event_at,
            'median_latency_s': sorted(self.recent_latencies)[len(self.recent_latencies)//2] if self.recent_latencies else None,
            'subscriptions': list(self.subscription_ids.keys()),
        }

    async def _subscribe(self, ws, name, params):
        """Subscribe to an eth_subscribe filter and store subscription ID."""
        msg = json.dumps({
            'jsonrpc': '2.0',
            'id': hash(name) & 0xFFFF,
            'method': 'eth_subscribe',
            'params': ['logs', params],
        })
        await ws.send(msg)
        resp = json.loads(await ws.recv())
        if 'result' in resp:
            sub_id = resp['result']
            self.subscription_ids[name] = sub_id
            LOG.info('subscribed %s: %s', name, sub_id)
        else:
            LOG.warning('subscribe %s failed: %s', name, resp.get('error'))

    async def _handle_log(self, log):
        """Parse a raw log entry and dispatch if it matches a monitored wallet."""
        self.events_seen += 1
        now = self.clock()

        # Try OrderFilled first, then TransferSingle
        event = parse_order_filled(log)
        if event is None:
            event = parse_transfer_single(log)
        if event is None:
            return

        wallet, role = matches_wallet(event, self.wallets)
        if wallet is None:
            return

        self.events_matched += 1
        self.last_event_at = now
        self.last_block = max(self.last_block, event.get('block_number', 0))

        # Enrich with detection metadata
        event['detected_at'] = now
        event['wallet'] = wallet
        event['role'] = role
        event['source'] = 'chain_monitor'

        # Estimate latency: block time ~2-3s, we detect in same block or next
        block_number = event.get('block_number', 0)
        event['detection_block'] = block_number

        try:
            await self.on_event(event)
        except Exception as e:
            LOG.warning('event handler error: %s', str(e)[:200])
            self.errors += 1

    async def run(self):
        """Main loop: connect, subscribe, process events. Reconnect on failure."""
        import websockets

        while True:
            self.connected_at = None
            self.subscription_ids.clear()
            try:
                async with websockets.connect(
                    self.wss_url,
                    open_timeout=10,
                    close_timeout=5,
                    max_size=5_000_000,  # some logs can be large
                    ping_interval=20,
                    ping_timeout=10,
                ) as ws:
                    self.connected_at = self.clock()
                    LOG.info('chain monitor connected to Polygon')

                    # Subscribe to OrderFilled on both exchanges
                    await self._subscribe(ws, 'ctf_orders', {
                        'address': CTF_EXCHANGE,
                        'topics': [ORDER_FILLED_TOPIC],
                    })
                    await self._subscribe(ws, 'negrisk_orders', {
                        'address': NEG_RISK_CTF_EXCHANGE,
                        'topics': [ORDER_FILLED_TOPIC],
                    })

                    # Process incoming events
                    async for message in ws:
                        if isinstance(message, bytes):
                            message = message.decode('utf-8')
                        if message in ('PONG', 'PING', ''):
                            continue

                        try:
                            data = json.loads(message)
                        except json.JSONDecodeError:
                            continue

                        # Subscription notification
                        if data.get('method') == 'eth_subscription':
                            params = data.get('params', {})
                            result = params.get('result', {})
                            if isinstance(result, dict) and 'topics' in result:
                                await self._handle_log(result)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.errors += 1
                self.connected_at = None
                LOG.warning('chain monitor disconnected: %s', str(e)[:200])
                await asyncio.sleep(5)


class ChainToActivityBridge:
    """Translates on-chain OrderFilled events into wallet_activity rows
    compatible with WalletObserver/WalletCopy pipeline.

    This bridges chain_monitor output → wallet_activity table → wallet_copy input.
    The REST WalletObserver continues to run as fallback for missed events.
    """

    def __init__(self, store, fetch, clock=time.time):
        from .token_resolver import TokenResolver
        self.store = store
        self.clock = clock
        self.resolver = TokenResolver(store, fetch, clock)
        self.events_bridged = 0
        self.events_skipped = 0
        self.events_unresolved = 0
        if not hasattr(store, "wallet_activity_ready"):
            store.wallet_activity_ready = asyncio.Event()

    async def on_chain_event(self, event):
        """Callback for ChainMonitor.on_event. Resolves token and inserts into wallet_activity."""
        import hashlib
        if event.get('type') != 'ORDER_FILLED':
            self.events_skipped += 1
            return

        now = self.clock()
        wallet = event['wallet']
        tx_hash = event.get('tx_hash', '')

        # Determine which token_id to resolve based on role:
        # taker buys maker's asset, so the relevant token is maker_asset_id
        token_id = event.get('maker_asset_id') if event['role'] == 'taker' else event.get('taker_asset_id')
        if not token_id:
            self.events_skipped += 1
            return

        # Resolve token_id → slug, conditionId, side
        info = await self.resolver.resolve(token_id)
        if info is None:
            self.events_unresolved += 1
            return

        # Determine BUY vs SELL:
        # taker who receives the conditional token is BUYING
        # maker who placed the order being filled could be either side
        side = 'BUY' if event['role'] == 'taker' else 'SELL'

        # Calculate price: maker_amount / taker_amount (both in micro-units)
        maker_amt = event.get('maker_amount', 0)
        taker_amt = event.get('taker_amount', 0)
        price = maker_amt / taker_amt if taker_amt > 0 else 0

        body = {
            'transactionHash': tx_hash,
            'type': 'TRADE',
            'side': side,
            'proxyWallet': wallet,
            'timestamp': now,
            'slug': info['slug'],
            'conditionId': info['conditionId'],
            'asset': info['asset'],
            'price': price,
            'size': taker_amt / 1e6,
            'usdcSize': maker_amt / 1e6 if side == 'BUY' else taker_amt / 1e6,
            'outcomeIndex': 0 if info['side'] == 'Up' else 1,
            # Chain-specific metadata
            '_source': 'chain_monitor',
            '_block_number': event.get('block_number'),
            '_log_index': event.get('log_index'),
            '_detected_at': event.get('detected_at'),
            '_resolved_side': info['side'],
        }

        # Fingerprint: tx_hash + log_index (unique per event, better than Data API)
        key_source = f"{tx_hash}:{event.get('log_index', 0)}"
        key = hashlib.sha256(key_source.encode()).hexdigest()

        with self.store.connect() as db:
            cur = db.execute(
                'INSERT OR IGNORE INTO wallet_activity VALUES (?,?,?,?,?)',
                (wallet, key, now, now, json.dumps(body, allow_nan=False)),
            )
            if cur.rowcount:
                self.events_bridged += 1
                if hasattr(self.store, 'wallet_activity_ready') and self.store.wallet_activity_ready is not None:
                    self.store.wallet_activity_ready.set()
            else:
                self.events_skipped += 1

    def status(self):
        return {
            'events_bridged': self.events_bridged,
            'events_skipped': self.events_skipped,
            'events_unresolved': self.events_unresolved,
            'resolver_cache': self.resolver.cache_stats(),
        }
