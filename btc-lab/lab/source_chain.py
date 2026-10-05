"""Confirmed source inventory from a token balance at one block.

The balance is the state at the end of that block, so every transfer in the
block is already included. Later transfers apply in block and log-index order.
The clock on this machine is not the coverage point. A failed read does not
mark the book known, and this module never opens a copy.
"""
import json
import os
import urllib.request
from decimal import Decimal
from urllib.parse import urlsplit

from .wallet_chain_monitor import CTF_TOKEN, TRANSFER_SINGLE_TOPIC, ZERO_ADDRESS
from .wallet_copy import (
    _dec, anchor_source_position, apply_source_trade, end_of_block,
    ensure_source_schema, order_cursor, source_position)

CONFIRMED_DEPTH = 5
LOOKBACK = 900
TOKEN_LIMIT = 4
REFRESH_LIMIT = 4
MAX_NEW_RECEIPTS = 8
SHARES_SCALE = Decimal(10) ** 6
BALANCE_OF = '00fdd58e'


def http_url_from_wss(url):
    if not isinstance(url, str) or not url:
        return None
    if url.startswith('wss://'):
        return 'https://' + url[len('wss://'):]
    if url.startswith('ws://'):
        return 'http://' + url[len('ws://'):]
    if url.startswith('https://') or url.startswith('http://'):
        return url
    return None


def reader_from_env(environ=None):
    environ = os.environ if environ is None else environ
    url = http_url_from_wss(environ.get('ALCHEMY_WSS') or '')
    if not url:
        return None
    return TokenBalanceReader(url)


def encode_balance_of(wallet, token_id):
    address = str(wallet).lower().removeprefix('0x')
    if len(address) != 40:
        raise ValueError('wallet')
    token = int(token_id)
    encoded = format(token, 'x')
    if len(encoded) > 64:
        raise ValueError('token')
    return '0x' + BALANCE_OF + address.rjust(64, '0') + encoded.rjust(64, '0')


def _post(url, payload, timeout=8):
    body = json.dumps(payload).encode()
    request = urllib.request.Request(url, data=body, headers={
        'User-Agent': 'BTC-Lab-Paper/0.1',
        'Accept': 'application/json',
        'Content-Type': 'application/json',
    })
    host = urlsplit(url).hostname or 'rpc'
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise ValueError('oversized rpc response')
            return json.loads(raw)
    except Exception:
        raise RuntimeError(f'{host}: no response') from None


class TokenBalanceReader:
    """JSON-RPC. Errors name the host only, never the URL path."""

    def __init__(self, url, post=None):
        self.url = url
        self._post = post or _post
        self._id = 0

    def _rpc(self, method, params):
        self._id += 1
        host = urlsplit(self.url).hostname or 'rpc'
        try:
            result = self._post(self.url, {
                'jsonrpc': '2.0', 'id': self._id, 'method': method, 'params': params})
        except Exception:
            raise RuntimeError(f'{host}: no response') from None
        if not isinstance(result, dict) or result.get('error'):
            raise RuntimeError(f'{host}: rpc rejected')
        return result.get('result')

    def block_number(self):
        raw = self._rpc('eth_blockNumber', [])
        if not isinstance(raw, str):
            raise RuntimeError('block number missing')
        return int(raw, 16)

    def token_balance_raw(self, wallet, token_id, block):
        raw = self._rpc('eth_call', [{
            'to': CTF_TOKEN,
            'data': encode_balance_of(wallet, token_id),
        }, hex(int(block))])
        # A confirmed zero is a full 32-byte word of zeros. An empty or missing
        # eth_call result is not that word.
        if not isinstance(raw, str) or not raw.startswith('0x'):
            raise RuntimeError('balance missing')
        body = raw[2:]
        if len(body) != 64 or any(char not in '0123456789abcdefABCDEF' for char in body):
            raise RuntimeError('balance missing')
        return int(body, 16)

    def transfers(self, tx_hash):
        raw = self._rpc('eth_getTransactionReceipt', [tx_hash])
        if raw is None:
            return None
        if not isinstance(raw, dict) or not raw.get('blockNumber'):
            raise RuntimeError('receipt missing')
        status = raw.get('status')
        ok = status is None or int(status, 16) == 1
        block = int(raw['blockNumber'], 16)
        logs = []
        if ok:
            for entry in raw.get('logs') or []:
                parsed = _parse_transfer(entry, block)
                if parsed:
                    logs.append(parsed)
        return {'block': block, 'ok': ok, 'logs': logs}

    def transfers_after(self, wallet, token_id, start_block, end_block):
        """Transfers of one token after the balance block, in chain order.

        fromBlock is the first block not included in the balance. toBlock is
        the head read after that balance, so a transfer mined during the read
        is included once.
        """
        if int(start_block) > int(end_block):
            return []
        topic = '0x' + str(wallet).lower().removeprefix('0x').rjust(64, '0')
        if len(topic) != 66:
            raise ValueError('wallet')
        found = {}
        for topics in (
            [TRANSFER_SINGLE_TOPIC, None, None, topic],
            [TRANSFER_SINGLE_TOPIC, None, topic, None],
        ):
            raw = self._rpc('eth_getLogs', [{
                'address': CTF_TOKEN,
                'fromBlock': hex(int(start_block)),
                'toBlock': hex(int(end_block)),
                'topics': topics,
            }])
            if not isinstance(raw, list):
                raise RuntimeError('logs missing')
            for entry in raw:
                parsed = _parse_transfer(entry, int(start_block))
                if not parsed or str(parsed['token_id']) != str(int(token_id)):
                    continue
                tx = str(entry.get('transactionHash') or '').lower()
                if not tx.startswith('0x'):
                    continue
                parsed['tx'] = tx
                found[(tx, int(parsed['log_index']))] = parsed
        return sorted(found.values(), key=lambda item: (int(item['block']), int(item['log_index'])))


