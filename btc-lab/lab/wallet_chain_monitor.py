"""On-chain detection + aggressive Data API poll for source execution price.

Non-blocking, bounded task queue, per-row dedup (not per-txHash).
"""
import asyncio
import hashlib
import json
import logging
import threading
import time
import urllib.parse
from decimal import Decimal

LOG = logging.getLogger('btc-lab.chain')

CTF_TOKEN = '0x4D97DCd97eC945f40cF65F87097ACe5EA0476045'
TRANSFER_SINGLE_TOPIC = '0xc3d58168c5ae7397731d063d5bbf3d657854427343f4c083240f7aacaa2d0f62'
DATA_API = 'https://data-api.polymarket.com'

# Seen operating real seed fills. Informational only: the relayer address
# rotates, so matching must never depend on this set.
EXCHANGE_OPERATORS = {
    '0x4bfb41d5b3570defd03c39a9a4d8de6bd8b8982e',
    '0xc5d563a36ae78145c45a50134d48a1215220f80a',
    '0xe111180000d2663c0091e4f400237545b87b996b',
}
ZERO_ADDRESS = '0x' + '0' * 40

POLL_TIMEOUT = 2
POLL_INTERVAL = 0.5
_TRADE_LOCK = threading.Lock()
_TRADES = {}


def note_market_trade(message):
    """Remember a public last_trade_price so a wallet's chain transfer can use it.

    The print has a price and a transaction hash. It does not name the wallet.
    It is used only when the hash and the token amount match that wallet's transfer.
    """
    if not isinstance(message, dict):
        return
    nested = message.get('trade') if isinstance(message.get('trade'), dict) else {}
    tx = str(
        message.get('transaction_hash') or message.get('transactionHash') or message.get('tx_hash')
        or nested.get('transaction_hash') or nested.get('transactionHash') or ''
    ).lower()
    if not tx:
        if not getattr(note_market_trade, 'shape_logged', False):
            note_market_trade.shape_logged = True
            LOG.info('last_trade_price has no transaction hash; keys=%s', sorted(message)[:24])
        return
    try:
        price = Decimal(str(message.get('price')))
        size = Decimal(str(message.get('size')))
        ts = float(message.get('timestamp') or 0)
    except Exception:
        return
    if not price.is_finite() or not size.is_finite() or price <= 0 or size <= 0:
        return
    if ts > 10_000_000_000:
        ts = ts / 1000
    item = {
        'asset': str(message.get('asset_id') or message.get('asset') or ''),
        'price': price, 'size': size, 'ts': ts,
        'side': message.get('side'),
    }
    with _TRADE_LOCK:
        bucket = _TRADES.setdefault(tx, [])
        bucket.append(item)
        if len(_TRADES) > 4000:
            for old in list(_TRADES)[:1000]:
                _TRADES.pop(old, None)


def confirmed_print(tx, token, shares):
    """VWAP of prints for this transaction and token, only if the size matches."""
    try:
        wanted = Decimal(str(shares))
    except Exception:
        return None
    if wanted <= 0:
        return None
    with _TRADE_LOCK:
        rows = list(_TRADES.get(str(tx).lower(), []))
    rows = [row for row in rows if row['asset'] == str(token)]
    if not rows:
        return None
    total = sum((row['size'] for row in rows), Decimal(0))
    if abs(total - wanted) > Decimal('0.000001'):
        return None
    usdc = sum((row['price'] * row['size'] for row in rows), Decimal(0))
    return {
        'price': usdc / total,
        'size': total,
        'usdc': usdc,
        'ts': min(row['ts'] for row in rows if row['ts']),
    }
# A seed can fill ten times inside one block. Off-market events now return at
# once, so the queue only holds short book lookups.
MAX_PENDING_TASKS = 120


