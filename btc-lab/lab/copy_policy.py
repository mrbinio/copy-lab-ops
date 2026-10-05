"""Shared PAPER copy decisions for the live account and versioned observation.

Independent hold-to-settlement tickets do not use this module. A missing
source price is a skip, never a substitute from the current book.
"""
from decimal import Decimal, ROUND_FLOOR

from .core import simulate_fill
from .mid_window import simulate_sale

POLICY = 'copy-paper-v2'
DEVIATION = Decimal('0.10')
MIN_SOURCE_PRICE = Decimal('0.20')
MAX_SOURCE_PRICE = Decimal('0.70')
BUDGET = 5_000_000


def level_key(price):
    return format(Decimal(str(price)).normalize(), 'f')


def confirmed_source_price(event):
    """The source trade's own price. The book is not a stand-in."""
    if not isinstance(event, dict) or 'price' not in event or event.get('price') in (None, ''):
        return None, 'SOURCE_PRICE_MISSING'
    try:
        price = Decimal(str(event.get('price')))
    except Exception:
        return None, 'SOURCE_PRICE_INVALID'
    if not price.is_finite() or not 0 < price < 1:
        return None, 'SOURCE_PRICE_INVALID'
    return price, None


def band_reason(price):
    if price < MIN_SOURCE_PRICE:
        return 'COPY_PRICE_TOO_LOW'
    if price > MAX_SOURCE_PRICE:
        return 'COPY_PRICE_TOO_HIGH'
    return None


def buy_limit(source, book):
    """Executable ask and the order cap must sit within source ± 0.10.

    ask + 2¢ is not this check. The cap is the top of the source band.
    """
    asks = (book or {}).get('asks') or []
    if not asks:
        return None, 'NO_ASK'
    ask = min(Decimal(str(price)) for price, _size in asks)
    if abs(ask - source) > DEVIATION:
        return None, 'SOURCE_PRICE_MOVED'
    return min(Decimal('0.999999'), source + DEVIATION), None


def sell_floor(book):
    bids = (book or {}).get('bids') or []
    if not bids:
        return None, 'NO_BID'
    tick = Decimal(str(book['tick']))
    bid = max(Decimal(str(price)) for price, _size in bids)
    return max(tick, bid - Decimal('0.02')), None


def _consumed_map(consumed, book):
    token = str((book or {}).get('token') or '')
    stamp = str((book or {}).get('source_ts') or '')
    return {
        price: shares
        for (tok, seen, price), shares in (consumed or {}).items()
        if tok == token and seen == stamp
    }


def asks_after_consumption(asks, consumed, book):
    taken = _consumed_map(consumed, book)
    out = []
    for price, size in asks or []:
        left = Decimal(str(size)) - Decimal(str(taken.get(level_key(price), 0)))
        if left > 0:
            out.append([str(price), format(left, 'f')])
    return out


def bids_after_consumption(bids, consumed, book):
    taken = _consumed_map(consumed, book)
    out = []
    for price, size in bids or []:
        left = Decimal(str(size)) - Decimal(str(taken.get(level_key(price), 0)))
        if left > 0:
            out.append([str(price), format(left, 'f')])
    return out


def remember_fill(consumed, book, fill):
    token = str((book or {}).get('token') or '')
    stamp = str((book or {}).get('source_ts') or '')
    for piece in (fill or {}).get('fills') or []:
        key = (token, stamp, level_key(piece['price']))
        consumed[key] = Decimal(str(consumed.get(key, 0))) + Decimal(str(piece['shares']))


def decide_buy(source, book, consumed, budget=BUDGET):
    limit, why = buy_limit(source, book)
    if why:
        return why, None
    asks = asks_after_consumption(book.get('asks'), consumed, book)
    if not asks:
        return 'BUY_NO_FULL_FILL_OR_MINIMUM', None
    ask = min(Decimal(str(price)) for price, _size in asks)
    if abs(ask - source) > DEVIATION:
        return 'SOURCE_PRICE_MOVED', None
    notional = (Decimal(str(book['min_shares'])) * ask).quantize(Decimal('0.000001'), rounding=ROUND_FLOOR)
    fill = simulate_fill(asks, notional, limit, book['fee_rate'], book['min_shares'], book['tick'])
    if not fill or fill['cost'] + fill['fee'] > budget:
        return 'BUY_NO_FULL_FILL_OR_MINIMUM', None
    if abs(Decimal(str(fill['vwap'])) - source) > DEVIATION:
        return 'SOURCE_PRICE_MOVED', None
    return None, fill


def decide_sell(book, shares, consumed):
    floor, why = sell_floor(book)
    if why:
        return why, None
    view = dict(book)
    view['bids'] = bids_after_consumption(book.get('bids'), consumed, book)
    if not view['bids']:
        return 'SELL_NO_FULL_FILL', None
    fill = simulate_sale(view, shares, book['fee_rate'], floor)
    if not fill:
        return 'SELL_NO_FULL_FILL', None
    return None, fill