def _parse_transfer(log, block):
    if not isinstance(log, dict) or log.get('removed'):
        return None
    if str(log.get('address') or '').lower() != CTF_TOKEN.lower():
        return None
    topics = [str(topic).lower() for topic in log.get('topics') or []]
    if len(topics) != 4 or topics[0] != TRANSFER_SINGLE_TOPIC.lower():
        return None
    data = str(log.get('data') or '0x')
    if len(data) < 2 + 128:
        return None
    try:
        body = data[2:]
        index = log.get('logIndex', '0x0')
        if isinstance(index, str) and index.startswith('0x'):
            log_index = int(index, 16)
        else:
            log_index = int(index)
        raw_block = log.get('blockNumber')
        if isinstance(raw_block, str) and raw_block.startswith('0x'):
            log_block = int(raw_block, 16)
        elif isinstance(raw_block, int):
            log_block = raw_block
        else:
            log_block = block
        return {
            'log_index': log_index,
            'token_id': str(int(body[0:64], 16)),
            'from': '0x' + topics[2][-40:],
            'to': '0x' + topics[3][-40:],
            'shares': format(Decimal(int(body[64:128], 16)) / SHARES_SCALE, 'f'),
            'block': log_block,
        }
    except (TypeError, ValueError):
        return None


def _safe_error(error):
    return type(error).__name__[:80]


def ensure_receipt_schema(db):
    db.execute(
        '''CREATE TABLE IF NOT EXISTS wallet_source_receipts (
             tx TEXT PRIMARY KEY, block TEXT, ok INTEGER NOT NULL, body TEXT)''')


def _load_receipt(store, tx):
    key = tx.lower()
    with store.connect() as db:
        ensure_receipt_schema(db)
        row = db.execute(
            'SELECT block, ok, body FROM wallet_source_receipts WHERE tx=?', (key,)).fetchone()
    if not row:
        return None
    try:
        logs = json.loads(row['body'])
    except (TypeError, ValueError):
        return None
    return {'block': int(row['block']), 'ok': bool(row['ok']), 'logs': logs}


def _save_receipt(store, tx, parsed):
    with store.connect() as db:
        ensure_receipt_schema(db)
        db.execute(
            '''INSERT OR REPLACE INTO wallet_source_receipts(tx, block, ok, body)
               VALUES (?,?,?,?)''',
            (tx.lower(), str(parsed['block']), 1 if parsed['ok'] else 0,
             json.dumps(parsed['logs'])))


def _side_hit(log, wallet, side):
    sender = str(log.get('from') or '').lower()
    receiver = str(log.get('to') or '').lower()
    if sender == receiver:
        return False
    if side == 'BUY':
        return receiver == wallet and sender != receiver
    if side == 'SELL':
        return sender == wallet and sender != ZERO_ADDRESS
    return False


