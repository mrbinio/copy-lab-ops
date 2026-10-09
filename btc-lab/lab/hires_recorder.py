"""High-resolution recorder for research. It records; it never trades.

Damian, 9 Oct 2026: a week of millisecond data to test two ideas the 25 s
book snapshots cannot: does Binance lead the Polymarket book, and can a
resting (maker) order earn the spread after adverse fills.

Sources, each to its own hourly gzip file under data/hires/YYYY-MM-DD/:
  polymarket  CLOB market channel for BTC 5m and 15m, current and next
              window: book, price_change, last_trade_price, raw
  binance     BTCUSDT trade and bookTicker
  coinbase    BTC-USD ticker, as a second reference
  rtds        Polymarket RTDS crypto prices and Chainlink TWAP
  meta        token -> slug map at every refresh

A line is `<local receive time in ns>\\t<raw message>`, except price_change,
which is one compact line per change (see compact_polymarket). Limits: 14 days, 10 GB, and no writing below 8 GB free disk.
Runs as its own launchd process (com.btc-lab.recorder), apart from the copier.
"""
import asyncio
import gzip
import json
import logging
import os
import shutil
import sys
import time
import urllib.request
from pathlib import Path

LOG = logging.getLogger('btc-lab.recorder')
KEEP_DAYS = 14
MAX_BYTES = 10 * 1024 ** 3
MIN_FREE = 8 * 1024 ** 3
FLUSH_EVERY = 5
STATUS_EVERY = 30
CLOB = 'wss://ws-subscriptions-clob.polymarket.com/ws/market'
BINANCE = 'wss://stream.binance.com:9443/stream?streams=btcusdt@trade/btcusdt@bookTicker'
COINBASE = 'wss://ws-feed.exchange.coinbase.com'
RTDS = 'wss://ws-live-data.polymarket.com'


class Sink:
    """Hourly gzip files per source, with disk limits."""

    def __init__(self, root, clock=time.time, disk=shutil.disk_usage):
        self.root = Path(root)
        self.clock = clock
        self.disk = disk
        self.files = {}
        self.counts = {}
        self.last = {}
        self.paused = None
        self._flushed = clock()

    def _path(self, source, now):
        stamp = time.gmtime(now)
        return self.root / time.strftime('%Y-%m-%d', stamp) / ('%s-%s.jsonl.gz' % (time.strftime('%H', stamp), source))

    def write(self, source, raw, received_ns=None):
        if self.paused:
            return False
        now = self.clock()
        path = self._path(source, now)
        current = self.files.get(source)
        if current is None or current[0] != path:
            if current is not None:
                current[1].close()
            path.parent.mkdir(parents=True, exist_ok=True)
            current = (path, gzip.open(path, 'at', compresslevel=5))
            self.files[source] = current
        text = raw if isinstance(raw, str) else raw.decode('utf-8', 'replace')
        current[1].write('%d\t%s\n' % (received_ns or time.time_ns(), text.replace('\n', ' ')))
        self.counts[source] = self.counts.get(source, 0) + 1
        self.last[source] = now
        if now - self._flushed >= FLUSH_EVERY:
            self.flush()
        return True

    def write_line(self, source, line):
        """A line that already carries its own receive time."""
        if self.paused:
            return False
        now = self.clock()
        path = self._path(source, now)
        current = self.files.get(source)
        if current is None or current[0] != path:
            if current is not None:
                current[1].close()
            path.parent.mkdir(parents=True, exist_ok=True)
            current = (path, gzip.open(path, 'at', compresslevel=5))
            self.files[source] = current
        current[1].write(line + '\n')
        self.counts[source] = self.counts.get(source, 0) + 1
        self.last[source] = now
        if now - self._flushed >= FLUSH_EVERY:
            self.flush()
        return True

    def flush(self):
        for _path, handle in self.files.values():
            handle.flush()
        self._flushed = self.clock()

    def close(self):
        for _path, handle in self.files.values():
            handle.close()
        self.files = {}

    def used(self):
        return sum(p.stat().st_size for p in self.root.rglob('*.gz')) if self.root.exists() else 0

    def housekeep(self):
        """Drop days past the limit, then the oldest days over the size cap. Pause on a full disk."""
        if self.root.exists():
            days = sorted(p for p in self.root.iterdir() if p.is_dir())
            cutoff = time.strftime('%Y-%m-%d', time.gmtime(self.clock() - KEEP_DAYS * 86400))
            for day in days:
                if day.name < cutoff:
                    shutil.rmtree(day, ignore_errors=True)
            days = sorted(p for p in self.root.iterdir() if p.is_dir())
            today = time.strftime('%Y-%m-%d', time.gmtime(self.clock()))
            while self.used() > MAX_BYTES and days and days[0].name != today:
                shutil.rmtree(days.pop(0), ignore_errors=True)
        self.root.mkdir(parents=True, exist_ok=True)
        free = self.disk(str(self.root)).free
        self.paused = 'disk_low' if free < MIN_FREE else None
        return free

    def status(self, started):
        now = self.clock()
        return {
            'at': now, 'started_at': started, 'paused': self.paused,
            'counts': dict(self.counts),
            'last_age_s': {k: round(now - v, 1) for k, v in self.last.items()},
            'bytes': self.used(),
            'limits': {'keep_days': KEEP_DAYS, 'max_bytes': MAX_BYTES, 'min_free_bytes': MIN_FREE},
        }


