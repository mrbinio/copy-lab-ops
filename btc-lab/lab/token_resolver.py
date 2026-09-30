"""Resolve Polymarket CLOB token IDs to market metadata (conditionId, slug, side).

On-chain OrderFilled events contain raw token IDs (large integers). WalletCopy
needs slug, conditionId, and asset (token ID as string) to process signals.

This resolver maintains a persistent SQLite cache to avoid repeated API lookups.
Cache entries expire after 24 hours; active markets are refreshed more frequently.
"""
import json
import logging
import re
import time

LOG = logging.getLogger('btc-lab.resolver')

# Gamma API for market lookup by token
GAMMA_TOKEN_URL = 'https://gamma-api.polymarket.com/markets?clob_token_ids={token_id}'
# CLOB API for token → condition mapping
CLOB_TOKEN_URL = 'https://clob.polymarket.com/markets/{condition_id}'

CACHE_TTL = 86400       # 24h for resolved entries
ACTIVE_TTL = 900        # 15min for active markets (re-check accepting status)
NEGATIVE_TTL = 3600     # 1h for "not a polymarket token" entries


class TokenResolver:
    """Translates CLOB token IDs to market metadata with persistent cache.

    Usage:
        resolver = TokenResolver(store, fetch)
        info = await resolver.resolve(token_id_int)
        # info = {'slug': 'btc-updown-15m-...', 'conditionId': '...', 'side': 'Up', ...}
        # or None if token is not a recognized Polymarket market
    """

    def __init__(self, store, fetch, clock=time.time):
        """
        Args:
            store: Core Store instance (provides SQLite connection)
            fetch: async-compatible fetch function (same as used in worker.py)
            clock: time source (for testing)
        """
        self.store = store
        self.fetch = fetch
        self.clock = clock
        self._memory_cache = {}  # token_id (int) → {info, fetched_at}
        self._init_db()

    def _init_db(self):
        with self.store.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS token_cache (
                token_id TEXT PRIMARY KEY,
                body TEXT NOT NULL,
                fetched_at REAL NOT NULL
            )''')

    def _get_cached(self, token_id):
        """Check memory cache, then SQLite. Returns info dict or None."""
        key = str(token_id)
        now = self.clock()

        # Memory cache first
        mem = self._memory_cache.get(key)
        if mem and now - mem['fetched_at'] < CACHE_TTL:
            return mem['info']

        # SQLite fallback
        with self.store.connect() as db:
            row = db.execute('SELECT body, fetched_at FROM token_cache WHERE token_id=?', (key,)).fetchone()
        if row:
            info = json.loads(row[0])
            fetched_at = row[1]
            ttl = NEGATIVE_TTL if info.get('status') == 'NOT_POLYMARKET' else CACHE_TTL
            if now - fetched_at < ttl:
                self._memory_cache[key] = {'info': info, 'fetched_at': fetched_at}
                return info

        return None

    def _set_cached(self, token_id, info):
        """Store in both memory and SQLite."""
        key = str(token_id)
        now = self.clock()
        self._memory_cache[key] = {'info': info, 'fetched_at': now}
        with self.store.connect() as db:
            db.execute('INSERT OR REPLACE INTO token_cache VALUES (?,?,?)',
                       (key, json.dumps(info, allow_nan=False), now))

    async def resolve(self, token_id):
        """Resolve a CLOB token ID to market metadata.

        Args:
            token_id: integer token ID from on-chain OrderFilled event

        Returns:
            dict with keys: slug, conditionId, side, asset (token_id as str),
                            interval, start, end, token_mapping
            or None if not a recognized BTC/ETH up-down market
        """
        cached = self._get_cached(token_id)
        if cached is not None:
            if cached.get('status') == 'NOT_POLYMARKET':
                return None
            return cached

        # Lookup via Gamma API: find market by CLOB token ID
        try:
            import asyncio
            url = GAMMA_TOKEN_URL.format(token_id=token_id)
            results = await asyncio.to_thread(self.fetch, url)

            if not isinstance(results, list) or len(results) == 0:
                self._set_cached(token_id, {'status': 'NOT_POLYMARKET', 'token_id': str(token_id)})
                return None

            raw = results[0]
            slug = raw.get('slug', '')

            # Only support BTC/ETH up-down markets
            match = re.fullmatch(r'(btc|eth)-updown-(5m|15m)-(\d+)', slug)
            if not match:
                self._set_cached(token_id, {'status': 'NOT_POLYMARKET', 'token_id': str(token_id), 'slug': slug})
                return None

            # Parse token mapping
            names = raw.get('outcomes', [])
            tokens = raw.get('clobTokenIds', [])
            if isinstance(names, str):
                names = json.loads(names)
            if isinstance(tokens, str):
                tokens = json.loads(tokens)

            if len(names) != 2 or set(names) != {'Up', 'Down'} or len(tokens) != 2:
                self._set_cached(token_id, {'status': 'INVALID_MAPPING', 'token_id': str(token_id), 'slug': slug})
                return None

            token_mapping = dict(zip(map(str, tokens), names))
            token_str = str(token_id)
            side = token_mapping.get(token_str)

            if side is None:
                # token_id might not be in this market's tokens
                self._set_cached(token_id, {'status': 'TOKEN_NOT_IN_MARKET', 'token_id': token_str, 'slug': slug})
                return None

            asset, interval, start_str = match.groups()
            start = int(start_str)
            end = start + (300 if interval == '5m' else 900)

            info = {
                'status': 'RESOLVED',
                'slug': slug,
                'conditionId': str(raw.get('conditionId', '')),
                'side': side,
                'asset': token_str,
                'interval': interval,
                'start': start,
                'end': end,
                'token_mapping': token_mapping,
            }
            self._set_cached(token_id, info)
            LOG.info('resolved token %s → %s %s', token_id, slug, side)
            return info

        except Exception as e:
            LOG.warning('token resolve failed for %s: %s', token_id, str(e)[:200])
            return None

    def cache_stats(self):
        with self.store.connect() as db:
            total = db.execute('SELECT COUNT(*) FROM token_cache').fetchone()[0]
            resolved = db.execute("SELECT COUNT(*) FROM token_cache WHERE body LIKE '%RESOLVED%'").fetchone()[0]
        return {'total': total, 'resolved': resolved, 'memory': len(self._memory_cache)}
