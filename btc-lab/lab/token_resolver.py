"""Resolve Polymarket CLOB token IDs to market metadata (conditionId, slug, side).

On-chain TransferSingle events contain raw token IDs (large integers). This resolver
maps them to market metadata via Gamma API, with persistent SQLite cache.
"""
import json
import logging
import re
import time

LOG = logging.getLogger('btc-lab.resolver')

GAMMA_TOKEN_URL = 'https://gamma-api.polymarket.com/markets?clob_token_ids={token_id}'
CACHE_TTL = 86400
NEGATIVE_TTL = 3600


class TokenResolver:
    def __init__(self, store, fetch, clock=time.time):
        self.store = store
        self.fetch = fetch
        self.clock = clock
        self._cache = {}
        with store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS token_cache (token_id TEXT PRIMARY KEY, body TEXT NOT NULL, fetched_at REAL NOT NULL)')

    def _get(self, token_id):
        key = str(token_id)
        now = self.clock()
        if key in self._cache:
            info, at = self._cache[key]
            ttl = NEGATIVE_TTL if info.get('status') == 'NOT_POLYMARKET' else CACHE_TTL
            if now - at < ttl: return info
        with self.store.connect() as db:
            row = db.execute('SELECT body, fetched_at FROM token_cache WHERE token_id=?', (key,)).fetchone()
        if row:
            info = json.loads(row[0])
            ttl = NEGATIVE_TTL if info.get('status') == 'NOT_POLYMARKET' else CACHE_TTL
            if now - row[1] < ttl:
                self._cache[key] = (info, row[1])
                return info
        return None

    def _put(self, token_id, info):
        key = str(token_id)
        now = self.clock()
        self._cache[key] = (info, now)
        with self.store.connect() as db:
            db.execute('INSERT OR REPLACE INTO token_cache VALUES (?,?,?)', (key, json.dumps(info), now))

    async def resolve(self, token_id):
        cached = self._get(token_id)
        if cached is not None:
            return None if cached.get('status') == 'NOT_POLYMARKET' else cached
        try:
            import asyncio
            results = await asyncio.to_thread(self.fetch, GAMMA_TOKEN_URL.format(token_id=token_id))
            if not isinstance(results, list) or not results:
                self._put(token_id, {'status': 'NOT_POLYMARKET', 'token_id': str(token_id)})
                return None
            raw = results[0]
            slug = raw.get('slug', '')
            match = re.fullmatch(r'(btc|eth)-updown-(5m|15m)-(\d+)', slug)
            if not match:
                self._put(token_id, {'status': 'NOT_POLYMARKET', 'token_id': str(token_id), 'slug': slug})
                return None
            names = json.loads(raw['outcomes']) if isinstance(raw.get('outcomes'), str) else raw.get('outcomes', [])
            tokens = json.loads(raw['clobTokenIds']) if isinstance(raw.get('clobTokenIds'), str) else raw.get('clobTokenIds', [])
            if len(names) != 2 or set(names) != {'Up', 'Down'} or len(tokens) != 2:
                self._put(token_id, {'status': 'INVALID_MAPPING'})
                return None
            mapping = dict(zip(map(str, tokens), names))
            side = mapping.get(str(token_id))
            if not side:
                self._put(token_id, {'status': 'TOKEN_NOT_IN_MARKET'})
                return None
            asset, interval, start_str = match.groups()
            info = {'status': 'RESOLVED', 'slug': slug, 'conditionId': str(raw.get('conditionId', '')),
                    'side': side, 'asset': str(token_id), 'interval': interval,
                    'start': int(start_str), 'end': int(start_str) + (300 if interval == '5m' else 900),
                    'token_mapping': mapping, 'all_tokens': {v: k for k, v in mapping.items()}}
            self._put(token_id, info)
            return info
        except Exception as e:
            LOG.warning('resolve %s failed: %s', token_id, str(e)[:200])
            return None
