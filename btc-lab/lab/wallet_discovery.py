"""Hourly 30-day shortlist. Candidates are never auto-copied."""
import asyncio
import json
import math
import re
import time
from urllib.parse import urlencode

from .wallet_observer import ensure_active_wallets_table, SEED_WALLETS

OUR_MARKETS = re.compile(r'^(btc|eth)-updown-(5m|15m)-')
LOOKBACK = 30 * 86400
MIN_MONTH_VOLUME = 1000
MAX_PROBE = 8
MIN_OUR_TRADES = 10
MIN_OUR_SHARE = 0.25


def our_slug(slug):
    return bool(OUR_MARKETS.match(str(slug or '')))


def score_candidate(candidate):
    """Keep the old helper for tests that imported it; no longer used to promote."""
    month_pnl = candidate.get('month_reported_pnl') or candidate.get('week_reported_pnl') or 0
    month_vol = candidate.get('month_volume') or candidate.get('week_volume') or 1
    if month_vol <= 0:
        return 0.0
    return min(1.0, max(0, month_pnl / month_vol))


def promote(store, wallet, score=0.0):
    """No-op. Auto-copy from the public table is how we got a losing extra wallet."""
    return


def demote(store, wallet):
    """Remove a discovery wallet from active_wallets. Seed wallets cannot be demoted."""
    if wallet in SEED_WALLETS:
        return
    with store.connect() as db:
        db.execute("DELETE FROM active_wallets WHERE wallet=? AND source='discovery'",
                   (wallet,))


def prune_discovery_rows(store):
    """Drop leftover discovery rows. Copy watches seeds only."""
    ensure_active_wallets_table(store)
    with store.connect() as db:
        db.execute("DELETE FROM active_wallets WHERE source='discovery'")


def market_stats(rows):
    trades = [r for r in rows if isinstance(r, dict) and str(r.get('type', '')).upper() == 'TRADE']
    ours = [r for r in trades if our_slug(r.get('slug'))]
    n = len(trades)
    return {
        'trades_30d': n,
        'our_trades_30d': len(ours),
        'our_share_30d': (len(ours) / n) if n else 0.0,
    }


class WalletDiscovery:
    def __init__(self, store, fetch):
        self.store, self.fetch = store, fetch
        with store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS wallet_discovery_scans (ts REAL PRIMARY KEY, body TEXT NOT NULL)')

    @staticmethod
    def parse(rows):
        if not isinstance(rows, list): raise ValueError('Invalid leaderboard response')
        out = {}
        for row in rows:
            wallet = str(row.get('proxyWallet', '')).lower()
            if not re.fullmatch(r'0x[0-9a-f]{40}', wallet): raise ValueError('Invalid wallet')
            pnl, vol = float(row['pnl']), float(row['vol'])
            if not math.isfinite(pnl) or not math.isfinite(vol) or vol < 0: raise ValueError('Invalid leaderboard amount')
            out[wallet] = {'wallet': wallet, 'name': str(row.get('userName', ''))[:100], 'pnl': pnl, 'volume': vol}
        return out

    async def probe_activity(self, wallet, now):
        start, end = int(now - LOOKBACK), int(now)
        collected = []
        try:
            for page in range(3):
                query = urlencode(dict(user=wallet, start=start, end=end, limit=500, offset=page * 500,
                                       sortBy='TIMESTAMP', sortDirection='DESC'))
                rows = await asyncio.to_thread(self.fetch, 'https://data-api.polymarket.com/activity?' + query)
                if not isinstance(rows, list):
                    break
                collected.extend(rows)
                if len(rows) < 500:
                    break
        except Exception:
            return {'trades_30d': None, 'our_trades_30d': None, 'our_share_30d': None, 'probe': 'ERROR'}
        stats = market_stats(collected)
        stats['probe'] = 'OK'
        return stats

    async def scan(self):
        previous = self.store.get('wallet_discovery', {})
        try:
            now = time.time()
            month_q = urlencode(dict(category='CRYPTO', timePeriod='MONTH', orderBy='PNL', limit=50, offset=0))
            week_q = urlencode(dict(category='CRYPTO', timePeriod='WEEK', orderBy='PNL', limit=50, offset=0))
            month = self.parse(await asyncio.to_thread(self.fetch, 'https://data-api.polymarket.com/v1/leaderboard?' + month_q))
            week = {}
            try:
                week = self.parse(await asyncio.to_thread(self.fetch, 'https://data-api.polymarket.com/v1/leaderboard?' + week_q))
            except Exception:
                week = {}
            ranked = sorted((w for w in month.values() if w['pnl'] > 0 and w['volume'] > MIN_MONTH_VOLUME),
                            key=lambda w: w['pnl'], reverse=True)
            candidates = []
            for i, w in enumerate(ranked[:20]):
                wk = week.get(w['wallet'], {})
                row = {'wallet': w['wallet'], 'name': w['name'],
                       'month_reported_pnl': w['pnl'], 'month_volume': w['volume'],
                       'week_reported_pnl': wk.get('pnl'), 'week_volume': wk.get('volume'),
                       'qualify_days': 30, 'copy_enabled': False, 'status': 'SHORTLIST_30D'}
                if i < MAX_PROBE:
                    stats = await self.probe_activity(w['wallet'], now)
                    row.update(stats)
                    if stats.get('probe') == 'OK':
                        if (stats['our_trades_30d'] or 0) >= MIN_OUR_TRADES and (stats['our_share_30d'] or 0) >= MIN_OUR_SHARE:
                            row['status'] = 'TRADES_OUR_MARKETS'
                        else:
                            row['status'] = 'WRONG_MARKETS'
                candidates.append(row)
            prune_discovery_rows(self.store)
            state = {'status': 'SCAN_OK', 'checked_at': now, 'last_success_at': now, 'interval_seconds': 3600,
                     'category': 'CRYPTO', 'qualify_days': 30,
                     'scope': 'Top 50 MONTH by reported PNL; 30-day window; top 8 probed for BTC/ETH 5m/15m share',
                     'candidates': candidates, 'copy_enabled': False,
                     'limitation': 'Leaderboard month PnL is not copy profit. A wallet is only a candidate after 30 days of our-market trades. Nobody is auto-copied.',
                     'error': None}
            with self.store.connect() as db:
                db.execute('INSERT INTO wallet_discovery_scans VALUES (?,?)', (now, json.dumps(state)))
            self.store.set('wallet_discovery', state)
            try:
                from .wallet_roster import tick as roster_tick
                stats = {}
                for c in candidates:
                    if c.get('status') == 'TRADES_OUR_MARKETS':
                        stats[c['wallet']] = {
                            'our_trades': c.get('our_trades_30d') or 0,
                            'windows': c.get('our_trades_30d') or 0,
                            'age_days': 30,
                            'copy_sim_net_usd': None,
                            'best_day_share': None,
                        }
                roster_tick(self.store, now, stats)
            except Exception:
                pass
        except Exception as error:
            self.store.set('wallet_discovery', {**previous, 'status': 'ERROR', 'checked_at': time.time(),
                                                'error': str(error)[:300], 'copy_enabled': False})

    async def run(self):
        while True:
            await self.scan()
            await asyncio.sleep(3600)