def parse_transfer_single(log):
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
    """Classify on who receives or sends the token.

    The operator is not a gate. Polymarket routes fills through rotating
    relayer addresses, so an allowlist silently dropped every seed fill.
    ChainBridge gates on the open market window instead.
    """
    if event['to'] in wallets_lower and event['from'] != event['to']:
        return event['to'], 'BUY'
    if event['from'] in wallets_lower and event['from'] != ZERO_ADDRESS:
        return event['from'], 'SELL'
    return None, None


def _row_key(source_row):
    """Dedup by trade identity, not price. Chain can insert before Data API."""
    fields = {k: source_row.get(k) for k in (
        'transactionHash', 'type', 'asset', 'side')}
    return hashlib.sha256(json.dumps(fields, sort_keys=True, allow_nan=False).encode()).hexdigest()


class ChainMonitor:
    """Non-blocking WebSocket monitor with bounded task queue."""

    def __init__(self, wss_url, wallets, on_event, clock=time.time):
        self.urls = [wss_url] if isinstance(wss_url, str) else [u for u in wss_url if u]
        if not self.urls:
            self.urls = ['wss://rpc-polygon.blockmachine.io']
        self.wss_url = self.urls[0]
        self._url_i = 0
        self._backoff = 1
        self.wallets = {w.lower() for w in wallets}
        self.on_event = on_event
        self.clock = clock
        self.events_seen = 0
        self.events_matched = 0
        self.events_dropped = 0
        self.errors = 0
        self.connected_at = None
        self.last_block = 0
        self._tasks = set()

    def status(self):
        return {'mode': 'CHAIN_FAST', 'connected': self.connected_at is not None,
                'last_block': self.last_block, 'events_seen': self.events_seen,
                'events_matched': self.events_matched, 'errors': self.errors,
                'events_dropped': self.events_dropped, 'pending_tasks': len(self._tasks),
                'wss_host': self.wss_url.split('://',1)[-1].split('/',1)[0]}

    def update_wallets(self, new_set):
        """Update the set of monitored wallets at runtime."""
        self.wallets = {w.lower() for w in new_set}

    async def run(self):
        import websockets
        while True:
            self.connected_at = None
            self.wss_url = self.urls[self._url_i % len(self.urls)]
            try:
                async with websockets.connect(self.wss_url, open_timeout=8, close_timeout=3,
                                               max_size=5_000_000, ping_interval=20, ping_timeout=10) as ws:
                    self.connected_at = self.clock()
                    self._backoff = 1
                    LOG.info('chain monitor connected %s', self.wss_url.split('://',1)[-1].split('/',1)[0])
                    sub = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'eth_subscribe',
                                      'params': ['logs', {'address': CTF_TOKEN, 'topics': [TRANSFER_SINGLE_TOPIC]}]})
                    await ws.send(sub)
                    resp = json.loads(await ws.recv())
                    if 'result' not in resp:
                        await asyncio.sleep(5); continue
                    async for message in ws:
                        if isinstance(message, bytes): message = message.decode()
                        try: data = json.loads(message)
                        except json.JSONDecodeError: continue
                        if data.get('method') != 'eth_subscription': continue
                        result = data.get('params', {}).get('result')
                        if not isinstance(result, dict): continue
                        event = parse_transfer_single(result)
                        if event is None:
                            continue
                        if event.get('removed'):
                            wallet, side = classify_transfer(event, self.wallets)
                            drop = getattr(self, 'on_removed', None)
                            if wallet is not None and drop is not None:
                                event.update(wallet=wallet, side=side, detected_at=self.clock())
                                task = asyncio.create_task(self._safe_drop(event))
                                self._tasks.add(task)
                                task.add_done_callback(self._tasks.discard)
                            continue
                        self.events_seen += 1
                        self.last_block = max(self.last_block, event['block_number'])
                        wallet, side = classify_transfer(event, self.wallets)
                        if wallet is None: continue
                        self.events_matched += 1
                        # Observed and paused names do not take a slot that a
                        # copied wallet may need in the same block.
                        want = getattr(self, 'want', None)
                        if want is not None and not want(wallet):
                            self.not_copied = getattr(self, 'not_copied', 0) + 1
                            continue
                        event.update(wallet=wallet, side=side, detected_at=self.clock())
                        # Bounded queue: drop if too many pending
                        if len(self._tasks) >= MAX_PENDING_TASKS:
                            self.events_dropped += 1
                            if self.clock() - getattr(self, '_drop_logged', 0) >= 5:
                                self._drop_logged = self.clock()
                                LOG.warning('queue full (%d), dropped %d', len(self._tasks), self.events_dropped)
                            continue
                        task = asyncio.create_task(self._safe_handle(event))
                        self._tasks.add(task)
                        task.add_done_callback(self._tasks.discard)
            except asyncio.CancelledError:
                for t in self._tasks: t.cancel()
                raise
            except Exception as e:
                self.errors += 1; self.connected_at = None
                self._url_i += 1
                LOG.warning('chain disconnected: %s', str(e)[:200])
                await asyncio.sleep(self._backoff)
                from .feed_watchdog import next_backoff
                self._backoff = next_backoff(self._backoff)

    async def _safe_handle(self, event):
        try:
            await asyncio.wait_for(self.on_event(event), timeout=6)
        except asyncio.TimeoutError:
            self.errors += 1
        except Exception as e:
            self.errors += 1
            LOG.warning('handler: %s', str(e)[:200])

    async def _safe_drop(self, event):
        drop = getattr(self, 'on_removed', None)
        if drop is None:
            return
        try:
            await asyncio.wait_for(drop(event), timeout=2)
        except Exception as e:
            self.errors += 1
            LOG.warning('reorg: %s', str(e)[:200])


