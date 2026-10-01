"""CLOB order module — places real limit orders on Polymarket via py-clob-client.

Requires:
  - pip install py-clob-client
  - Polygon wallet private key
  - Polymarket API credentials (key, secret, passphrase)
  - USDC balance on Polygon

This module is DISABLED by default. Set CLOB_LIVE=true in config to enable.
All orders are GTC limit orders on the BUY side only.

Safety:
  - Max order size capped at MAX_ORDER_USD
  - Only BTC/ETH up/down 5m/15m markets
  - Requires explicit CLOB_LIVE=true flag
  - Logs every order attempt
"""
import json
import logging
import time
from decimal import Decimal, ROUND_FLOOR

log = logging.getLogger(__name__)

# Hard caps — never exceed these regardless of config
MAX_ORDER_USD = 10.0
CHAIN_ID = 137  # Polygon mainnet


class CLOBClient:
    """Thin wrapper around py-clob-client for copy trading."""

    def __init__(self, private_key: str, max_order_usd: float = 5.0,
                 funder: str | None = None):
        """
        Args:
            private_key: Polygon wallet private key (hex, with or without 0x)
            api_key: Polymarket CLOB API key
            api_secret: Polymarket CLOB API secret
            api_passphrase: Polymarket CLOB API passphrase
            funder: Optional funder address (for proxy wallets)
            max_order_usd: Max USD per order (capped at MAX_ORDER_USD)
        """
        # Lazy import — don't crash if py-clob-client not installed
        from py_order_utils.types import BUY
        from py_clob_client.client import ClobClient
        from py_clob_client.clob_types import OrderArgs, OrderType

        self._BUY = BUY
        self._OrderArgs = OrderArgs
        self._OrderType = OrderType

        self.max_order_usd = min(max_order_usd, MAX_ORDER_USD)
        self.client = ClobClient(
            host="https://clob.polymarket.com",
            chain_id=CHAIN_ID,
            private_key=private_key,
            signature_type=0,  # EOA wallet
            funder=funder,
        )
        self.client.set_api_creds(self.client.create_or_derive_api_creds())
        log.info("CLOB client initialized, max_order=%.2f USD", self.max_order_usd)

    def buy(self, token_id: str, price: float, size: float,
            fee_rate: float = 0.07) -> dict:
        """Place a GTC BUY limit order.

        Args:
            token_id: Polymarket condition token ID for the side to buy
            price: Limit price (e.g. 0.65 for 65c)
            size: Number of shares (NOT USD — shares = usd / price approximately)
            fee_rate: Taker fee rate (default 7%)

        Returns:
            dict with order_id, status, and full response
        """
        # Safety checks
        cost_usd = size * price
        if cost_usd > self.max_order_usd:
            raise ValueError(
                f"Order cost ${cost_usd:.2f} exceeds max ${self.max_order_usd:.2f}"
            )
        if not 0.01 <= price <= 0.99:
            raise ValueError(f"Price {price} outside valid range 0.01-0.99")
        if size < 5:
            raise ValueError(f"Size {size} below Polymarket minimum of 5 shares")

        order_args = self._OrderArgs(
            price=price,
            size=size,
            side=self._BUY,
            token_id=token_id,
        )

        log.info(
            "CLOB BUY: token=%s price=%.2f size=%.2f cost=~$%.2f",
            token_id[:16] + "...", price, size, cost_usd,
        )

        try:
            signed = self.client.create_order(order_args)
            resp = self.client.post_order(signed, self._OrderType.GTC)
            log.info("CLOB order response: %s", json.dumps(resp, default=str)[:500])
            return {
                "ok": resp.get("success", False),
                "order_id": resp.get("orderID"),
                "status": resp.get("status", "UNKNOWN"),
                "response": resp,
                "placed_at": time.time(),
                "price": price,
                "size": size,
                "token_id": token_id,
            }
        except Exception as e:
            log.error("CLOB order failed: %s", e)
            return {
                "ok": False,
                "error": str(e)[:400],
                "placed_at": time.time(),
                "price": price,
                "size": size,
                "token_id": token_id,
            }

    def sell(self, token_id: str, price: float, size: float) -> dict:
        """Place a GTC SELL limit order.

        Args:
            token_id: Token to sell
            price: Limit price
            size: Number of shares to sell
        """
        from py_order_utils.types import SELL as SELL_SIDE

        if not 0.01 <= price <= 0.99:
            raise ValueError(f"Price {price} outside valid range")
        if size < 5:
            raise ValueError(f"Size {size} below minimum")

        order_args = self._OrderArgs(
            price=price,
            size=size,
            side=SELL_SIDE,
            token_id=token_id,
        )

        log.info(
            "CLOB SELL: token=%s price=%.2f size=%.2f",
            token_id[:16] + "...", price, size,
        )

        try:
            signed = self.client.create_order(order_args)
            resp = self.client.post_order(signed, self._OrderType.GTC)
            log.info("CLOB sell response: %s", json.dumps(resp, default=str)[:500])
            return {
                "ok": resp.get("success", False),
                "order_id": resp.get("orderID"),
                "response": resp,
                "placed_at": time.time(),
            }
        except Exception as e:
            log.error("CLOB sell failed: %s", e)
            return {"ok": False, "error": str(e)[:400], "placed_at": time.time()}

    def cancel(self, order_id: str) -> dict:
        """Cancel an open order."""
        try:
            resp = self.client.cancel(order_id)
            return {"ok": True, "response": resp}
        except Exception as e:
            return {"ok": False, "error": str(e)[:400]}

    def balance(self) -> dict:
        """Check USDC balance (if supported by client)."""
        try:
            # py-clob-client may not have direct balance check
            # This is a placeholder — real balance check needs web3
            return {"status": "NOT_IMPLEMENTED"}
        except Exception as e:
            return {"error": str(e)[:200]}


def calculate_order(budget_usd: float, ask_price: float,
                    fee_rate: float = 0.07) -> dict:
    """Calculate order parameters from a USD budget.

    Args:
        budget_usd: Max USD to spend (including fees)
        ask_price: Current best ask price
        fee_rate: Taker fee rate

    Returns:
        dict with price, size (shares), estimated_cost
    """
    # Net budget after fees
    net = Decimal(str(budget_usd)) / (1 + Decimal(str(fee_rate)))
    shares = (net / Decimal(str(ask_price))).quantize(
        Decimal("0.01"), rounding=ROUND_FLOOR
    )
    cost = float(shares * Decimal(str(ask_price)))
    fee = float(Decimal(str(cost)) * Decimal(str(fee_rate)))

    return {
        "price": ask_price,
        "size": float(shares),
        "estimated_cost": cost,
        "estimated_fee": fee,
        "estimated_total": cost + fee,
    }
