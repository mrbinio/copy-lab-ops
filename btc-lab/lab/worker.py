"""Read-only public collectors and paper execution. Contains no signed API calls."""
import asyncio
import hashlib
import json
import logging
import os
import re
import time
import urllib.parse
import urllib.request
from collections import deque
from datetime import datetime
from pathlib import Path
from .core import Store, STRATEGIES, simulate_fill, LedgerError
from .strategy import choose, features
from .research import train, report
from .reference import classify_rule, observation, SPOT, TWAP60, TWAP30

LOG=logging.getLogger('btc-lab')
GAMMA='https://gamma-api.polymarket.com'
CLOB='https://clob.polymarket.com'
RTDS='wss://ws-live-data.polymarket.com'

def reference_subscription():
    filters=json.dumps({'symbol':'btc/usd'},separators=(',',':'))
    return {'action':'subscribe','subscriptions':[
        {'topic':topic,'type':'*' if topic=='crypto_prices_chainlink' else 'update','filters':filters}
        for topic in ('crypto_prices_chainlink','crypto_prices_twap_thirty','crypto_prices_twap_sixty')]}

def error_detail(error):
    detail=str(getattr(error,'reason',error))
    detail=re.sub(r'(://)[^/\s@]+@',r'\1[redacted]@',detail)
    return f'{type(error).__name__}: {detail}'[:400].replace('\n',' ')

def get_json(url):
    request=urllib.request.Request(url,headers={'User-Agent':'BTC-Lab-Paper/0.1','Accept':'application/json'})
    try:
        with urllib.request.urlopen(request,timeout=8) as response:
            raw=response.read(2_000_001)
            if len(raw)>2_000_000: raise ValueError('oversized public response')
            return json.loads(raw)
    except Exception as error:
        endpoint=urllib.parse.urlsplit(url)
        raise RuntimeError(f'{endpoint.hostname}{endpoint.path}: {error_detail(error)}') from error

def array(value):
    return json.loads(value) if isinstance(value,str) else value

def normalize_market(raw, start):
    names,tokens=array(raw['outcomes']),array(raw['clobTokenIds'])
    if len(names)!=2 or len(tokens)!=2 or set(names)!={'Up','Down'} or len(set(tokens))!=2:
        raise ValueError('unsupported outcome mapping')
    description=raw.get('description','')
    kind,topic,schema=classify_rule(description)
    supported=topic is not None
    if kind=='TWAP60':
        try:
            event_start=datetime.fromisoformat(raw['eventStartTime'].replace('Z','+00:00'))
            event_end=datetime.fromisoformat(raw['endDate'].replace('Z','+00:00'))
            supported=(raw['slug']==f'btc-updown-15m-{start}' and
                       event_start.tzinfo is not None and event_end.tzinfo is not None and
                       event_start.timestamp()==start and event_end.timestamp()==start+900)
        except (KeyError,ValueError,TypeError):supported=False
    fees=raw.get('feeSchedule') or {}
    verified=raw.get('feesEnabled') is False or (raw.get('feesEnabled') is True and fees.get('exponent')==1 and 'rate' in fees)
    rate=0 if raw.get('feesEnabled') is False else float(fees.get('rate',0))
    if not 0<=rate<=1: raise ValueError('invalid fee schedule')
    return {'slug':raw['slug'],'condition':raw['conditionId'],'start':start,'end':start+900,
            'rule_kind':kind,'reference_topic':topic,'feature_schema':schema,
            'tokens':dict(zip(names,tokens)),'rule_supported':supported,'rule_hash':hashlib.sha256(description.encode()).hexdigest(),
            'fee_rate':rate,'fee_verified':verified,'opening':None,'books':{},'title':raw.get('question',raw['slug']),
            'accepting':raw.get('active') is True and raw.get('closed') is False and raw.get('acceptingOrders') is True}

