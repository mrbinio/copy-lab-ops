"""Read a wallet's fill from the exchange transaction before it is mined.

Polymarket matches on the CLOB, then the operator sends matchOrders to the
exchange. The market channel prints the trade with that transaction hash at
match time. The transaction is in the mempool about 70 ms later, about 1.4 s
before its logs are on chain. Its input names every order in the match:
maker, token, amounts, side and the time the order was signed.

Layout measured on 9 Oct 2026 against 0xe111180000d2663c0091e4f400237545b87b996b,
selector 0x3c2b4399:

    matchOrders(bytes32, Order taker, Order[] makers, uint256 takerFill,
                uint256[] makerFills, uint256 takerFee, uint256[] makerFees)
    Order = (salt, maker, signer, tokenId, makerAmount, takerAmount, side,
             signatureType, timestampMs, bytes32, bytes32, bytes signature)

Fill amounts are in the units the order gives: USDC for a BUY, shares for a
SELL. Everything has six decimals. A shape that does not match returns None,
and the slower receipt path stays the fallback.
"""
from decimal import Decimal

MATCH_EXCHANGE = '0xe111180000d2663c0091e4f400237545b87b996b'
MATCH_SELECTOR = '0x3c2b4399'
SCALE = Decimal(10) ** 6
_ORDER_WORDS = 12
_MAX_MAKERS = 64


def _words(hex_body):
    body = hex_body[2:] if hex_body.startswith('0x') else hex_body
    if len(body) % 64:
        return None
    try:
        return [int(body[i:i + 64], 16) for i in range(0, len(body), 64)]
    except ValueError:
        return None


def _address(word):
    return '0x' + format(word, '064x')[-40:]


def _order(words, start):
    if start < 0 or start + _ORDER_WORDS > len(words):
        return None
    w = words[start:start + _ORDER_WORDS]
    if w[6] not in (0, 1) or w[1] >> 160 or w[2] >> 160:
        return None
    return {
        'maker': _address(w[1]),
        'signer': _address(w[2]),
        'token': w[3],
        'maker_amount': w[4],
        'taker_amount': w[5],
        'side': 'BUY' if w[6] == 0 else 'SELL',
        'signed_ms': w[8],
    }


def _array(words, offset_word):
    if offset_word % 32:
        return None
    at = offset_word // 32
    if at >= len(words):
        return None
    n = words[at]
    if n > _MAX_MAKERS or at + 1 + n > len(words):
        return None
    return at, n


def decode_match(tx):
    """Taker order, maker orders and fill amounts, or None."""
    if not isinstance(tx, dict):
        return None
    if str(tx.get('to') or '').lower() != MATCH_EXCHANGE:
        return None
    data = str(tx.get('input') or '')
    if not data.lower().startswith(MATCH_SELECTOR):
        return None
    words = _words(data[10:])
    if not words or len(words) < 7:
        return None
    if words[1] % 32 or words[2] % 32 or words[4] % 32 or words[6] % 32:
        return None
    taker = _order(words, words[1] // 32)
    makers_at = _array(words, words[2])
    fills_at = _array(words, words[4])
    fees_at = _array(words, words[6])
    if not taker or not makers_at or not fills_at or not fees_at:
        return None
    at, n = makers_at
    makers = []
    for i in range(n):
        rel = words[at + 1 + i]
        if rel % 32:
            return None
        order = _order(words, at + 1 + rel // 32)
        if not order:
            return None
        makers.append(order)
    f_at, f_n = fills_at
    e_at, e_n = fees_at
    if f_n != n or e_n != n:
        return None
    return {
        'tx': str(tx.get('hash') or '').lower(),
        'taker': taker,
        'makers': makers,
        'taker_fill': words[3],
        'taker_fee': words[5],
        'maker_fills': words[f_at + 1:f_at + 1 + n],
        'maker_fees': words[e_at + 1:e_at + 1 + n],
        'pending': tx.get('blockNumber') is None,
    }


def _price(order):
    """USDC per share at this order's limit."""
    if order['maker_amount'] <= 0 or order['taker_amount'] <= 0:
        return None
    if order['side'] == 'BUY':
        return Decimal(order['maker_amount']) / Decimal(order['taker_amount'])
    return Decimal(order['taker_amount']) / Decimal(order['maker_amount'])


def _maker_shares(order, fill):
    """Shares that changed hands for one maker fill, in raw units."""
    price = _price(order)
    if price is None or price <= 0:
        return None
    if order['side'] == 'BUY':
        return Decimal(fill) / price
    return Decimal(fill)


def wallet_fills(match, wallets):
    """One leg per watched wallet: side, token, shares, USDC, price, fee, signed time.

    A taker's shares are what its makers delivered. Against a maker on the
    complementary token (a mint or a merge), one share of each side is one
    share for the taker as well. The taker's USDC is its own fill for a BUY,
    and for a SELL it is what the makers paid, net of the complement.
    """
    if not match:
        return []
    watched = {str(w).lower() for w in wallets}
    legs = []
    taker = match['taker']
    if taker['maker'] in watched:
        shares = Decimal(0)
        usdc_in = Decimal(0)
        for order, fill in zip(match['makers'], match['maker_fills']):
            got = _maker_shares(order, fill)
            if got is None:
                return legs
            shares += got
            price = _price(order)
            same = order['token'] == taker['token']
            if taker['side'] == 'SELL':
                usdc_in += got * price if same else got * (1 - price)
        if taker['side'] == 'BUY':
            usdc = Decimal(match['taker_fill'])
        else:
            usdc = usdc_in
            if abs(shares - Decimal(match['taker_fill'])) > 1:
                shares = Decimal(match['taker_fill'])
        legs.append(_leg(taker, shares, usdc, match['taker_fee'], 'taker'))
    for order, fill, fee in zip(match['makers'], match['maker_fills'], match['maker_fees']):
        if order['maker'] not in watched:
            continue
        price = _price(order)
        if price is None:
            continue
        if order['side'] == 'BUY':
            usdc, shares = Decimal(fill), Decimal(fill) / price
        else:
            shares, usdc = Decimal(fill), Decimal(fill) * price
        legs.append(_leg(order, shares, usdc, fee, 'maker'))
    return [leg for leg in legs if leg]


def _leg(order, shares_raw, usdc_raw, fee_raw, role):
    if shares_raw <= 0 or usdc_raw <= 0:
        return None
    shares = (shares_raw / SCALE).quantize(Decimal('0.000001'))
    usdc = (Decimal(usdc_raw) / SCALE).quantize(Decimal('0.000001'))
    return {
        'wallet': order['maker'],
        'side': order['side'],
        'token': str(order['token']),
        'shares': shares,
        'usdc': usdc,
        'price': usdc / shares,
        'fee': Decimal(fee_raw) / SCALE,
        'signed_at': order['signed_ms'] / 1000 if order['signed_ms'] else None,
        'role': role,
    }
