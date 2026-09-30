"""On-chain Polygon WebSocket monitor for Polymarket wallet activity.

HYBRID ARCHITECTURE (2026-09-30):
  Chain monitor detects trades fast (~2-3s) but CANNOT extract execution price
  from on-chain data (Polymarket NegRisk does pair splits at 1.00 USD,
  individual token price is in CLOB order, not on-chain settlement).

  Solution: Chain monitor triggers immediate REST poll of Data API,
  which has the execution price. The REST observer (wallet_observer.py)
  handles actual insertion into wallet_activity with full price data.

  Chain ──(2-3s)──► "wallet X traded in TX Y" ──► trigger immediate REST poll
  REST  ──(5-15s)─► "price = 0.65, slug = ..." ──► wallet_activity ──► wallet_copy

  Net latency: ~5-8s (chain detection + triggered REST) vs ~7-35s (REST-only polling).
  The chain monitor does NOT insert into wallet_activity directly.

Requires: Alchemy (or compatible) WebSocket endpoint for Polygon Mainnet.
"""
import asyncio
import json
import logging
import time

LOG = logging.getLogger('btc-lab.chain')

# Polymarket CTF Token contract on Polygon PoS (Chain ID 137).
CTF_TOKEN = '0x4D97DCd97eC945f40cF65F87097ACe5EA0476045'

# ERC1155 TransferSingle(address indexed operator, address indexed from,
#                         address indexed to, uint256 id, uint256 value)
TRANSFER_SINGLE_TOPIC = '0xc3d58168c5ae7397731d063d5bbf3d657854427343f4c083240f7aacaa2d0f62'

# Known Polymarket exchange operators — transfers initiated by these are exchange fills.
EXCHANGE_OPERATORS = {
    '0x4bfb41d5b3570defd03c39a9a4d8de6bd8b8982e',  # CTF Exchange
    '0xc5d563a36ae78145c45a50134d48a1215220f80a',  # NegRisk CTF Exchange
}

ZERO_ADDRESS = '0x' + '0' * 40


def parse_transfer_single(log):
    """Parse ERC1155 TransferSingle from a raw Polygon log entry.

    Real format (verified on-chain 2026-09-30):
      topics[0] = event signature
      topics[1] = operator (address, indexed)
      topics[2] = from (address, indexed)
      topics[3] = to (address, indexed)
      data = token_id (uint256) + value (uint256)

    Returns parsed dict or None.
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
    """Determine if a TransferSingle involves a monitored wallet.

    Returns (wallet, side) where side is 'BUY' or 'SELL', or (None, None).
    Only considers exchange-initiated transfers.
    """
    operator = event['operator']
    if operator not in EXCHANGE_OPERATORS:
        return None, None

    frm = event['from']
    to = event['to']

    if to in wallets_lower and frm != to:
        return to, 'BUY'
    if frm in wallets_lower and frm != ZERO_ADDRESS:
        return frm, 'SELL'

    return None, None


class ChainMonitor:
    """WebSocket subscription to TransferSingle events on CTF Token contract.

    When a monitored wallet's trade is detected on-chain, triggers an
    immediate REST poll via wallet_observer to get the full event with price.
    Does NOT insert into wallet_activity directly.
    """

    def __init__(self, wss_url, wallets, on_detection, clock=time.time):
        """
        Args:
            wss_url: Alchemy WSS endpoint
            wallets: list of wallet addresses to monitor
            on_detection: async callback(wallet, tx_hash, side, token_id)
                          — called when a monitored wallet trades on-chain.
                          Should trigger immediate REST poll for that wallet.
            clock: time source
        """
        self.wss_url = wss_url
        self.wallets = {w.lower() for w in wallets}
        self.on_detection = on_detection
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
            'mode': 'HYBRID_DETECTION_ONLY',
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
        """Main loop: connect, subscribe to TransferSingle, trigger on detection."""
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
                    LOG.info('chain monitor connected (hybrid detection mode)')

                    sub_msg = json.dumps({
                        'jsonrpc': '2.0', 'id': 1,
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
                        if event is None or event.get('removed'):
                            continue

                        self.events_seen += 1
                        self.last_block = max(self.last_block, event['block_number'])

                        wallet, side = classify_transfer(event, self.wallets)
                        if wallet is None:
                            continue

                        self.events_matched += 1
                        self.last_event_at = self.clock()

                        try:
                            await self.on_detection(
                                wallet=wallet,
                                tx_hash=event['tx_hash'],
                                side=side,
                                token_id=event['token_id'],
                                block_number=event['block_number'],
                                detected_at=self.last_event_at,
                            )
                        except Exception as e:
                            LOG.warning('detection handler error: %s', str(e)[:200])
                            self.errors += 1

            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.errors += 1
                self.connected_at = None
                LOG.warning('chain monitor disconnected: %s', str(e)[:200])
                await asyncio.sleep(5)
