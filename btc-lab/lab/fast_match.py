"""Fast lane: a match print, the pending exchange transaction, a decision.

Measured on 9 Oct 2026 on BTC 15m:
  print arrival vs its match time   about 0 s (the print is the match)
  pending tx readable after print   about 70 ms
  chain log after print             1.4 s median, 2.0 s p90
  RTDS activity after chain log     about 1 s

The market channel names the transaction but not the wallet. The pending
transaction names every order in the match. A watched wallet in it goes
straight to its copier, without waiting for the chain or the database poll.
Nothing here places an order.
"""
import asyncio
import http.client
import json
import logging
import threading
import time
from urllib.parse import urlsplit
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

from .match_decoder import decode_match, wallet_fills

LOG = logging.getLogger('btc-lab.fast')
PUBLIC_RPC = ('https://rpc-polygon.blockmachine.io', 'https://polygon.drpc.org')
RESOLVE_DEADLINE = 0.6
RETRY_EVERY = 0.04
MAX_INFLIGHT = 48
RPC_POOL = ThreadPoolExecutor(max_workers=12, thread_name_prefix='lab-fast')
# Mitch trades only BTC 15m. Since 10 Oct the lane also reads ETH and 5m
# prints for the qualifier; those must not queue in front of his.
PRIORITY_POOL = ThreadPoolExecutor(max_workers=16, thread_name_prefix='lab-fast-btc15')


def _priority(item):
    meta = window_of(item.get('asset_id')) if isinstance(item, dict) else None
    return bool(meta) and str(meta[0]).startswith('btc-updown-15m-')
_TOKENS = {}
CURRENT = None


def remember_window(token, slug, condition, outcome=None):
    """Slug, condition and outcome of a token the market channel is subscribed to."""
    _TOKENS[str(token)] = (str(slug), str(condition or ''), outcome)
    if len(_TOKENS) > 128:
        for old in list(_TOKENS)[:32]:
            _TOKENS.pop(old, None)


def window_of(token):
    return _TOKENS.get(str(token))


def rpc_urls(environ=None):
    from .source_chain import http_url_from_wss
    import os
    environ = os.environ if environ is None else environ
    urls = []
    private = http_url_from_wss(environ.get('ALCHEMY_WSS') or '')
    if private:
        urls.append(private)
    urls.extend(url for url in PUBLIC_RPC if url not in urls)
    return tuple(urls)


_LOCAL = threading.local()


def _lookup(url, tx):
    """eth_getTransactionByHash on a kept-alive connection of this pool thread.
    A fresh TLS connection per try cost ~90 ms on every 40 ms retry."""
    conns = getattr(_LOCAL, 'conns', None)
    if conns is None:
        conns = _LOCAL.conns = {}
    parts = urlsplit(url)
    conn = conns.get(url)
    if conn is None:
        conn = conns[url] = http.client.HTTPSConnection(parts.hostname, parts.port, timeout=0.5)
    body = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'eth_getTransactionByHash', 'params': [tx]})
    path = parts.path or '/'
    if parts.query:
        path += '?' + parts.query
    try:
        conn.request('POST', path, body, {'User-Agent': 'BTC-Lab-Paper/0.1', 'Content-Type': 'application/json',
                                           'Accept': 'application/json'})
        reply = json.loads(conn.getresponse().read(2_000_001))
    except Exception:
        conns.pop(url, None)
        conn.close()
        raise RuntimeError('%s: no response' % (parts.hostname or 'rpc')) from None
    return reply.get('result') if isinstance(reply, dict) else reply