def compact_polymarket(raw, received_ns, tops=None):
    """price_change is ~95% of the channel (about 1,900 a second on 9 Oct).
    Kept: a change at the best bid or ask, and any change that moves them,
    one short line each: token (last 12 digits; full ids are in meta),
    price, size, side, new best bid, new best ask, venue time. Deeper levels
    are dropped (81%); full `book` messages stay raw for depth."""
    try:
        message = json.loads(raw)
    except ValueError:
        return None
    items = message if isinstance(message, list) else [message]
    if not items or any(not isinstance(x, dict) or x.get('event_type') != 'price_change' for x in items):
        return None
    lines = []
    for item in items:
        stamp = item.get('timestamp') or ''
        for change in item.get('price_changes') or []:
            token = str(change.get('asset_id') or '')[-12:]
            top = (change.get('best_bid'), change.get('best_ask'))
            at_best = (change.get('side') == 'BUY' and change.get('price') == top[0]) or \
                      (change.get('side') == 'SELL' and change.get('price') == top[1])
            if tops is not None:
                moved = tops.get(token) != top
                tops[token] = top
                if not (at_best or moved):
                    continue
            lines.append('%d\tPC\t%s\t%s\t%s\t%s\t%s\t%s\t%s' % (
                received_ns, token, change.get('price'), change.get('size'),
                change.get('side'), change.get('best_bid'), change.get('best_ask'), stamp))
    return lines


def window_tokens(fetch, now=None):
    """Tokens of BTC 5m and 15m, current and next window, with their slugs."""
    now = int(now or time.time())
    out = {}
    for interval, length in (('5m', 300), ('15m', 900)):
        start = now - now % length
        for begin in (start, start + length):
            slug = 'btc-updown-%s-%d' % (interval, begin)
            try:
                market = fetch('https://gamma-api.polymarket.com/markets/slug/' + slug)
            except Exception:
                continue
            tokens = market.get('clobTokenIds') if isinstance(market, dict) else None
            if isinstance(tokens, str):
                try:
                    tokens = json.loads(tokens)
                except ValueError:
                    tokens = None
            for token in tokens or []:
                out[str(token)] = slug
    return out


def get_json(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'BTC-Lab-Recorder/1.0'})
    with urllib.request.urlopen(request, timeout=10) as reply:
        return json.loads(reply.read().decode())


async def _forever(name, run):
    import random
    delay = 1
    while True:
        try:
            await run()
            delay = 1
        except asyncio.CancelledError:
            raise
        except Exception as error:
            LOG.info('%s: %s', name, str(error)[:160])
        await asyncio.sleep(delay + random.random())
        delay = min(delay * 2, 30)


