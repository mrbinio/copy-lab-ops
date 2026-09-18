"""Read-only runtime diagnosis; prints no credentials and submits no orders."""
import asyncio
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import urllib.request

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from lab.worker import Worker, get_json, normalize_market, normalize_book, error_detail, GAMMA, CLOB
from lab.core import Store

def check(label, action, display=True):
    try:
        result=action()
        print(label, 'OK', result if display and result is not None else '', flush=True)
        return result
    except Exception as e:
        print(label, 'FAIL', error_detail(e), flush=True)

async def reference_probe():
    with tempfile.TemporaryDirectory() as tmp:
        worker=Worker(Store(Path(tmp)/'probe.sqlite'),tmp)
        task=asyncio.create_task(worker.reference_stream())
        try:
            deadline=time.monotonic()+15
            while time.monotonic()<deadline and not (worker.reference and 'crypto_prices_twap_sixty' in worker.reference_topics):
                await asyncio.sleep(.25)
            if worker.references.get('crypto_prices_twap_sixty'):
                print('RTDS TWAP60 OK: exact E18 BTC observation received',flush=True)
            else:
                print('RTDS TWAP60 FAIL:',worker.feed_error or 'no valid TWAP60 observation within 15 seconds',flush=True)
            print('RTDS received topics:',json.dumps(worker.reference_topics),flush=True)
        finally:
            task.cancel()
            await asyncio.gather(task,return_exceptions=True)

def main():
    root=Path.home()/'Library/Application Support/BTC Lab'
    config=json.loads((root/'config.json').read_text())
    print('BTC LAB DIAGNOSIS — '+time.strftime('%Y-%m-%d %H:%M:%S'),flush=True)
    print('Release:',config.get('revision'),'Python:',sys.version.split()[0],flush=True)
    url=f"http://127.0.0.1:{int(config['port'])}"
    print('Dashboard:',url,'Login:',config.get('username'),flush=True)
    def health():
        with urllib.request.urlopen(url+'/healthz',timeout=5) as r:return r.status
    check('Local health',health)
    def database():
        db=sqlite3.connect((root/'data/lab.sqlite').as_uri()+'?mode=ro',uri=True,timeout=3)
        try:
            for key in ('worker','reference'):
                row=db.execute('SELECT body FROM state WHERE key=?',(key,)).fetchone()
                print(key+':',row[0] if row else 'missing',flush=True)
                if key=='worker' and row:
                    print('Worker heartbeat age seconds:',round(time.time()-json.loads(row[0]).get('heartbeat',0),1),flush=True)
            row=db.execute("SELECT body FROM state WHERE key='market'").fetchone()
            if row:
                m=json.loads(row[0])
                print('Active market:',json.dumps({key:m.get(key) for key in ('slug','rule_kind','rule_supported','reference_topic','opening','feature_schema')}),flush=True)
            print('Latest decisions:',db.execute('SELECT strategy,reason FROM decisions ORDER BY id DESC LIMIT 3').fetchall(),flush=True)
        finally:db.close()
    check('Runtime state',database)
    check('CLOB time',lambda:get_json(CLOB+'/time'))
    start=int(time.time())//900*900
    raw=check('Current BTC market',lambda:get_json(f'{GAMMA}/markets/slug/btc-updown-15m-{start}'),False)
    if raw:
        market=check('Market parser',lambda:normalize_market(raw,start),False)
        if market:
            print('Rule supported:',market['rule_supported'],'Fee verified:',market['fee_verified'],flush=True)
            print('Rule kind:',market.get('rule_kind'),'Description:',str(raw.get('description',''))[:2500],flush=True)
            for side,token in market['tokens'].items():
                def book(token=token):
                    raw_book=get_json(CLOB+'/book?token_id='+str(token))
                    normalized=normalize_book(raw_book,token,time.time())
                    return {'asks':len(normalized['asks']),'bids':len(normalized['bids'])}
                check('Book '+side,book)
    asyncio.run(reference_probe())
    check('Runtime state AFTER probes',database)
    check('Local health AFTER probes',health)
    print('END BTC LAB DIAGNOSIS',flush=True)

if __name__=='__main__':main()