def _match_log(parsed, wallet, token, side, api_size):
    if not parsed or not parsed.get('ok'):
        return 'ignored' if parsed and not parsed.get('ok') else None
    wallet = wallet.lower()
    token = str(int(token))
    hits = [log for log in parsed['logs']
            if str(log.get('token_id')) == token and _side_hit(log, wallet, side)]
    if len(hits) == 1:
        return hits[0]
    if api_size is not None:
        exact = [log for log in hits if _dec(log.get('shares')) == api_size]
        if len(exact) == 1:
            return exact[0]
    if len(hits) > 1:
        return 'ambiguous'
    return None


def _cached_or_fetch(store, reader, tx):
    cached = _load_receipt(store, tx)
    if cached is not None:
        return cached, False
    parsed = reader.transfers(tx)
    if parsed is None:
        return None, True
    _save_receipt(store, tx, parsed)
    return parsed, True


class _StaleSnapshot(Exception):
    """A transfer landed after the balance read and before the book was saved."""


def _activity_rows(db, wallet, since):
    ready = db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='wallet_activity'"
    ).fetchone()
    if not ready:
        return []
    return db.execute(
        '''SELECT event_key, source_ts, body FROM wallet_activity
           WHERE wallet=? AND first_seen>=?''',
        (wallet, since)).fetchall()


def _events_from_rows(rows, wallet, token):
    events = []
    blocked = False
    for row in rows:
        try:
            event = json.loads(row['body'])
        except (TypeError, ValueError):
            blocked = True
            continue
        if str(event.get('asset') or '') != str(token):
            continue
        if event.get('type') != 'TRADE' or event.get('side') not in ('BUY', 'SELL'):
            continue
        events.append({
            'event_key': row['event_key'],
            'source_ts': row['source_ts'],
            'side': event['side'],
            'size': event.get('size'),
            'tx': str(event.get('transactionHash') or ''),
            'wallet': wallet,
            'token': str(token),
        })
    return events, blocked


def _load_events(store, wallet, token, since, db=None):
    if db is None:
        with store.connect() as db:
            rows = _activity_rows(db, wallet, since)
    else:
        rows = _activity_rows(db, wallet, since)
    return _events_from_rows(rows, wallet, token)


def _place(store, reader, wallet, token, block, events):
    placed = []
    blocked = False
    fresh = 0
    seen = set()
    for event in events:
        tx = event['tx']
        if not tx.startswith('0x'):
            blocked = True
            continue
        try:
            cached = _load_receipt(store, tx)
            if cached is None:
                if fresh >= MAX_NEW_RECEIPTS:
                    blocked = True
                    continue
                parsed, fetched = _cached_or_fetch(store, reader, tx)
                if fetched:
                    fresh += 1
            else:
                parsed = cached
        except Exception:
            blocked = True
            continue
        if parsed is None:
            blocked = True
            continue
        if parsed['block'] <= block:
            continue
        if not parsed['ok']:
            continue
        matched = _match_log(parsed, wallet, token, event['side'], _dec(event.get('size')))
        if matched in (None, 'ambiguous'):
            blocked = True
            continue
        if matched == 'ignored':
            continue
        ident = (tx.lower(), int(matched['log_index']))
        if ident in seen:
            blocked = True
            continue
        seen.add(ident)
        shares = _dec(matched.get('shares'))
        cursor = order_cursor(parsed['block'], matched['log_index'])
        if shares is None or shares <= 0 or cursor is None:
            blocked = True
            continue
        placed.append({
            'event_key': event['event_key'],
            'side': event['side'],
            'shares': shares,
            'cursor': cursor,
        })
    placed.sort(key=lambda item: (item['cursor'], item['event_key']))
    return placed, blocked


def _drop_reapplied(db, wallet, token, end):
    rows = db.execute(
        '''SELECT event_key, known, source_ts FROM wallet_source_events
           WHERE wallet=? AND token=?''',
        (wallet, token)).fetchall()
    for row in rows:
        ts = _dec(row['source_ts'])
        if row['known'] and ts is not None and ts <= end:
            continue
        db.execute(
            'DELETE FROM wallet_source_events WHERE wallet=? AND event_key=?',
            (wallet, row['event_key']))


def _log_side(log, wallet):
    wallet = wallet.lower()
    sender = str(log.get('from') or '').lower()
    receiver = str(log.get('to') or '').lower()
    if sender == receiver:
        return None
    if receiver == wallet:
        return 'BUY'
    if sender == wallet and sender != ZERO_ADDRESS:
        return 'SELL'
    return None


