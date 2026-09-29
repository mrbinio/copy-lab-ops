"""Hourly public CRYPTO leaderboard shortlist. Candidates are never auto-copied."""
import asyncio
import json
import math
import re
import time
from urllib.parse import urlencode

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