def activity_row(leg, tx, match_ts, arrived, resolved_at, meta):
    """The fill as a wallet_activity body. usdcSize includes his fee like the public list."""
    slug, condition = meta[0], meta[1]
    outcome = meta[2] if len(meta) > 2 else None
    return {
        'transactionHash': tx,
        'type': 'TRADE',
        'side': leg['side'],
        'proxyWallet': leg['wallet'],
        'slug': slug,
        'conditionId': condition,
        'asset': leg['token'],
        'outcome': outcome,
        'size': format(leg['shares'], 'f'),
        'usdcSize': format(leg['usdc'] + leg['fee'], 'f'),
        'price': format(leg['price'], 'f'),
        'timestamp': match_ts,
        '_source': 'clob_match',
        '_ts_basis': 'match',
        '_fee': format(leg['fee'], 'f'),
        '_role': leg['role'],
        '_signed_at': leg['signed_at'],
        '_print_at': arrived,
        '_resolve_ms': round((resolved_at - arrived) * 1000, 1),
    }


class FastMatch:
    def __init__(self, wallets, sink, urls=None, lookup=_lookup, clock=time.time, sleep=asyncio.sleep):
        self.wallets = {str(w).lower() for w in wallets}
        self.sink = sink
        self.urls = tuple(urls or rpc_urls())
        self.lookup = lookup
        self.clock = clock
        self.sleep = sleep
        self._seen = OrderedDict()
        self._inflight = set()
        self.counts = {'prints': 0, 'resolved': 0, 'missed': 0, 'other_shape': 0,
                       'watched': 0, 'dropped': 0, 'errors': 0}
        self._resolve_ms = []

    def set_wallets(self, wallets):
        """Replace the watched set (Mitch plus the qualifier's copying wallets)."""
        self.wallets = {str(w).lower() for w in wallets}

    def note(self, item, arrived=None):
        """Called for each last_trade_price. Never blocks the socket loop."""
        if not isinstance(item, dict):
            return None
        tx = str(item.get('transaction_hash') or '').lower()
        if not tx or tx in self._seen:
            return None
        self._seen[tx] = True
        if len(self._seen) > 5000:
            self._seen.popitem(last=False)
        self.counts['prints'] += 1
        priority = _priority(item)
        if len(self._inflight) >= MAX_INFLIGHT and not priority:
            self.counts['dropped'] += 1
            return None
        try:
            match_ts = float(item.get('timestamp') or 0)
        except (TypeError, ValueError):
            match_ts = 0
        if match_ts > 10_000_000_000:
            match_ts /= 1000
        arrived = self.clock() if arrived is None else arrived
        task = asyncio.ensure_future(self.resolve(tx, match_ts or arrived, arrived,
                                                  PRIORITY_POOL if priority else RPC_POOL))
        self._inflight.add(task)
        task.add_done_callback(self._inflight.discard)
        return task

    async def _poll(self, url, tx, deadline, pool):
        loop = asyncio.get_running_loop()
        while True:
            try:
                found = await loop.run_in_executor(pool, self.lookup, url, tx)
            except Exception:
                found = None
            if isinstance(found, dict) and found.get('input'):
                return found
            if self.clock() >= deadline:
                return None
            await self.sleep(RETRY_EVERY)

    async def _race(self, tx, deadline, pool=RPC_POOL):
        """Each endpoint retries on its own; the first one that has it wins.
        10 Oct 2026: one round waited for the slower endpoint (up to 0.5 s)
        before the next try, while blockmachine had the tx in 0.12 s p50."""
        tasks = [asyncio.ensure_future(self._poll(url, tx, deadline, pool)) for url in self.urls]
        try:
            for done in asyncio.as_completed(tasks):
                found = await done
                if found:
                    return found
            return None
        finally:
            for task in tasks:
                task.cancel()

    async def resolve(self, tx, match_ts, arrived, pool=RPC_POOL):
        deadline = arrived + RESOLVE_DEADLINE
        found = await self._race(tx, deadline, pool)
        if not found:
            self.counts['missed'] += 1
            return []
        match = decode_match(dict(found, hash=tx))
        if not match:
            self.counts['other_shape'] += 1
            return []
        resolved_at = self.clock()
        self.counts['resolved'] += 1
        self._resolve_ms.append((resolved_at - arrived) * 1000)
        if len(self._resolve_ms) > 500:
            self._resolve_ms = self._resolve_ms[-500:]
        legs = wallet_fills(match, self.wallets)
        rows = []
        for leg in legs:
            meta = window_of(leg['token'])
            if meta is None:
                continue
            row = activity_row(leg, tx, match_ts, arrived, resolved_at, meta)
            rows.append(row)
            self.counts['watched'] += 1
            LOG.info('clob-match: %s %s %s @ %s in %.0f ms', leg['side'], leg['wallet'][-8:],
                     leg['shares'], leg['price'].quantize(Decimal('0.0001')), row['_resolve_ms'])
            try:
                await self.sink(leg['wallet'], row, arrived)
            except Exception as error:
                self.counts['errors'] += 1
                LOG.warning('fast sink: %s', str(error)[:200])
        return rows

    def status(self):
        values = sorted(self._resolve_ms)
        median = values[len(values) // 2] if values else None
        p90 = values[int(len(values) * 0.9)] if values else None
        return dict(self.counts, resolve_median_ms=None if median is None else round(median, 1),
                    resolve_p90_ms=None if p90 is None else round(p90, 1),
                    rpc=len(self.urls), at=self.clock())


def hand_to_loop(loop, sink):
    """A sink that runs on another loop. The lane does not wait for the copy."""
    async def handed(wallet, row, arrived):
        future = asyncio.run_coroutine_threadsafe(sink(wallet, row, arrived), loop)

        def report(done):
            if not done.cancelled() and done.exception() is not None:
                LOG.warning('fast copy: %s', str(done.exception())[:200])
        future.add_done_callback(report)
    return handed


def insert_row(store, wallet, body, detected_at):
    """Store the fill so the board, history and later rows see it. Returns the queue row."""
    from .wallet_chain_monitor import _row_key
    key = _row_key(body)
    now = time.time()
    body = dict(body, _detected_at=detected_at)
    text = json.dumps(body, allow_nan=False)
    with store.connect() as db:
        existing = db.execute(
            'SELECT first_seen, body FROM wallet_activity WHERE wallet=? AND event_key=?',
            (wallet, key),
        ).fetchone()
        if existing:
            old = json.loads(existing[1] or '{}')
            if old.get('_source') in ('clob_match', 'order_filled'):
                return None
            db.execute(
                'UPDATE wallet_activity SET source_ts=?, body=? WHERE wallet=? AND event_key=?',
                (float(body['timestamp']), text, wallet, key),
            )
            first_seen = float(existing[0])
        else:
            db.execute(
                'INSERT INTO wallet_activity VALUES (?,?,?,?,?)',
                (wallet, key, now, float(body['timestamp']), text),
            )
            first_seen = now
    return {'wallet': wallet, 'event_key': key, 'first_seen': first_seen,
            'source_ts': float(body['timestamp']), 'body': text}


def route(mitch_sink, qualifier_sink, mitch_wallets):
    """Mitch wallets go to his copier; every other watched wallet to the qualifier."""
    mitch = {str(w).lower() for w in mitch_wallets}

    async def sink(wallet, row, arrived):
        if str(wallet).lower() in mitch:
            await mitch_sink(wallet, row, arrived)
        else:
            await qualifier_sink(wallet, row, arrived)
    return sink


QUALIFIER_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix='lab-fast-q')


def qualifier_sink(store):
    """Store the fill for the qualifier's queue. It picks the row up like any source row."""
    async def sink(wallet, row, arrived):
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(QUALIFIER_POOL, insert_row, store, wallet, row, arrived)
    return sink


def copying_wallets(store, mitch_wallets):
    roster = ((store.get('wallet_roster') or {}).get('wallets') or {})
    copying = {w for w, row in roster.items() if (row or {}).get('state') in ('paper_test', 'paper_active')}
    return set(mitch_wallets) | copying