def normalize_book(raw, token, now):
    if str(raw.get('asset_id'))!=str(token): raise ValueError('book token mismatch')
    source=float(raw['timestamp'])/1000
    if not -.25 <= now-source <= 3: raise ValueError('stale/future book')
    return {'asks':[[x['price'],x['size']] for x in raw['asks']],
            'bids':[[x['price'],x['size']] for x in raw['bids']],
            'source_ts':source,'received_at':now,'min_shares':raw['min_order_size'],'tick':raw['tick_size']}

class Worker:
    def __init__(self, store, data):
        self.store,self.data=store,Path(data)
        self.reference=None
        self.history=deque(maxlen=3600)
        self.market=None
        self.last_research=0
        self.last_registry=0
        self.feed_error=None
        self.last_decisions={}
        self.last_reconcile=0
        self.reconciliation_ok=False
        self.reference_topics={}
        self.references={}
        self.twap_history=deque(maxlen=3600)

    def selected_reference(self,market):
        return self.references.get(TWAP60) if market.get('reference_topic')==TWAP60 else self.reference if market.get('reference_topic') in (None,SPOT) else None

    def selected_history(self,market):
        return [(r['source_ts'],r['price']) for r in self.twap_history] if market.get('reference_topic')==TWAP60 else list(self.history)

    def capture_opening(self,market):
        if market.get('opening') is not None:return
        if market.get('reference_topic')==TWAP60:
            sample=next((r for r in self.twap_history if r['source_ms']==market['start']*1000),None)
            if sample:
                market.update(opening=sample['price'],opening_decimal=sample['price_decimal'],opening_evidence=dict(sample))
        else:
            market['opening']=next((v for t,v in self.history if abs(t-market['start'])<.001),None)

    def accept_reference(self,event,now):
        value=observation(event,now)
        if value is None:return
        topic=value['topic']
        previous=self.references.get(topic)
        if previous and value['source_ts']<=previous['source_ts']:return
        if previous and value['source_ts']-previous['source_ts']>10:
            self.store.record('reference_gap',{'topic':topic,'from':previous['source_ts'],'to':value['source_ts']},now)
            if topic==SPOT:self.history.clear()
            if topic==TWAP60:self.twap_history.clear()
        self.store.record('rtds',event,now)
        self.references[topic]=value
        self.reference_topics[topic]=value['source_ts']
        self.store.set('reference_topics',self.reference_topics)
        if topic==TWAP60:self.twap_history.append(value)
        if topic==SPOT:
            self.reference=value
            self.history.append((value['source_ts'],value['price']))
        self.feed_error=None

    def decision(self,strategy,market,reason,body,now):
        # Persist changes immediately, repeated skip reasons at most once per minute.
        old=self.last_decisions.get(strategy)
        if old and old[:2]==(market,reason) and now-old[2]<60:
            return
        self.store.decide(strategy,market,reason,body,now)
        self.last_decisions[strategy]=(market,reason,now)

    async def reference_stream(self):
        import websockets
        while True:
            try:
                async with websockets.connect(RTDS,open_timeout=10,max_size=1_000_000) as ws:
                    await ws.send(json.dumps(reference_subscription()))
                    async def ping():
                        while True:
                            await ws.send('PING')
                            await asyncio.sleep(5)
                    task=asyncio.create_task(ping())
                    try:
                        async for message in ws:
                            if message in ('PONG','PING',''): continue
                            e=json.loads(message)
                            try:self.accept_reference(e,time.time())
                            except (ValueError,KeyError,TypeError) as error:
                                self.feed_error=error_detail(error)
                                self.store.record('reference_rejected',{'error':self.feed_error,'topic':e.get('topic')})
                    finally:
                        task.cancel()
                        await asyncio.gather(task,return_exceptions=True)
            except Exception as e:
                self.feed_error=error_detail(e)
                LOG.warning('reference halted: %s',self.feed_error)
                self.store.record('reference_disconnect',{'error':self.feed_error})
                self.reference=None
                self.history.clear()
                self.references.clear()
                self.twap_history.clear()
                self.reference_topics.clear()
                await asyncio.sleep(5)

    async def discover(self, start):
        slug=f'btc-updown-15m-{start}'
        raw=await asyncio.to_thread(get_json,f'{GAMMA}/markets/slug/{slug}')
        if raw.get('slug')!=slug: raise ValueError('market slug mismatch')
        m=normalize_market(raw,start)
        # Require an observed source tick exactly at the boundary; no Binance fallback,
        # no nearest-tick substitution. Missing history means this window is skipped.
        self.capture_opening(m)
        if self.market and self.market['slug']==slug and self.market['rule_hash']==m['rule_hash']:
            for key in ('opening','opening_decimal','opening_evidence'):
                if self.market.get(key) is not None:m[key]=self.market[key]
        self.store.record('market_metadata',raw)
        return m

    async def books(self, m):
        async def one(side,token):
            raw=await asyncio.to_thread(get_json,f'{CLOB}/book?token_id={urllib.parse.quote(str(token),safe="")}')
            now=time.time()
            self.store.record('book',{'market':m['slug'],'side':side,'raw':raw},now)
            return side,normalize_book(raw,token,now)
        results=await asyncio.gather(*(one(s,t) for s,t in m['tokens'].items()))
        return dict(results)

    async def reconcile(self):
        with self.store.connect() as db:
            rows=db.execute("SELECT DISTINCT market FROM positions WHERE status='OPEN' UNION SELECT market FROM examples WHERE market NOT IN (SELECT market FROM labels)").fetchall()
        for row in rows[:100]:
            slug=row[0]
            if int(slug.rsplit('-',1)[1])+900>time.time(): continue
            raw=await asyncio.to_thread(get_json,f'{GAMMA}/markets/slug/{slug}')
            condition=raw['conditionId']
            official=await asyncio.to_thread(get_json,f'{CLOB}/markets/{condition}')
            if str(official.get('condition_id'))!=str(condition): raise ValueError('resolution condition mismatch')
            winners=[t for t in official.get('tokens',[]) if t.get('winner') is True]
            if official.get('closed') is True and len(winners)==1 and winners[0].get('outcome') in ('Up','Down'):
                self.store.resolve(slug,winners[0]['outcome'],{'source':'clob_official_winner','closed':True,
                    'condition':condition,'token':winners[0]['token_id']},time.time())
        self.store.redeem(time.time())
        self.store.audit()

    async def cycle(self, entries_allowed=True):
        self.store.audit()
        now=time.time()
        start=int(now)//900*900
        if not self.market or self.market['start']!=start or now-self.last_registry>=30:
            self.market=await self.discover(start)
            self.last_registry=now
        m=self.market
        self.capture_opening(m)
        reference=self.selected_reference(m)
        history=self.selected_history(m)
        self.store.set('reference',reference or {})
        self.store.set('market',m)
        m['books']=await self.books(m)
        now=time.time()
        up=m['books']['Up']; down=m['books']['Down']
        def mid(b):
            if not b['asks'] or not b['bids']: return None
            return (min(float(x[0]) for x in b['asks'])+max(float(x[0]) for x in b['bids']))/2
        um,dm=mid(up),mid(down)
        probability=um/(um+dm) if um is not None and dm is not None and um+dm>0 else None
        m['features']=None
        if reference and m['opening'] and probability and -.25<=now-reference['source_ts']<=5:
            past=[x for x in history if now-600<=x[0]<=now]
            m['features']=features(reference['price'],m['opening'],past,probability,m['end']-now)
        if m['features'] and m['rule_supported'] and 119 <= m['end']-now <=121:
            with self.store.connect() as db:
                db.execute('INSERT OR IGNORE INTO examples VALUES (?,?,?)',(m['slug'],now,json.dumps({'features':m['features'],'book_probability':probability,'rule_hash':m['rule_hash'],'feature_schema':m['feature_schema']})))
        self.store.set('market',m)
        self.store.set('price_history',history[-900:])
        model=self.store.get('model',{})
        signals=[]
        paused=(self.data/'PAUSE').exists() or not entries_allowed
        for strategy in STRATEGIES:
            intent,reason=choose(strategy,m,reference,model,now) if not paused else (None,'MANUAL_PAUSE')
            if intent: signals.append(intent)
            else: self.decision(strategy,m['slug'],reason,{},now)
        if signals:
            # New arrival books after explicit latency: never fill on the decision snapshot.
            await asyncio.sleep(.25)
            arrival=await self.books(m)
            for intent in signals:
                at=time.time()
                book=arrival[intent['side']]
                reason='ARRIVAL_INVALID'
                reference=self.selected_reference(m)
                if not (self.data/'PAUSE').exists() and at < m['end']-30 and reference and -.25 <= at-reference['source_ts']<=5:
                    fill=simulate_fill(book['asks'],'5',str(intent['limit']),str(m['fee_rate']),book['min_shares'],book['tick'])
                    reason='NO_FULL_FILL'
                    if fill:
                        if intent['probability'] is not None and intent['probability']-fill['vwap']-fill['fee']/fill['shares']-.03<.02:
                            reason='EDGE_LOST'
                        else:
                            reason=self.store.open(intent['strategy'],m['slug'],intent['side'],fill,
                                {**intent,'arrival_at':at,'rule_hash':m['rule_hash'],'reference':reference,
                                 'feature_schema':m['feature_schema'],'opening_evidence':m.get('opening_evidence'),
                                 'opening':m['opening'],'model_id':model.get('model_id'),'depth_fraction':.5},at)
                self.decision(intent['strategy'],m['slug'],reason,intent,at)
        reference=self.selected_reference(m)
        self.store.set('reference',reference or {})
        reference_fresh=reference and -.25<=time.time()-reference['source_ts']<=5
        self.store.set('worker',{'status':('PAUSED' if paused else 'RECORDING') if reference_fresh else 'DEGRADED','heartbeat':time.time(),
            'reference_status':'FRESH' if reference_fresh else 'MISSING_OR_STALE',
            'reference_error':self.feed_error,'version':'0.2.0','execution':'PAPER ONLY'})

    async def iteration(self):
        errors=[]
        def failure(stage,error):
            errors.append({'stage':stage,'error':type(error).__name__,'detail':error_detail(error)})
            LOG.warning('%s halted: %s',stage,error_detail(error))
            if isinstance(error,LedgerError):
                (self.data/'PAUSE').touch()
        # Settlement must keep running when current-market discovery/books fail.
        # A failed reconciliation blocks fresh entries until a successful retry.
        if time.time()-self.last_reconcile>60:
            self.last_reconcile=time.time()
            try:
                await self.reconcile()
                self.reconciliation_ok=True
            except Exception as e:
                self.reconciliation_ok=False
                failure('reconciliation',e)
        try:
            await self.cycle(entries_allowed=self.reconciliation_ok)
        except Exception as e:
            failure('collection',e)
        if time.time()-self.last_research>3600 or self.store.get('model',{}).get('feature_schema')!=(self.store.get('market',{}).get('feature_schema') or 'spot-v1'):
            try:
                train(self.store)
                self.store.set('report',report(self.store))
                self.last_research=time.time()
            except Exception as e:
                failure('research',e)
        if errors:
            self.store.set('worker',{'status':'DEGRADED','heartbeat':time.time(),
                'errors':errors,'version':'0.2.0'})

    async def run(self):
        self.store.audit()
        reference=asyncio.create_task(self.reference_stream())
        try:
            while True:
                await self.iteration()
                await asyncio.sleep(2)
        finally:
            reference.cancel()
            await asyncio.gather(reference,return_exceptions=True)

def main():
    import fcntl
    logging.basicConfig(level=logging.INFO)
    data=Path(os.environ.get('LAB_DATA','./runtime'))
    data.mkdir(parents=True,exist_ok=True)
    with (data/'worker.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        asyncio.run(Worker(Store(data/'lab.sqlite'),data).run())

if __name__=='__main__': main()
