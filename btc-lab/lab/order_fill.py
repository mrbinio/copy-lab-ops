"""Decode a Polymarket order fill from the transaction that moved the tokens.

A token transfer says shares moved. It does not say the price. OrderFilled in
the same receipt names the wallet, the side, the token, the shares and the
collateral actually paid. A removed log is a reorg and is not a fill. The
public activity list stays a fallback when this receipt has no matching fill.
"""
from decimal import Decimal

# keccak256("OrderFilled(bytes32,address,address,uint256,uint256,uint256,uint256,uint256)")
ORDER_FILLED_TOPIC = '0xd0a08e8c493f9c94f29311604c9de1b4e8c8d4c06bd0c789af57f2d65bfec0f6'
# Exchange 0xe111180000d2663c0091e4f400237545b87b996b, seen on every Mitch fill
# on 8-9 Oct 2026. Data: side (0 BUY), token, maker gave, maker got, fee, two
# words not used here. One log per order and its maker is the order's owner.
ORDER_FILLED_V2_TOPIC = '0xd543adfd945773f1a62f74f0ee55a5e3b9b1a28262980ba90b1a89f2ea84d8ee'
SCALE = Decimal(10) ** 6
_SHARE_TOLERANCE = Decimal('0.000001')


def _address(topic):
    text = str(topic or '')
    if text.startswith('0x'):
        text = text[2:]
    if len(text) < 40:
        return None
    return '0x' + text[-40:].lower()


def _words(data):
    body = str(data or '')
    if body.startswith('0x'):
        body = body[2:]
    if len(body) < 64 * 5 or len(body) % 64:
        return None
    try:
        return [int(body[index:index + 64], 16) for index in range(0, 64 * 5, 64)]
    except ValueError:
        return None


def _parse_v2(log, topics):
    words = _words(log.get('data'))
    if not words:
        return None
    side, token, gave, got, fee = words
    if side not in (0, 1) or token == 0:
        return None
    maker = _address(topics[2])
    taker = _address(topics[3])
    if not maker or not taker:
        return None
    try:
        index = int(str(log.get('logIndex') or '0x0'), 16)
    except ValueError:
        return None
    buy = side == 0
    return {
        'maker': maker,
        'taker': taker,
        'maker_asset': 0 if buy else token,
        'taker_asset': token if buy else 0,
        'maker_amount': gave,
        'taker_amount': got,
        'fee': fee,
        'log_index': index,
        'tx': log.get('transactionHash'),
        'owner_only': True,
    }


def parse_order_filled(log):
    """One OrderFilled log, or None when it is not that event or was removed."""
    if not isinstance(log, dict) or log.get('removed'):
        return None
    topics = log.get('topics') or []
    if len(topics) < 4:
        return None
    if str(topics[0]).lower() == ORDER_FILLED_V2_TOPIC:
        return _parse_v2(log, topics)
    if str(topics[0]).lower() != ORDER_FILLED_TOPIC:
        return None
    words = _words(log.get('data'))
    if not words:
        return None
    maker = _address(topics[2])
    taker = _address(topics[3])
    if not maker or not taker:
        return None
    try:
        index = int(str(log.get('logIndex') or '0x0'), 16)
    except ValueError:
        return None
    return {
        'maker': maker,
        'taker': taker,
        'maker_asset': words[0],
        'taker_asset': words[1],
        'maker_amount': words[2],
        'taker_amount': words[3],
        'fee': words[4],
        'log_index': index,
        'tx': log.get('transactionHash'),
    }


def _leg(fill, wallet, token):
    """Shares and collateral for this wallet. The other wallets in the tx are ignored."""
    wallet = str(wallet).lower()
    if fill['maker'] == wallet:
        give_asset, give_amount = fill['maker_asset'], fill['maker_amount']
        take_asset, take_amount = fill['taker_asset'], fill['taker_amount']
    elif fill['taker'] == wallet and not fill.get('owner_only'):
        give_asset, give_amount = fill['taker_asset'], fill['taker_amount']
        take_asset, take_amount = fill['maker_asset'], fill['maker_amount']
    else:
        return None
    if give_asset == 0 and take_asset == token and give_amount > 0 and take_amount > 0:
        return 'BUY', take_amount, give_amount
    if take_asset == 0 and give_asset == token and give_amount > 0 and take_amount > 0:
        return 'SELL', give_amount, take_amount
    return None


def fill_for_wallet(logs, wallet, token_id, shares=None):
    """Sum this wallet's fills of one token in one transaction.

    The same log index is one fill. A second index is another execution.
    The share total has to match the token transfer. A book price is not used.
    """
    try:
        token = int(token_id)
    except (TypeError, ValueError):
        return None
    wanted = None
    if shares is not None:
        try:
            wanted = Decimal(str(shares))
        except Exception:
            return None
        if not wanted.is_finite() or wanted <= 0:
            return None
    seen = set()
    legs = []
    for log in logs or []:
        parsed = parse_order_filled(log)
        if not parsed:
            continue
        identity = (str(parsed.get('tx') or ''), parsed['log_index'])
        if identity in seen:
            continue
        seen.add(identity)
        leg = _leg(parsed, wallet, token)
        if leg:
            legs.append((leg[0], leg[1], leg[2], parsed['fee']))
    if not legs:
        return None
    if len({leg[0] for leg in legs}) != 1:
        return None
    share_raw = sum(leg[1] for leg in legs)
    usdc_raw = sum(leg[2] for leg in legs)
    if share_raw <= 0 or usdc_raw <= 0:
        return None
    size = Decimal(share_raw) / SCALE
    usdc = Decimal(usdc_raw) / SCALE
    if wanted is not None and abs(size - wanted) > _SHARE_TOLERANCE:
        return None
    return {
        'side': legs[0][0],
        'size': size,
        'usdc': usdc,
        'price': usdc / size,
        'fee': Decimal(sum(leg[3] for leg in legs)) / SCALE,
        'fills': len(legs),
    }


def execution_from_receipt(reader, event, want_block=True):
    """Receipt plus the block time. None when the RPC or the decode does not match.

    The block time is the chain's publication of the fill, not the moment the
    order was signed. A failure here leaves the public list as the fallback.
    """
    import time
    tx = event.get('tx_hash')
    if not tx or reader is None:
        return None
    started = time.perf_counter()
    try:
        receipt = reader._rpc('eth_getTransactionReceipt', [tx])
    except Exception:
        return None
    if not isinstance(receipt, dict):
        return None
    logs = [log for log in (receipt.get('logs') or []) if isinstance(log, dict) and not log.get('removed')]
    shares = None
    try:
        shares = Decimal(event.get('value') or 0) / SCALE
    except Exception:
        shares = None
    parsed = fill_for_wallet(logs, event.get('wallet'), event.get('token_id'), shares)
    if not parsed or parsed['side'] != event.get('side'):
        return None
    rpc_ms = (time.perf_counter() - started) * 1000
    block_ts = None
    block_hex = receipt.get('blockNumber')
    if want_block and isinstance(block_hex, str) and rpc_ms < 400:
        try:
            block = reader._rpc('eth_getBlockByNumber', [block_hex, False])
        except Exception:
            block = None
        if isinstance(block, dict) and isinstance(block.get('timestamp'), str):
            try:
                block_ts = int(block['timestamp'], 16)
            except ValueError:
                block_ts = None
        rpc_ms = (time.perf_counter() - started) * 1000
    return parsed, block_ts, rpc_ms