async def record_polymarket(sink, fetch=get_json):
    import websockets
    loop = asyncio.get_running_loop()
    tokens = await loop.run_in_executor(None, window_tokens, fetch)
    if not tokens:
        raise RuntimeError('no window tokens')
    sink.write('meta', json.dumps({'tokens': tokens}))
    async with websockets.connect(CLOB, open_timeout=15, ping_interval=None, max_size=None) as ws:
        await ws.send(json.dumps({'assets_ids': list(tokens), 'type': 'market', 'custom_feature_enabled': True}))
        last_ping = last_refresh = time.monotonic()
        tops = {}
        while True:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=5)
            except asyncio.TimeoutError:
                raw = None
            received = time.time_ns()
            if raw and raw not in ('PONG', 'PING'):
                lines = compact_polymarket(raw, received, tops)
                if lines is None:
                    sink.write('polymarket', raw, received)
                else:
                    for line in lines:
                        sink.write_line('polymarket', line)
            mono = time.monotonic()
            if mono - last_ping >= 10:
                await ws.send('PING')
                last_ping = mono
            if mono - last_refresh >= 20:
                last_refresh = mono
                fresh = await loop.run_in_executor(None, window_tokens, fetch)
                if fresh and set(fresh) != set(tokens):
                    # A new subscription on a fresh socket keeps the stream clean.
                    sink.write('meta', json.dumps({'tokens': fresh}))
                    return


async def record_binance(sink):
    import websockets
    async with websockets.connect(BINANCE, open_timeout=15, ping_interval=20, max_size=None) as ws:
        async for raw in ws:
            sink.write('binance', raw, time.time_ns())


async def record_coinbase(sink):
    import websockets
    async with websockets.connect(COINBASE, open_timeout=15, ping_interval=20, max_size=None) as ws:
        await ws.send(json.dumps({'type': 'subscribe', 'product_ids': ['BTC-USD'], 'channels': ['ticker']}))
        async for raw in ws:
            sink.write('coinbase', raw, time.time_ns())


async def record_rtds(sink):
    import websockets
    async with websockets.connect(RTDS, open_timeout=15, ping_interval=5, max_size=None) as ws:
        # Same subscription as the worker's reference feed, plus Polymarket's
        # Binance relay so both clocks sit on one timeline.
        chainlink = json.dumps({'symbol': 'btc/usd'}, separators=(',', ':'))
        await ws.send(json.dumps({'action': 'subscribe', 'subscriptions': [
            {'topic': 'crypto_prices_chainlink', 'type': '*', 'filters': chainlink},
            {'topic': 'crypto_prices_twap_sixty', 'type': 'update', 'filters': chainlink},
            {'topic': 'crypto_prices', 'type': 'update', 'filters': json.dumps({'symbol': 'btcusdt'}, separators=(',', ':'))},
        ]}))
        async for raw in ws:
            sink.write('rtds', raw, time.time_ns())


async def main(root):
    base = Path(root)
    sink = Sink(base / 'data' / 'hires')
    status_path = base / 'logs' / 'recorder-status.json'
    started = time.time()
    sink.housekeep()
    tasks = [asyncio.create_task(_forever(name, lambda run=run: run(sink))) for name, run in (
        ('polymarket', record_polymarket), ('binance', record_binance),
        ('coinbase', record_coinbase), ('rtds', record_rtds),
    )]
    try:
        while True:
            await asyncio.sleep(STATUS_EVERY)
            sink.flush()
            sink.housekeep()
            body = json.dumps(sink.status(started))
            tmp = status_path.with_suffix('.tmp')
            tmp.write_text(body)
            os.replace(tmp, status_path)
    finally:
        for task in tasks:
            task.cancel()
        sink.close()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s:%(name)s:%(message)s')
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else str(Path.home() / 'Library/Application Support/BTC Lab')))