class ChainBridge:
    """Poll Data API for confirmed source price. Per-row dedup, not per-txHash.

    Does NOT skip entire txHash — always polls API and inserts any new rows.
    Dedup is per individual fill (same key as REST observer).
    """

    def __init__(self, store, fetch, clock=time.time, sleep=asyncio.sleep):
        self.store = store
        self.fetch = fetch
        self.clock = clock
        self.sleep = sleep
        self.bridged = 0
        self.skipped = 0
        self.timeouts = 0
        self.off_market = 0
        self._windows = []
        self._windows_at = 0
        self._window_lock = threading.Lock()

    def _current_windows(self):
        now = self.clock()
        if now - self._windows_at < 15 and self._windows:
            return self._windows
        found = []
        for asset in ('btc', 'eth'):
            for interval, dur in (('5m', 300), ('15m', 900)):
                start = int(now) // dur * dur
                slug = f'{asset}-updown-{interval}-{start}'
                try:
                    raw = self.fetch(f'https://gamma-api.polymarket.com/markets/slug/{slug}')
                except Exception:
                    continue
                if not isinstance(raw, dict):
                    continue
                tokens = raw.get('clobTokenIds')
                if isinstance(tokens, str):
                    try:
                        tokens = json.loads(tokens)
                    except json.JSONDecodeError:
                        continue
                if not tokens:
                    continue
                found.append({'slug': slug, 'conditionId': raw.get('conditionId'),
                              'tokens': {str(t) for t in tokens}})
        if found:
            self._windows = found
            self._windows_at = now
            return found
        return self._windows  # keep the last good set through a gamma hiccup

    def _window_for(self, token):
        if not token:
            return None
        # One refresh at a time. The other matches use the cache they already
        # have instead of each opening four market requests.
        if self.clock() - self._windows_at >= 15 and self._window_lock.acquire(blocking=False):
            try:
                if self.clock() - self._windows_at >= 15:
                    self._current_windows()
            finally:
                self._window_lock.release()
        return next((m for m in self._windows if token in m['tokens']), None)

    def _insert(self, wallet, source_row, detected_at, label):
        now = self.clock()
        ts = float(source_row.get('timestamp', now))
        key = _row_key(source_row)
        source_row['_detected_at'] = detected_at
        body = json.dumps(source_row, allow_nan=False)
        rank = {'chain_fast': 0, 'chain_accelerated': 1, 'market_trade': 2, 'order_filled': 3, 'clob_match': 4}
        with self.store.connect() as db:
            existing = db.execute(
                'SELECT body FROM wallet_activity WHERE wallet=? AND event_key=?',
                (wallet, key),
            ).fetchone()
            if not existing:
                db.execute(
                    'INSERT INTO wallet_activity VALUES (?,?,?,?,?)',
                    (wallet, key, now, ts, body),
                )
                wrote = True
            else:
                old = json.loads(existing[0] or '{}')
                new_rank = rank.get(source_row.get('_source'), 1)
                old_rank = rank.get(old.get('_source'), 1)
                if new_rank <= old_rank:
                    return False
                db.execute(
                    'UPDATE wallet_activity SET source_ts=?, body=? WHERE wallet=? AND event_key=?',
                    (ts, body, wallet, key),
                )
                wrote = True
            if wrote:
                self.bridged += 1
                LOG.info('%s: %s %s @ %s', label, source_row.get('side', '?'),
                         wallet[-8:], source_row.get('price'))
                ready = getattr(self.store, 'wallet_activity_ready', None)
                if ready is not None and hasattr(ready, 'set'):
                    ready.set()
                return True
        return False

    def _order_fill_row(self, event, meta):
        """Price and size from OrderFilled in this transaction. None falls back."""
        from .order_fill import execution_from_receipt
        from .source_chain import TokenBalanceReader, _post, reader_from_env
        reader = reader_from_env()
        url = reader.url if reader is not None else 'https://rpc-polygon.blockmachine.io'

        def post(target, payload, timeout=8):
            return _post(target, payload, timeout=1.0)

        # The age of a copy is counted from his trade. The match print has it
        # in ms. Without a print the block time is the next best, and it is
        # never later than the trade it carries. Our own detection time is
        # not his trade time and is marked so a buy cannot pass on it.
        token = str(event.get('token_id') or '')
        printed = confirmed_print(event.get('tx_hash'), token, event.get('value', 0) / 1e6)
        try:
            parsed = execution_from_receipt(
                TokenBalanceReader(url, post=post), event, want_block=not printed,
            )
        except Exception:
            return None
        if not parsed:
            return None
        fill, block_ts, rpc_ms = parsed
        detected_at = event.get('detected_at', self.clock())
        provider = None
        if printed and printed.get('ts'):
            stamp = float(printed['ts'])
            basis = 'match'
            provider = detected_at - stamp
        elif block_ts and 0 <= detected_at - block_ts <= 30:
            stamp = float(block_ts)
            basis = 'block'
            provider = detected_at - stamp
        else:
            stamp = detected_at
            basis = 'local_detect'
        return {
            'transactionHash': event['tx_hash'],
            'type': 'TRADE',
            'side': fill['side'],
            'proxyWallet': event['wallet'],
            'slug': meta['slug'],
            'conditionId': meta['conditionId'],
            'asset': str(event.get('token_id') or ''),
            'size': format(fill['size'], 'f'),
            'usdcSize': format(fill['usdc'], 'f'),
            'price': format(fill['price'], 'f'),
            'timestamp': stamp,
            '_source': 'order_filled',
            '_fee': format(fill['fee'], 'f'),
            '_fills': fill['fills'],
            '_rpc_ms': round(rpc_ms, 1),
            '_provider_delay_s': None if provider is None else round(provider, 3),
            '_ts_basis': basis,
            '_block': event.get('block_number'),
        }

    async def on_removed(self, event):
        from .hot_path import DB
        await asyncio.get_running_loop().run_in_executor(DB, self._drop_reorg, event)

    def _drop_reorg(self, event):
        """A removed log is not an execution. An undecided row is dropped.

        A copy that already ran stays in the paper book. It is noted, not replayed.
        """
        token = str(event.get('token_id') or '')
        key = _row_key({
            'transactionHash': event.get('tx_hash'),
            'type': 'TRADE',
            'asset': token,
            'side': event.get('side'),
        })
        wallet = event['wallet']
        note = None
        with self.store.connect() as db:
            decided = None
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='mitch_events'").fetchone():
                decided = db.execute(
                    'SELECT reason FROM mitch_events WHERE wallet=? AND event_key=?',
                    (wallet, key),
                ).fetchone()
            copied = None
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='wallet_copy_events'").fetchone():
                copied = db.execute(
                    "SELECT reason FROM wallet_copy_events WHERE wallet=? AND event_key=? AND reason!='PROCESSING'",
                    (wallet, key),
                ).fetchone()
            if decided or copied:
                note = (decided or copied)[0]
            else:
                db.execute(
                    'DELETE FROM wallet_activity WHERE wallet=? AND event_key=?',
                    (wallet, key),
                )
        if note:
            self.store.set('chain_reorg_after_copy', {
                'at': self.clock(), 'wallet': wallet, 'tx': event.get('tx_hash'),
                'reason': note,
            })
            return False
        return True

    def _fast_row(self, event, meta):
        token = str(event.get('token_id') or '')
        shares = event.get('value', 0) / 1e6
        printed = confirmed_print(event.get('tx_hash'), token, shares)
        detected_at = event.get('detected_at', self.clock())
        base = {
            'transactionHash': event['tx_hash'],
            'type': 'TRADE',
            'side': event['side'],
            'proxyWallet': event['wallet'],
            'slug': meta['slug'],
            'conditionId': meta['conditionId'],
            'asset': token,
            'size': shares,
        }
        if printed:
            base.update(
                timestamp=printed['ts'] or detected_at,
                price=format(printed['price'], 'f'),
                usdcSize=format(printed['usdc'], 'f'),
                _source='market_trade',
            )
            return base
        from .hot_path import cached_book, remember_book
        book = cached_book(token, 1.0, self.clock())
        if book is None:
            try:
                book = self.fetch('https://clob.polymarket.com/book?token_id=' + urllib.parse.quote(token, safe=''))
            except Exception:
                return None
            if book.get('asks'):
                remember_book(token, book, self.clock())
        if not isinstance(book, dict):
            return None
        asks = book.get('asks') or []
        if not asks:
            return None
        try:
            price = min(float(a['price']) for a in asks if isinstance(a, dict) and a.get('price') is not None)
        except ValueError:
            return None
        base.update(timestamp=detected_at, price=price, _source='chain_fast')
        return base

    def _confirm(self, wallet, source_row, detected_at):
        """Replace a book quote with the API row, or insert the API row."""
        from .wallet_observer import merge_activity_body
        now = self.clock()
        ts = float(source_row.get('timestamp', now))
        key = _row_key(source_row)
        source_row['_detected_at'] = detected_at
        with self.store.connect() as db:
            existing = db.execute(
                'SELECT body FROM wallet_activity WHERE wallet=? AND event_key=?',
                (wallet, key),
            ).fetchone()
            if not existing:
                db.execute(
                    'INSERT INTO wallet_activity VALUES (?,?,?,?,?)',
                    (wallet, key, now, ts, json.dumps(source_row, allow_nan=False)),
                )
                self.bridged += 1
            elif json.loads(existing[0]).get('_source') in ('order_filled', 'clob_match'):
                # The receipt is the execution. A later public row does not replace it.
                return False
            else:
                merged, did = merge_activity_body(existing[0], source_row)
                if not did:
                    return False
                db.execute(
                    'UPDATE wallet_activity SET source_ts=?, body=? WHERE wallet=? AND event_key=?',
                    (ts, merged, wallet, key),
                )
        ready = getattr(self.store, 'wallet_activity_ready', None)
        if ready is not None and hasattr(ready, 'set'):
            ready.set()
        return True

    def _worth_accelerating(self, wallet):
        """Chain inserts only for a wallet we would actually copy.

        Paused and observed names stay on the slower public list. Their
        transfers do not take a database write ahead of a live copy.
        """
        from .mitch_copy import WALLETS
        if wallet in WALLETS:
            return True
        now = self.clock()
        if now - getattr(self, '_roster_at', 0) >= 5:
            roster = (self.store.get('wallet_roster') or {}).get('wallets') or {}
            self._copying = {
                name for name, row in roster.items()
                if (row or {}).get('state') in ('paper_test', 'paper_active')
            }
            self._roster_at = now
        return wallet in getattr(self, '_copying', ())

    async def on_event(self, event):
        wallet = event['wallet']
        tx_hash = event.get('tx_hash', '')
        if not tx_hash:
            self.skipped += 1; return
        if not self._worth_accelerating(wallet):
            self.off_market += 1
            return

        detected_at = event.get('detected_at', self.clock())

        # Only trades on an open 5m/15m window can be copied. Everything else
        # (hourly markets, share transfers) must not occupy the poll queue.
        from .hot_path import IO
        from .mitch_copy import WALLETS as MITCH_WALLETS
        loop = asyncio.get_running_loop()
        meta = await loop.run_in_executor(IO, self._window_for, str(event.get('token_id') or ''))
        if meta is None:
            self.off_market += 1
            return

        try:
            filled = None
            if wallet in MITCH_WALLETS:
                from .hot_path import CHAIN
                filled = await loop.run_in_executor(CHAIN, self._order_fill_row, event, meta)
            if filled:
                from .hot_path import DB
                await loop.run_in_executor(
                    DB, self._insert, wallet, filled, detected_at, 'order-filled',
                )
                return
            fast = await loop.run_in_executor(IO, self._fast_row, event, meta)
            if fast:
                from .hot_path import DB
                await loop.run_in_executor(
                    DB, self._insert, wallet, fast, detected_at, 'chain-fast',
                )
        except Exception as e:
            LOG.debug('fast path miss: %s', str(e)[:120])

        timeout = 0.85 if wallet in MITCH_WALLETS else POLL_TIMEOUT
        interval = 0.05 if wallet in MITCH_WALLETS else POLL_INTERVAL
        deadline = detected_at + timeout
        source_rows = None

        # Poll until the receipt names the fill. For Mitch the public list is
        # not a buy price. Retry the receipt inside one second.
        while self.clock() < deadline:
            if wallet in MITCH_WALLETS:
                try:
                    from .hot_path import CHAIN, DB
                    filled = await loop.run_in_executor(CHAIN, self._order_fill_row, event, meta)
                    if filled:
                        await loop.run_in_executor(
                            DB, self._insert, wallet, filled, detected_at, 'order-filled',
                        )
                        return
                except Exception as error:
                    LOG.debug('receipt retry: %s', str(error)[:100])
            try:
                api_rows = await loop.run_in_executor(IO, self._poll_activity, wallet, detected_at)
                source_rows = [r for r in (api_rows or [])
                               if isinstance(r, dict) and r.get('transactionHash') == tx_hash]
                if source_rows:
                    break
            except Exception as e:
                LOG.debug('poll retry: %s', str(e)[:100])
            before = self.clock()
            await self.sleep(interval)
            # A frozen clock must not spin. Production time moves during the wait.
            if self.clock() <= before:
                break

        if not source_rows:
            self.timeouts += 1
            self.store.record('chain_timeout', {'wallet': wallet, 'tx': tx_hash,
                              'side': event['side'], 'block': event.get('block_number')})
            return

        now = self.clock()
        for source_row in source_rows:
            source_row['_source'] = 'chain_accelerated'
            source_row['_chain_to_api_seconds'] = now - detected_at
            from .hot_path import DB
            await asyncio.get_running_loop().run_in_executor(
                DB, self._confirm, wallet, source_row, detected_at,
            )

    def _poll_activity(self, wallet, since):
        start = max(0, int(since) - 30)
        end = int(self.clock()) + 5
        from .data_api import fetch_rows
        rows, _cursor = fetch_rows(self.fetch, 'activity', user=wallet, start=start, end=end,
                                   limit=100, sortBy='TIMESTAMP', sortDirection='DESC')
        return rows

    def status(self):
        return {'bridged': self.bridged, 'skipped': self.skipped, 'timeouts': self.timeouts,
                'off_market': self.off_market}


