"""Copy-critical HTTP and the single database writer.

The paper database is large. A commit on the asyncio loop freezes every
websocket handshake, and a book request stuck behind that same pool arrives
too late to copy. Book fetches use their own pool. Database work uses one
thread so writers do not queue on the loop.
"""
import threading
import time
from concurrent.futures import ThreadPoolExecutor

IO = ThreadPoolExecutor(max_workers=6, thread_name_prefix='lab-io')
# Active copy books and market terms. History, discovery and the activity
# fallback stay on IO, so a long search cannot occupy a copy slot.
COPY = ThreadPoolExecutor(max_workers=4, thread_name_prefix='lab-copy')
# Receipt reads for the five copied wallets. Separate from the book slots.
CHAIN = ThreadPoolExecutor(max_workers=2, thread_name_prefix='lab-chain')
# One writer. Long reads use READ so a ledger scan cannot sit in front of a copy.
DB = ThreadPoolExecutor(max_workers=1, thread_name_prefix='lab-db')
READ = ThreadPoolExecutor(max_workers=2, thread_name_prefix='lab-read')
# Mitch's fast lane. Its own thread, so a copy does not wait behind the
# shared writer's queue. SQLite still serialises the write itself.
MITCH = ThreadPoolExecutor(max_workers=1, thread_name_prefix='lab-mitch')

_LOCK = threading.Lock()
_BOOKS = {}
_TERMS = {}


def remember_book(token, raw, at=None):
    if not token or not isinstance(raw, dict):
        return
    if not raw.get('asks') and not raw.get('bids'):
        return
    with _LOCK:
        _BOOKS[str(token)] = (time.time() if at is None else at, raw)
        if len(_BOOKS) > 32:
            for key in sorted(_BOOKS, key=lambda item: _BOOKS[item][0])[:8]:
                _BOOKS.pop(key, None)


def cached_book(token, max_age=1.0, now=None):
    with _LOCK:
        item = _BOOKS.get(str(token))
    if not item:
        return None
    fetched, raw = item
    age = (time.time() if now is None else now) - fetched
    if age < 0 or age > max_age:
        return None
    return raw


def remember_terms(slug, raw, at=None):
    if not slug or not isinstance(raw, dict):
        return
    with _LOCK:
        _TERMS[str(slug)] = (time.time() if at is None else at, raw)


def cached_terms(slug, max_age=30.0, now=None):
    with _LOCK:
        item = _TERMS.get(str(slug))
    if not item:
        return None
    fetched, raw = item
    age = (time.time() if now is None else now) - fetched
    if age < 0 or age > max_age:
        return None
    return raw


def clear_hot_path():
    with _LOCK:
        _BOOKS.clear()
        _TERMS.clear()
        _STAGES.clear()


_STAGES = []
_LOOP_LAG = None
_ATTEMPT = threading.local()


def note_attempt(count):
    _ATTEMPT.n = int(count)


def measured_call(fn, url, submitted):
    """Run fn on a pool thread. The wait to start is not the HTTP time."""
    note_attempt(1)
    pool_ms = (time.perf_counter() - float(submitted)) * 1000
    started = time.perf_counter()
    try:
        raw = fn(url)
    except Exception:
        http_ms = (time.perf_counter() - started) * 1000
        note_stage({
            'pool_ms': round(pool_ms, 1),
            'http_ms': round(http_ms, 1),
            'tries': getattr(_ATTEMPT, 'n', 1),
            'cache': False,
            'error': True,
        })
        raise
    http_ms = (time.perf_counter() - started) * 1000
    stage = {
        'pool_ms': round(pool_ms, 1),
        'http_ms': round(http_ms, 1),
        'tries': getattr(_ATTEMPT, 'n', 1),
        'cache': False,
    }
    note_stage(stage)
    return raw, stage


def fetch_copy(url):
    """Book and terms for a live copy. One retry, except a rate limit.

    Two seconds is the cap on one attempt. A 429 is the provider's limit and
    is not retried.
    """
    from .worker import get_json
    last = None
    for attempt in range(2):
        note_attempt(attempt + 1)
        try:
            return get_json(url, timeout=2, attempts=1)
        except Exception as error:
            last = error
            text = str(error)
            if '429' in text or '403' in text or attempt == 1:
                raise
    raise last


def note_stage(sample):
    if not isinstance(sample, dict):
        return
    with _LOCK:
        _STAGES.append(dict(sample))
        del _STAGES[:-40]


def latest_stage():
    with _LOCK:
        return dict(_STAGES[-1]) if _STAGES else {}


def note_loop_lag(milliseconds):
    global _LOOP_LAG
    with _LOCK:
        _LOOP_LAG = milliseconds


def _queued(pool):
    try:
        return pool._work_queue.qsize()
    except Exception:
        return None


def snapshot():
    with _LOCK:
        stage = dict(_STAGES[-1]) if _STAGES else {}
        lag = _LOOP_LAG
    return {
        'loop_lag_ms': None if lag is None else round(lag, 1),
        'copy_queued': _queued(COPY),
        'io_queued': _queued(IO),
        'db_queued': _queued(DB),
        'read_queued': _queued(READ),
        'chain_queued': _queued(CHAIN),
        'pool_ms': stage.get('pool_ms'),
        'http_ms': stage.get('http_ms'),
        'tries': stage.get('tries'),
        'db_wait_ms': stage.get('db_wait_ms'),
        'db_write_ms': stage.get('db_write_ms'),
        'cache': stage.get('cache'),
    }