def _commit_anchor(store, wallet, token, shares, block, logs):
    end = end_of_block(block)
    placed = []
    with store.connect() as db:
        ensure_source_schema(db)
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        _drop_reapplied(db, wallet, token, end)
        anchor_source_position(db, wallet, token, shares, block)
        logs = sorted(logs, key=lambda item: (int(item['block']), int(item['log_index'])))
        for item in logs:
            side = _log_side(item, wallet)
            shares_moved = _dec(item.get('shares'))
            cursor = order_cursor(item['block'], item['log_index'])
            if side is None or shares_moved is None or cursor is None or item['block'] <= block:
                continue
            key = item['tx'].lower() + ':' + str(int(item['log_index']))
            result = apply_source_trade(
                db, wallet, token, key, side, shares_moved, cursor)
            placed.append(result)
            if not result.get('known'):
                break
    with store.connect() as db:
        return source_position(db, wallet, token), placed


def reconcile_token(store, reader, wallet, token, now, head=None):
    """Balance at one confirmed block, plus every later transfer of that token."""
    if reader is None:
        return {'ok': False, 'error': 'NO_READER'}
    try:
        if head is None:
            head = int(reader.block_number())
        head = int(head)
        block = head - CONFIRMED_DEPTH
        if block < 0:
            return {'ok': False, 'error': 'NO_BLOCK'}
        raw = int(reader.token_balance_raw(wallet, token, block))
        logs = reader.transfers_after(wallet, token, block + 1, head)
    except Exception as error:
        return {'ok': False, 'error': _safe_error(error)}
    if raw < 0 or logs is None:
        return {'ok': False, 'error': 'BALANCE', 'block': block}
    shares = Decimal(raw) / SHARES_SCALE
    position, placed = _commit_anchor(store, wallet, str(token), shares, block, logs)
    if position.get('known'):
        store.set('wallet_source_anchor', {
            'at': now,
            'wallet': str(wallet)[-8:],
            'token': str(token)[-8:],
            'block': int(block),
            'shares': format(position['shares'], 'f') if position.get('shares') is not None else format(shares, 'f'),
            'applied': len(placed),
        })
        store.set('wallet_source_anchor_error', {})
    return {
        'ok': bool(position.get('known')),
        'block': int(block),
        'shares': position.get('shares'),
        'applied': len(placed),
        'error': None if position.get('known') else 'UNKNOWN',
    }


def _recent_tokens(store, now):
    """Unknown books first, then confirmed books that still have fresh trades.

    The copy queue can be behind. A later trade still has to move the source
    book, and this read does not open a copy.
    """
    with store.connect() as db:
        ready = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='wallet_activity'"
        ).fetchone()
        if not ready:
            return []
        rows = db.execute(
            '''SELECT wallet, body FROM wallet_activity
               WHERE first_seen>=? ORDER BY first_seen DESC LIMIT 400''',
            (now - LOOKBACK,)).fetchall()
        known = set()
        positions = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='wallet_source_positions'"
        ).fetchone()
        if positions:
            ensure_source_schema(db)
            for row in db.execute(
                    'SELECT wallet, token, known, anchor_at FROM wallet_source_positions'):
                if row['known'] and row['anchor_at']:
                    known.add((row['wallet'], row['token']))
    unknown = []
    refresh = []
    seen = set()
    for row in rows:
        try:
            event = json.loads(row['body'])
        except (TypeError, ValueError):
            continue
        token = str(event.get('asset') or '')
        if not token or event.get('type') != 'TRADE' or event.get('side') not in ('BUY', 'SELL'):
            continue
        key = (row['wallet'], token)
        if key in seen:
            continue
        seen.add(key)
        if key in known:
            if len(refresh) < REFRESH_LIMIT:
                refresh.append(key)
        elif len(unknown) < TOKEN_LIMIT:
            unknown.append(key)
    return unknown + refresh


def reconcile_recent(store, now, reader=None, environ=None):
    """Recent unknown tokens, then a refresh of confirmed tokens that just traded."""
    if reader is None:
        reader = reader_from_env(environ)
    if reader is None:
        store.set('wallet_source_anchor_error', {'at': now, 'error': 'ALCHEMY_WSS missing'})
        return []
    results = []
    for wallet, token in _recent_tokens(store, now):
        try:
            results.append(reconcile_token(store, reader, wallet, token, now))
        except Exception as error:
            results.append({'ok': False, 'error': _safe_error(error), 'wallet': str(wallet)[-8:]})
    if any(item.get('ok') for item in results):
        store.set('wallet_source_anchor_error', {})
    elif results:
        store.set('wallet_source_anchor_error', {
            'at': now, 'error': results[0].get('error') or 'UNORDERED'})
    return results