def _print_tokens(raw, stamp):
    if not isinstance(raw, dict):
        return []
    from .worker import normalize_market
    try:
        market = normalize_market(raw, stamp, 'BTC')
    except (ValueError, KeyError, TypeError):
        return []
    return [str(token) for token in market['tokens'].values()]


async def _window_tokens(fetch):
    from .hot_path import IO
    now = int(time.time())
    start = now - (now % 900)
    ids = []
    loop = asyncio.get_running_loop()
    from .fast_match import remember_window
    for stamp in (start, start + 900):
        slug = 'btc-updown-15m-%s' % stamp
        raw = await loop.run_in_executor(
            IO, fetch, 'https://gamma-api.polymarket.com/markets/slug/' + slug,
        )
        tokens = _print_tokens(raw, stamp)
        for token in tokens:
            remember_window(token, slug, raw.get('conditionId') if isinstance(raw, dict) else None)
        ids.extend(tokens)
    return ids


def run_market_prints_thread(fetch, fast=None):
    """The market channel on its own thread and loop.

    On the worker loop a database stall stopped reads long enough for the
    server to close with 1013 slow consumer, and opening handshakes timed
    out. This socket is the start of the fast lane, so it waits for nothing.
    """
    asyncio.run(run_market_prints(fetch, fast=fast))


