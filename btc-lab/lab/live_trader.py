"""Real orders through Polymarket's Deposit Wallet (Damian, 20 Oct 2026).

On 20 Oct 01:09 Polymarket rejected the first real order from the plain wallet:
"maker address not allowed, please use the deposit wallet flow". Orders,
sells, redeems and withdrawals now go through the official unified SDK
(polymarket-client) and the signer's Deposit Wallet:

  signer (EOA)    0xEb1F…bF01   holds the key, POL, and is the 'bank' for
                                Kraken deposits and profit sweeps
  deposit wallet  0x2De4…778c   holds the trading pUSD and outcome shares

Wallet actions (redeem, transfer back to the signer) are gasless through the
Polymarket relayer, authorised with the Builder API key in
secrets/builder.json. The SDK client is built once and kept warm; signing and
posting a market order takes ~15 ms + the network round trip.
"""
import json
import logging
import threading
from decimal import Decimal
from pathlib import Path

LOG = logging.getLogger(__name__)

PUSD = '0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB'
FILLED_STATUSES = ('matched', 'mined', 'confirmed')


class Trader:
    def __init__(self, root, factory=None):
        self.root = Path(root)
        self._factory = factory or self._make
        self._client = None
        self._lock = threading.Lock()

    def _make(self):
        from polymarket import BuilderApiKey, SecureClient
        builder = json.loads((self.root / 'secrets' / 'builder.json').read_text())
        key = (self.root / 'secrets' / 'polygon.key').read_text().strip()
        try:
            return SecureClient.create(private_key=key, api_key=BuilderApiKey(
                key=builder['key'], secret=builder['secret'], passphrase=builder['passphrase']))
        finally:
            del key

    def client(self):
        with self._lock:
            if self._client is None:
                self._client = self._factory()
            return self._client

    def ready(self):
        return (self.root / 'secrets' / 'builder.json').exists() and (self.root / 'secrets' / 'polygon.key').exists()

    def wallet_address(self):
        return str(self.client().wallet)

    def buy(self, token, amount, max_price):
        return self._order(dict(asset_id=str(token), side='BUY', amount=Decimal(str(amount)),
                                max_price=Decimal(str(max_price)), order_type='FOK'))

    def sell(self, token, shares, min_price):
        return self._order(dict(asset_id=str(token), side='SELL', shares=Decimal(str(shares)),
                                min_price=Decimal(str(min_price)), order_type='FOK'))

    def _order(self, args):
        """The reply in the shape the live mirror already stores (old CLOB keys)."""
        from polymarket.errors import InsufficientLiquidityError
        try:
            r = self.client().place_market_order(**args)
        except InsufficientLiquidityError as error:
            return {'success': False, 'status': 'unmatched', 'errorMsg': str(error)[:200]}
        return {'success': bool(getattr(r, 'ok', False)), 'status': str(getattr(r, 'status', '') or ''),
                'orderID': getattr(r, 'order_id', None),
                'makingAmount': str(getattr(r, 'making_amount', '') or ''),
                'takingAmount': str(getattr(r, 'taking_amount', '') or ''),
                'transactionsHashes': list(getattr(r, 'transactions_hashes', None) or []),
                'errorMsg': getattr(r, 'error_msg', None) or getattr(r, 'error', None)}

    def warm_market(self, token):
        """Cache a market's order data before its first order. With None it
        refreshes the last market, which also keeps the connection open."""
        client = self.client()
        ctx = client._ctx
        if token is None:
            token = getattr(self, '_last_warm', None)
            if token:
                ctx.order_metadata.fetch_current_market(ctx, token_id=token)
            return
        ctx.order_metadata.resolve_market(ctx, token_id=str(token))
        self._last_warm = str(token)

    def redeem(self, condition):
        return _tx(self.client().redeem_positions(condition_id=str(condition)))

    def pull(self, amount_micro, to):
        """pUSD from the deposit wallet back to the signer (gasless)."""
        return _tx(self.client().transfer_erc20(token_address=PUSD, recipient_address=to, amount=int(amount_micro)))


def filled(reply):
    return bool(reply and reply.get('success') and str(reply.get('status', '')).lower() in FILLED_STATUSES)


def _tx(handle):
    out = handle.wait()
    return getattr(out, 'transaction_hash', None) or getattr(handle, 'transaction_hash', None)
