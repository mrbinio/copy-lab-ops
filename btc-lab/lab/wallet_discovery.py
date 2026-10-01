"""Hourly public CRYPTO leaderboard shortlist. Candidates are never auto-copied."""
import asyncio
import json
import math
import re
import time
from urllib.parse import urlencode

from .wallet_observer import ensure_active_wallets_table, SEED_WALLETS

# Promotion criteria: positive PnL both week AND month, week volume > 1000.
MIN_WEEK_VOLUME = 1000


def score_candidate(candidate):
    """Estimate a win-rate score from leaderboard data.

    Uses a simple heuristic: normalized PnL relative to volume as a proxy
    for edge. Higher is better, range roughly 0-1.
    """
    week_pnl = candidate.get('week_reported_pnl', 0)
    month_pnl = candidate.get('month_reported_pnl', 0)
    week_vol = candidate.get('week_volume', 1)
    month_vol = candidate.get('month_volume', 1)
    if week_vol <= 0 or month_vol <= 0:
        return 0.0
    # Edge estimate: average of week and month PnL/volume ratios, clamped to [0, 1]
    week_edge = max(0, week_pnl / week_vol)
    month_edge = max(0, month_pnl / month_vol)
    return min(1.0, (week_edge + month_edge) / 2)


def promote(store, wallet, score=0.0):
    """Add a wallet to active_wallets with source='discovery'."""
    ensure_active_wallets_table(store)
    with store.connect() as db:
        db.execute('INSERT OR IGNORE INTO active_wallets VALUES (?,?,?,?,?)',
                   (wallet, 'discovery', time.time(), score, 0))
        # Update score if already exists
        db.execute('UPDATE active_wallets SET score=? WHERE wallet=? AND source=?',
                   (score, wallet, 'discovery'))


def demote(store, wallet):
    """Remove a discovery wallet from active_wallets. Seed wallets cannot be demoted."""
    if wallet in SEED_WALLETS:
        return
    with store.connect() as db:
        db.execute("DELETE FROM active_wallets WHERE wallet=? AND source='discovery'",
                   (wallet,))


class WalletDiscovery:
    def __init__(self, store, fetch):
        self.store, self.fetch = store, fetch
        with store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS wallet_discovery_scans (ts REAL PRIMARY KEY, body TEXT NOT NULL)')

    @staticmethod
    def parse(rows):
        if not isinstance(rows,list): raise ValueError('Invalid leaderboard response')
        out={}
        for row in rows:
            wallet=str(row.get('proxyWallet','')).lower()
            if not re.fullmatch(r'0x[0-9a-f]{40}',wallet): raise ValueError('Invalid wallet')
            pnl,vol=float(row['pnl']),float(row['vol'])
            if not math.isfinite(pnl) or not math.isfinite(vol) or vol<0: raise ValueError('Invalid leaderboard amount')
            out[wallet]={'wallet':wallet,'name':str(row.get('userName',''))[:100],'pnl':pnl,'volume':vol}
        return out

    async def scan(self):
        previous=self.store.get('wallet_discovery',{})
        try:
            periods={}
            for period in ('WEEK','MONTH'):
                query=urlencode(dict(category='CRYPTO',timePeriod=period,orderBy='PNL',limit=50,offset=0))
                periods[period]=self.parse(await asyncio.to_thread(self.fetch,'https://data-api.polymarket.com/v1/leaderboard?'+query))
            candidates=[]
            for wallet,w in periods['WEEK'].items():
                m=periods['MONTH'].get(wallet)
                if m and w['pnl']>0 and m['pnl']>0 and w['volume']>0 and m['volume']>0:
                    candidates.append({'wallet':wallet,'name':w['name'],'week_reported_pnl':w['pnl'],
                        'month_reported_pnl':m['pnl'],'week_volume':w['volume'],'month_volume':m['volume'],
                        'status':'UNVERIFIED_CANDIDATE','copy_enabled':False})
            now=time.time()

            # Auto-promote candidates meeting stricter criteria into active_wallets
            for c in candidates:
                if (c['week_reported_pnl'] > 0 and c['month_reported_pnl'] > 0
                        and c['week_volume'] > MIN_WEEK_VOLUME):
                    score = score_candidate(c)
                    promote(self.store, c['wallet'], score)

            state={'status':'SCAN_OK','checked_at':now,'last_success_at':now,'interval_seconds':3600,
                'category':'CRYPTO','scope':'Top 50 WEEK and MONTH by reported PNL; intersection with positive PNL and volume',
                'candidates':candidates,'copy_enabled':False,
                'limitation':'Leaderboard PnL is not independently reconciled profit. Overlapping periods, selection bias, open inventory, fees and delayed copy execution need forward verification.',
                'error':None}
            with self.store.connect() as db:
                db.execute('INSERT INTO wallet_discovery_scans VALUES (?,?)',(now,json.dumps(state)))
            self.store.set('wallet_discovery',state)
        except Exception as error:
            self.store.set('wallet_discovery',{**previous,'status':'ERROR','checked_at':time.time(),
                'error':str(error)[:300],'copy_enabled':False})

    async def run(self):
        while True:
            await self.scan()
            await asyncio.sleep(3600)