async def run_market_prints(fetch, sleep=asyncio.sleep, fast=None):
    """Public market channel. Stays up across windows. A print is not a wallet until the transfer matches."""
    import websockets
    url = 'wss://ws-subscriptions-clob.polymarket.com/ws/market'
    while True:
        try:
            ids = await _window_tokens(fetch)
            if not ids:
                await sleep(5)
                continue
            async with websockets.connect(url, open_timeout=15, ping_interval=None) as ws:
                subscribed = tuple(ids[:8])
                await ws.send(json.dumps({
                    'assets_ids': list(subscribed), 'type': 'market', 'custom_feature_enabled': True,
                }))
                last_ping = time.monotonic()
                last_refresh = last_ping
                quiet = 0
                while True:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=10)
                    except asyncio.TimeoutError:
                        # A quiet book is not a dead socket. Ask, and leave
                        # only after thirty seconds without a word.
                        quiet += 1
                        if quiet >= 3:
                            raise
                        await ws.send('PING')
                        last_ping = time.monotonic()
                        continue
                    quiet = 0
                    now_m = time.monotonic()
                    if now_m - last_ping >= 10:
                        await ws.send('PING')
                        last_ping = now_m
                    if now_m - last_refresh >= 20:
                        last_refresh = now_m
                        fresh = tuple((await _window_tokens(fetch))[:8])
                        if fresh and fresh != subscribed:
                            subscribed = fresh
                            await ws.send(json.dumps({
                                'assets_ids': list(subscribed), 'type': 'market',
                                'custom_feature_enabled': True,
                            }))
                    if raw in ('PONG', 'PING', ''):
                        if raw == 'PING':
                            await ws.send('PONG')
                        continue
                    # Hundreds of book changes a second arrive here; only trade
                    # prints are used. Parsing the rest held the GIL and starved
                    # the worker loop (heartbeat 35 s, healthz 503, 9 Oct).
                    if '"event_type":"last_trade_price"' not in raw and '"event_type": "last_trade_price"' not in raw:
                        continue
                    try:
                        msg = json.loads(raw)
                    except ValueError:
                        continue
                    rows = msg if isinstance(msg, list) else [msg]
                    for item in rows:
                        if isinstance(item, dict) and item.get('event_type') == 'last_trade_price':
                            note_market_trade(item)
                            if fast is not None:
                                fast.note(item)
        except Exception as error:
            LOG.info('market prints: %s', str(error)[:160])
            await sleep(2)