def proportion_for_transaction(store, wallet, token, tx, size=None):
    """One sell log for this wallet, token and size. A tx hash alone is not a match.

    Two fills of the same size stay unconfirmed. A different size uses its own
    log. Nothing here clears the stored balance.
    """
    wanted = _dec(size)
    if not tx or wanted is None:
        return {'proportion': None, 'known': True}
    prefix = str(tx).lower() + ':'
    with store.connect() as db:
        ready = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='wallet_source_events'"
        ).fetchone()
        if not ready:
            return {'proportion': None, 'known': True}
        rows = db.execute(
            '''SELECT event_key, side, size, proportion FROM wallet_source_events
               WHERE wallet=? AND token=? AND event_key LIKE ?''',
            (wallet, str(token), prefix + '%')).fetchall()
    matched = []
    seen = set()
    for row in rows:
        if row['side'] != 'SELL' or not row['proportion']:
            continue
        if _dec(row['size']) != wanted:
            continue
        if row['event_key'] in seen:
            continue
        seen.add(row['event_key'])
        matched.append(row)
    if len(matched) != 1:
        return {'proportion': None, 'known': True}
    return {'proportion': Decimal(matched[0]['proportion']), 'known': True}


def historical_sell_proportion(reader, wallet, token, tx, size):
    """Proportion from the balance before the sell's block, plus earlier logs.

    The balance at today's head already includes an old sell. That number is
    not the position the sell was taken from. This does not write a trade.
    """
    wanted = _dec(size)
    if reader is None or not tx or wanted is None or wanted <= 0:
        return {'proportion': None, 'known': False}
    try:
        parsed = reader.transfers(tx)
    except Exception:
        return {'proportion': None, 'known': False}
    if not parsed or not parsed.get('ok'):
        return {'proportion': None, 'known': False}
    hits = []
    for entry in parsed.get('logs') or []:
        item = dict(entry)
        item.setdefault('tx', str(tx).lower())
        item.setdefault('block', parsed.get('block'))
        if str(item.get('token_id')) != str(int(token)):
            continue
        if _log_side(item, wallet) != 'SELL':
            continue
        if _dec(item.get('shares')) != wanted:
            continue
        hits.append(item)
    if len(hits) != 1:
        return {'proportion': None, 'known': False}
    sell = hits[0]
    block = int(sell['block'])
    if block < 1:
        return {'proportion': None, 'known': False}
    try:
        raw = int(reader.token_balance_raw(wallet, token, block - 1))
        earlier = reader.transfers_after(wallet, token, block, block)
    except Exception:
        return {'proportion': None, 'known': False}
    if raw < 0 or earlier is None:
        return {'proportion': None, 'known': False}
    shares = Decimal(raw) / SHARES_SCALE
    used = set()
    for item in earlier:
        ident = (str(item.get('tx') or '').lower(), int(item['log_index']))
        if ident in used or int(item['log_index']) >= int(sell['log_index']):
            continue
        side = _log_side(item, wallet)
        moved = _dec(item.get('shares'))
        if side not in ('BUY', 'SELL') or moved is None or moved <= 0:
            return {'proportion': None, 'known': False}
        used.add(ident)
        if side == 'BUY':
            shares += moved
        elif moved > shares:
            return {'proportion': None, 'known': False}
        else:
            shares -= moved
    if shares <= 0 or wanted > shares:
        return {'proportion': None, 'known': False}
    return {
        'proportion': wanted / shares,
        'known': True,
        'block': block - 1,
        'log_index': int(sell['log_index']),
    }


def resolve_event(store, event, wallet, reader=None):
    """One receipt for a book that is already confirmed. None leaves the sell unknown."""
    if reader is None:
        reader = reader_from_env()
    if reader is None or not isinstance(event, dict):
        return None
    tx = str(event.get('transactionHash') or '')
    token = str(event.get('asset') or '')
    side = event.get('side')
    if not tx.startswith('0x') or not token or side not in ('BUY', 'SELL'):
        return None
    try:
        parsed, _fetched = _cached_or_fetch(store, reader, tx)
    except Exception:
        return None
    if not parsed or not parsed.get('ok'):
        return None
    matched = _match_log(parsed, wallet, token, side, _dec(event.get('size')))
    if not isinstance(matched, dict):
        return None
    shares = _dec(matched.get('shares'))
    if shares is None or shares <= 0:
        return None
    return {
        'blockNumber': int(parsed['block']),
        'logIndex': int(matched['log_index']),
        '_chain_shares': format(shares, 'f'),
    }
