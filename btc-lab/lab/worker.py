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
from .core import Store, STRATEGIES, VenueClock, simulate_fill, LedgerError
from .strategy import choose, features, MODEL_HORIZON
from .research import train, report
from .mid_window import exit_intent, simulate_sale
from .mid_window_v2 import exit_intent_v2
from .exit_comparison import ExitComparison
from .complete_set import CompleteSetObserver
from .feed_watchdog import fresh_messages, next_backoff
from .wallet_observer import WalletObserver, get_active_wallets
from .wallet_discovery import WalletDiscovery
from .wallet_copy import WalletCopy
from .opportunity_research import OpportunityResearch
from .value_execution import ValueExecution
from .strategy_control import is_paused as strategy_paused
from .reference import classify_rule, observation, SPOT, TWAP60, TWAP30

LOG=logging.getLogger('btc-lab')
GAMMA='https://gamma-api.polymarket.com'
CLOB='https://clob.polymarket.com'
RTDS='wss://ws-live-data.polymarket.com'
# Free public Polygon log stream. Replaces paid Alchemy when no URL is set.
# blockmachine held 90s with live TransferSingle logs; drpc drops ~30s; llamarpc fails DNS here.
DEFAULT_CHAIN_WSS=('wss://rpc-polygon.blockmachine.io','wss://polygon.drpc.org')

def reference_subscription(asset="BTC"):
    if asset not in ("BTC", "ETH"): raise ValueError("unsupported asset")
    filters=json.dumps({'symbol':asset.lower()+'/usd'},separators=(',',':'))
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

def normalize_market(raw, start, asset="BTC"):
    if asset not in ("BTC", "ETH"): raise ValueError("unsupported asset")
    names,tokens=array(raw['outcomes']),array(raw['clobTokenIds'])
    if len(names)!=2 or len(tokens)!=2 or set(names)!={'Up','Down'} or len(set(tokens))!=2:
        raise ValueError('unsupported outcome mapping')
    description=raw.get('description','')
    kind,topic,schema=classify_rule(description,asset)
    supported=topic is not None
    if kind=='TWAP60':
        try:
            event_start=datetime.fromisoformat(raw['eventStartTime'].replace('Z','+00:00'))
            event_end=datetime.fromisoformat(raw['endDate'].replace('Z','+00:00'))
            supported=(raw['slug']==f'{asset.lower()}-updown-15m-{start}' and
                       event_start.tzinfo is not None and event_end.tzinfo is not None and
                       event_start.timestamp()==start and event_end.timestamp()==start+900)
        except (KeyError,ValueError,TypeError):supported=False
    fees=raw.get('feeSchedule') or {}
    verified=raw.get('feesEnabled') is False or (raw.get('feesEnabled') is True and fees.get('exponent')==1 and 'rate' in fees)
    rate=0 if raw.get('feesEnabled') is False else float(fees.get('rate',0))
    if not 0<=rate<=1: raise ValueError('invalid fee schedule')
    return {'asset':asset,'slug':raw['slug'],'condition':raw['conditionId'],'start':start,'end':start+900,
            'rule_kind':kind,'reference_topic':topic,'feature_schema':schema,
            'tokens':dict(zip(names,tokens)),'rule_supported':supported,'rule_hash':hashlib.sha256(description.encode()).hexdigest(),
            'fee_rate':rate,'fee_verified':verified,'opening':None,'books':{},'title':raw.get('question',raw['slug']),
            'accepting':raw.get('active') is True and raw.get('closed') is False and raw.get('acceptingOrders') is True}

def normalize_book(raw, token, now, max_age=8, venue_clock=None):
    if str(raw.get('asset_id'))!=str(token): raise ValueError('book token mismatch')
    source=float(raw['timestamp'])/1000
    age=now-source
    if venue_clock is not None:
        venue_clock.observe(source,now)
        age=venue_clock.age(source,now)
    if not -.25 <= age <= max_age: raise ValueError('stale/future book')
    return {'asks':[[x['price'],x['size']] for x in raw['asks']],
            'bids':[[x['price'],x['size']] for x in raw['bids']],
            'source_ts':source,'received_at':now,'min_shares':raw['min_order_size'],'tick':raw['tick_size']}

class Worker:
    def __init__(self, store, data):
        self.store,self.data=store,Path(data)
        self.asset=store.asset
        self.entry_strategy="mid-window-v1" if self.asset=="BTC" else "eth-mid-window-v1"
        self.reference=None
        self.history=deque(maxlen=3600)
        self.market=None
        self.last_research=0
        self.last_prune=0
        self.last_registry=0
        self.feed_error=None
        self.last_decisions={}
        self.last_reconcile=0
        self.reconciliation_ok=False
        self.ledger_ok=True  # False only on LedgerError; blocks ALL operations including exits
        self._feed_backoff=2
        self.reference_topics={}
        self.references={}
        # The order books and the price feed are separate venues with separate
        # clocks; one shared offset would hide a drift in either of them.
        self.book_clock=VenueClock()
        self.reference_clock=VenueClock()
        self.twap_history=deque(maxlen=3600)
        self.exit_comparison=ExitComparison(store)
        self.complete_set=CompleteSetObserver(store)
        self.opportunity_research=OpportunityResearch(store)
        self.value_execution=ValueExecution(store)

    def choose_entry(self, strategy, market, reference, model, now, paused=False):
        # Pause late entries only. BTC 3–7 is active. Existing exits and settlement
        # run independently and historical positions are never rewritten.
        if self.asset == "BTC" and strategy == "late-v1":
            return None, "STRATEGY_RETIRED"
        if strategy_paused(self.store, strategy):
            return None, "STRATEGY_PAUSED"
        if paused:
            return None, "MANUAL_PAUSE"
        return choose("mid-window-v1" if self.asset == "ETH" else strategy,
                      market, reference, model, now)

    def is_paused(self):
        return (self.data/"PAUSE").exists() or (self.asset=="ETH" and (self.data.parent/"PAUSE").exists())

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
        value=observation(event,now,self.asset)
        if value is None:return
        topic=value['topic']
        self.reference_clock.observe(value['source_ts'],now)
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
                async with websockets.connect(RTDS,open_timeout=10,max_size=1_000_000,
                                               ping_interval=20,ping_timeout=10) as ws:
                    self._feed_backoff=2
                    drop=self.data/'DROP_REFERENCE'
                    if drop.exists():
                        drop.unlink()
                        raise TimeoutError('controlled reference drop')
                    await ws.send(json.dumps(reference_subscription(self.asset)))
                    async def ping():
                        while True:
                            await ws.send('PING')
                            await asyncio.sleep(5)
                    task=asyncio.create_task(ping())
                    try:
                        async for message in fresh_messages(ws, lambda: self.references.get(TWAP60,{}).get('source_ts')):
                            drop=self.data/'DROP_REFERENCE'
                            if drop.exists():
                                drop.unlink()
                                raise TimeoutError('controlled reference drop')
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
                await asyncio.sleep(self._feed_backoff)
                self._feed_backoff=next_backoff(self._feed_backoff)

    async def discover(self, start):
        asset=self.asset
        slug=f'{asset.lower()}-updown-15m-{start}'
        raw=await asyncio.to_thread(get_json,f'{GAMMA}/markets/slug/{slug}')
        if raw.get('slug')!=slug: raise ValueError('market slug mismatch')
        m=normalize_market(raw,start,self.asset)
        # Require an observed source tick exactly at the boundary; no Binance fallback,
        # no nearest-tick substitution. Missing history means this window is skipped.
        self.capture_opening(m)
        if self.market and self.market['slug']==slug and self.market['rule_hash']==m['rule_hash']:
            for key in ('opening','opening_decimal','opening_evidence'):
                if self.market.get(key) is not None:m[key]=self.market[key]
        self.store.record('market_metadata',raw)
        return m

    def clock_skew(self):
        """Published so a drifting local clock is visible before it costs a trade."""
        return {'book':round(self.book_clock.skew(),3),'reference':round(self.reference_clock.skew(),3),
                'samples':{'book':len(self.book_clock.offsets),'reference':len(self.reference_clock.offsets)}}

    async def books(self, m):
        async def one(side,token):
            raw=await asyncio.to_thread(get_json,f'{CLOB}/book?token_id={urllib.parse.quote(str(token),safe="")}')
            now=time.time()
            self.store.record('book',{'market':m['slug'],'side':side,'raw':raw},now)
            return side,normalize_book(raw,token,now,venue_clock=self.book_clock)
        results=await asyncio.gather(*(one(s,t) for s,t in m['tokens'].items()))
        return dict(results)

    async def reconcile(self):
        with self.store.connect() as db:
            rows=db.execute("SELECT DISTINCT market FROM positions WHERE status='OPEN' UNION SELECT market FROM examples WHERE market NOT IN (SELECT market FROM labels)").fetchall()
            shadow_markets={json.loads(r[0])['market'] for r in db.execute('SELECT body FROM exit_comparison')
                            if json.loads(r[0])['status']=='OPEN'}
            shadow_markets.update(r[0] for r in db.execute("SELECT DISTINCT market FROM opportunity_samples WHERE market NOT IN (SELECT market FROM labels)"))
            known={r[0] for r in rows}
            rows=list(rows)+[(slug,) for slug in sorted(shadow_markets-known)]
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

    async def paper_exits(self, market, reconciliation_ok):
        # P0-1 FIX: Stop-loss exits run independently of network reconciliation failures.
        # However, a LedgerError (integrity violation) MUST block everything.
        if not self.ledger_ok:return
        if not market.get('accepting') or not market.get('fee_verified') or not market.get('rule_supported'):return
        with self.store.connect() as db:
            rows=[dict(r) for r in db.execute("SELECT * FROM positions WHERE status='OPEN' AND market=?",(market['slug'],))]
        rows=[p for p in rows if p['strategy'] in (self.entry_strategy,'mid-window-v2') or json.loads(p['evidence']).get('risk_policy') in ('btc-stop10-v1','eth-stop10-v1','btc-mid-v2-stop10','eth-mid-v2-stop10')]
        for p in rows:
            # Route to the correct exit_intent based on strategy version.
            if p['strategy'] == 'mid-window-v2':
                intent,reason=exit_intent_v2(p,market,time.time())
            else:
                intent,reason=exit_intent(p,market,time.time())
            if intent:
                decision_book_ts=market['books'][p['side']]['source_ts']
                await asyncio.sleep(.25)
                arrival=await self.books(market)
                at=time.time();book=arrival[p['side']]
                reason='EXIT_CUTOFF'
                protected=json.loads(p['evidence']).get('risk_policy') in ('btc-stop10-v1','eth-stop10-v1','btc-mid-v2-stop10','eth-mid-v2-stop10')
                if at<market['start']+900 and (protected or at<market['start']+600):
                    # P0-2 FIX: Require arrival book strictly newer than decision snapshot.
                    # Filling on the same book violates independent-arrival principle.
                    reason='EXIT_ARRIVAL_NOT_NEWER'
                    if book['source_ts']>decision_book_ts and -.25<=self.book_clock.age(book['source_ts'],at)<=3:
                        fill=simulate_sale(book,p['shares'],market['fee_rate'],intent['floor'])
                        reason='EXIT_NO_FULL_FILL'
                        if fill:
                            reason=self.store.close_paper(p['id'],fill,{**intent,'arrival_at':at,'book_source_ts':book['source_ts'],'decision_book_ts':decision_book_ts},at)
            self.decision(p['strategy'],market['slug'],reason, intent or {},time.time())

    async def cycle(self, entries_allowed=True):
        self.store.audit()
        now=time.time()
        start=int(now)//900*900
        if not self.market or self.market['start']!=start or now-self.last_registry>=30:
            self.market=await self.discover(start)
            self.last_registry=now
        m=self.market
        self.capture_opening(m)
        self.store.set('market',m)
        try:
            m['books']=await self.books(m)
        except ValueError as error:
            if 'stale/future book' not in str(error):
                raise
            now=time.time()
            self.store.set('worker',{'status':'DEGRADED','heartbeat':now,
                'reference_status':'FRESH' if self.selected_reference(m) else 'MISSING_OR_STALE',
                'book_status':'STALE','reference_error':self.feed_error,'version':'0.6.7','asset':self.asset,
                'execution':'PAPER ONLY','clock_skew':self.clock_skew()})
            return
        now=time.time()
        try:
            self.complete_set.step(m,now)
            self.store.set('complete_set_error',{})
        except Exception as error:
            self.store.set('complete_set_error',{'at':now,'error':error_detail(error)})
        # RTDS continues while REST requests are in flight. Use the latest
        # reference/history available at the actual decision time.
        self.capture_opening(m)
        reference=self.selected_reference(m)
        history=self.selected_history(m)
        self.store.set('reference',reference or {})
        up=m['books']['Up']; down=m['books']['Down']
        def mid(b):
            if not b['asks'] or not b['bids']: return None
            return (min(float(x[0]) for x in b['asks'])+max(float(x[0]) for x in b['bids']))/2
        um,dm=mid(up),mid(down)
        probability=um/(um+dm) if um is not None and dm is not None and um+dm>0 else None
        m['causal_history']=[x for x in history if now-35<=x[0]<=now]
        m['features']=None
        if reference and m['opening'] and probability and -.25<=self.reference_clock.age(reference['source_ts'],now)<=5:
            past=[x for x in history if now-600<=x[0]<=now]
            m['features']=features(reference['price'],m['opening'],past,probability,m['end']-now)
        try:
            self.opportunity_research.step(m,reference,now)
            self.store.set('opportunity_research_error',{})
        except Exception as error:
            self.store.set('opportunity_research_error',{'at':now,'error':error_detail(error)})
        try:
            self.value_execution.step(m,reference,time.time(),entries_allowed and not self.is_paused() and not strategy_paused(self.store,'value-surface-paper-v1'))
            self.store.set('value_surface_execution_error',{})
        except Exception as error:
            self.store.set('value_surface_execution_error',{'at':time.time(),'error':error_detail(error)})
        # Match the model's existing decision horizon. One causal sample per
        # market; never backdate or fill a missed window with later data.
        books_fresh=all(-.25 <= self.book_clock.age(b['source_ts'],now) <= 3 for b in (up,down))
        if (self.asset=='BTC' and m['features'] and m['rule_supported'] and books_fresh
                and MODEL_HORIZON[0] <= m['end']-now <= MODEL_HORIZON[1]):
            with self.store.connect() as db:
                db.execute('INSERT OR IGNORE INTO examples VALUES (?,?,?)',(m['slug'],now,json.dumps({'features':m['features'],'book_probability':probability,'rule_hash':m['rule_hash'],'feature_schema':m['feature_schema'],
                    'sampling_policy':'first-valid-model-horizon-v2','remaining_seconds':m['end']-now,
                    'reference_source_ts':reference['source_ts'],
                    'book_source_ts':{side:b['source_ts'] for side,b in m['books'].items()}})))
        self.store.set('market',m)
        self.store.set('price_history',history[-900:])
        # Isolated paired research uses the already collected snapshot: no extra
        # HTTP calls or sleeps, no mutation of trading accounts or risk limits.
        try:
            if self.asset=='BTC':self.exit_comparison.step(m,time.time(),entries_allowed)
            self.store.set('exit_comparison_error',{})
        except Exception as error:
            self.store.set('exit_comparison_error',{'at':time.time(),'error':error_detail(error)})
            LOG.warning('exit comparison halted: %s',error_detail(error))
        await self.paper_exits(m, entries_allowed)
        model=self.store.get('model',{})
        signals=[]
        paused=self.is_paused() or not entries_allowed
        for strategy in self.store.strategies:
            intent,reason=self.choose_entry(strategy,m,reference,model,now,paused)
            if intent:
                if self.asset=="ETH":
                    intent.update(strategy=strategy,config_version="eth-mid-window-v1",asset="ETH",hypothesis={**intent["hypothesis"],"id":"eth-mid-window-v1","asset":"ETH"})
                if (self.asset=='BTC' and strategy in ('mid-window-v1','early-v1','mid-window-v2')) or (self.asset=='ETH' and strategy=='eth-mid-window-v1'):
                    risk_policy=self.asset.lower()+('-mid-v2-stop10' if strategy=='mid-window-v2' else '-stop10-v1')
                    intent.update(risk_policy=risk_policy,config_version=strategy+'-stop10-v1',
                                  stop_loss_net_fraction=.10,entry_all_in_cap_usd=5)
                    if 'hypothesis' in intent:
                        intent['hypothesis']={**intent['hypothesis'],'id':intent['config_version'],
                            'stop_loss_net_fraction':.10,'protective_sale_until_elapsed_exclusive':900,
                            'entry_all_in_cap_usd':5}
                signals.append(intent)
            else: self.decision(strategy,m['slug'],reason,{},now)
        if signals:
            # New arrival books after explicit latency: never fill on the decision snapshot.
            # P0-2 FIX: Record decision book timestamps to enforce strictly newer arrival.
            decision_book_ts={side:b['source_ts'] for side,b in m['books'].items()}
            await asyncio.sleep(.25)
            arrival=await self.books(m)
            for intent in signals:
                at=time.time()
                book=arrival[intent['side']]
                reason='ARRIVAL_INVALID'
                reference=self.selected_reference(m)
                # Enforce each strategy's entry window at arrival time, not just decision time.
                elapsed_at_arrival=at-m['start']
                if intent['strategy']==self.entry_strategy:
                    time_valid=180<=elapsed_at_arrival<=420
                elif intent['strategy']=='mid-window-v2':
                    time_valid=180<=elapsed_at_arrival<=420
                else:
                    time_valid=True  # other strategies have their own window checks in choose()
                # P0-2 FIX: Arrival book must have a strictly newer source_ts than decision.
                book_valid=all(-.25<=self.book_clock.age(b['source_ts'],at)<=3 and b['source_ts']>decision_book_ts.get(side,0) for side,b in arrival.items())
                if time_valid and book_valid and not self.is_paused() and at < m['end']-30 and reference and -.25 <= self.reference_clock.age(reference['source_ts'],at)<=5 and m.get('fee_verified'):
                    capacity=self.store.entry_capacity(intent['strategy'],at)
                    intent.update(sizing_policy='remaining-risk-v1',entry_capacity_micro=capacity)
                    if capacity<=0:
                        self.decision(intent['strategy'],m['slug'],'RISK_CAPACITY_EXHAUSTED',intent,at);continue
                    budget=str(max(0,capacity-100)/1e6/(1+float(m['fee_rate'])))
                    fill=simulate_fill(book['asks'],budget,str(intent['limit']),str(m['fee_rate']),book['min_shares'],book['tick'])
                    if fill and fill['cost']+fill['fee']>capacity:fill=None
                    reason='CAPACITY_BELOW_MARKET_MINIMUM' if float(budget)<float(book['min_shares'])*float(intent['limit']) else 'NO_FULL_FILL'
                    if fill and intent['strategy']==self.entry_strategy and any(not .50<=float(f['price'])<=.60 for f in fill['fills']):
                        fill=None;reason='ARRIVAL_PRICE_OUTSIDE_RANGE'
                    if fill and intent['strategy']=='mid-window-v2' and any(not .55<=float(f['price'])<=.80 for f in fill['fills']):
                        fill=None;reason='ARRIVAL_PRICE_OUTSIDE_RANGE'
                    if fill:
                        if intent['probability'] is not None and intent['probability']-fill['vwap']-fill['fee']/fill['shares']-.03<.02:
                            reason='EDGE_LOST'
                        else:
                            reason=self.store.open(intent['strategy'],m['slug'],intent['side'],fill,
                                {**intent,'arrival_at':at,'rule_hash':m['rule_hash'],'reference':reference,
                                 'feature_schema':m['feature_schema'],'opening_evidence':m.get('opening_evidence'),
                                 'opening':m['opening'],'model_id':model.get('model_id'),'depth_fraction':.5},at)
                            if self.asset=='BTC' and reason=='FILLED' and intent['strategy']==self.entry_strategy:
                                self.exit_comparison.capture(m,at)
                self.decision(intent['strategy'],m['slug'],reason,intent,at)
        reference=self.selected_reference(m)
        self.store.set('reference',reference or {})
        now=time.time()
        reference_fresh=reference and -.25<=self.reference_clock.age(reference['source_ts'],now)<=5
        self.store.set('worker',{'status':('PAUSED' if paused else 'RECORDING') if reference_fresh else 'DEGRADED','heartbeat':now,
            'reference_status':'FRESH' if reference_fresh else 'MISSING_OR_STALE',
            'book_status':'FRESH' if books_fresh else 'STALE',
            'reference_error':self.feed_error,'version':'0.6.7','asset':self.asset,'execution':'PAPER ONLY',
            'clock_skew':self.clock_skew()})

    async def iteration(self):
        errors=[]
        def failure(stage,error):
            errors.append({'stage':stage,'error':type(error).__name__,'detail':error_detail(error)})
            LOG.warning('%s halted: %s',stage,error_detail(error))
            if isinstance(error,LedgerError):
                self.ledger_ok=False
                (self.data/'PAUSE').touch()
        # Settlement must keep running when current-market discovery/books fail.
        # A failed reconciliation blocks fresh entries until a successful retry.
        if time.time()-self.last_reconcile>60:
            self.last_reconcile=time.time()
            try:
                await self.reconcile()
                self.reconciliation_ok=True
            except LedgerError as e:
                self.reconciliation_ok=False
                failure('reconciliation',e)
            except Exception as e:
                self.reconciliation_ok=False
                failure('reconciliation',e)
        try:
            self.value_execution.settle(time.time())
        except Exception as e:
            failure('value_settlement',e)
        try:
            await self.cycle(entries_allowed=self.reconciliation_ok)
        except Exception as e:
            failure('collection',e)
        if self.asset=='BTC' and (time.time()-self.last_research>3600 or self.store.get('model',{}).get('feature_schema')!=(self.store.get('market',{}).get('feature_schema') or 'spot-v1')):
            try:
                train(self.store)
                self.store.set('report',report(self.store))
                self.last_research=time.time()
            except Exception as e:
                failure('research',e)
        if time.time()-self.last_prune>=600:
            try:
                dropped=await asyncio.to_thread(self.store.prune_ephemeral)
                self.last_prune=time.time()
                if dropped:
                    LOG.info('pruned %d old book/price notes',dropped)
            except Exception as e:
                failure('prune',e)
        if errors:
            self.store.set('worker',{'status':'DEGRADED','heartbeat':time.time(),
                'errors':errors,'version':'0.6.7','asset':self.asset,'clock_skew':self.clock_skew()})

    async def run(self):
        self.store.audit()
        reference=asyncio.create_task(self.reference_stream())
        observer=WalletObserver(self.store,get_json) if self.asset=="BTC" else None
        wallets=asyncio.create_task(observer.run()) if observer else None
        # Hourly shortlist only. Candidates are never auto-copied.
        discovery=asyncio.create_task(WalletDiscovery(self.store,get_json).run()) if self.asset=='BTC' else None
        # --- CLOB live order support (optional, off by default) ---
        clob_client = None
        if self.asset == "BTC":
            config_path = self.data / 'config.json'
            if not config_path.exists():
                config_path = self.data.parent / 'config.json'
            if config_path.exists():
                try:
                    config = json.loads(config_path.read_text())
                    clob_key = config.get('clob_private_key', '')
                    clob_live = config.get('clob_live', False)
                    if clob_key and clob_live is True:
                        from .clob_order import CLOBClient as _CLOBClient
                        clob_client = _CLOBClient(
                            private_key=clob_key,
                            max_order_usd=5.0,
                        )
                        LOG.info('CLOB live orders ENABLED (max $5/order, $10 exposure)')
                    else:
                        LOG.info('CLOB live orders disabled (clob_live=%s, key=%s)',
                                 clob_live, 'present' if clob_key else 'missing')
                except Exception as e:
                    LOG.warning('Failed to initialize CLOB client: %s', e)
                    clob_client = None
        copier=asyncio.create_task(WalletCopy(self.store,get_json,self.is_paused,clob_client=clob_client).run()) if self.asset=="BTC" else None
        # Chain monitor: insert the seed trade as soon as it hits Polygon.
        # Same activity key as REST, so the public list cannot double-copy.
        chain_task=None
        monitor=None
        if self.asset=="BTC":
            chain_wss=os.environ.get('ALCHEMY_WSS')
            chain_urls=[u for u in ((chain_wss,) if chain_wss else DEFAULT_CHAIN_WSS) + DEFAULT_CHAIN_WSS if u]
            chain_urls=list(dict.fromkeys(chain_urls))
            if chain_urls:
                from .wallet_chain_monitor import ChainMonitor, ChainBridge
                bridge=ChainBridge(self.store,get_json)
                monitor=ChainMonitor(chain_urls,get_active_wallets(self.store),bridge.on_event)
                chain_task=asyncio.create_task(monitor.run())
                LOG.info('chain monitor: detect on-chain → copy without waiting for the public list')
            else:
                LOG.info('ALCHEMY_WSS not set; REST-only polling')
        last_wallet_refresh=time.time()
        try:
            while True:
                await self.iteration()
                # Refresh chain monitor wallet set every 60s
                if monitor and time.time()-last_wallet_refresh>=60:
                    monitor.update_wallets(get_active_wallets(self.store))
                    last_wallet_refresh=time.time()
                await asyncio.sleep(2)
        finally:
            reference.cancel()
            if wallets:wallets.cancel()
            if discovery:discovery.cancel()
            if copier:copier.cancel()
            if chain_task:chain_task.cancel()
            await asyncio.gather(reference,*([wallets] if wallets else []),*([discovery] if discovery else []),*([copier] if copier else []),*([chain_task] if chain_task else []),return_exceptions=True)

def main():
    import fcntl
    logging.basicConfig(level=logging.INFO)
    data=Path(os.environ.get('LAB_DATA','./runtime'))
    asset=os.environ.get('LAB_ASSET','BTC')
    if asset not in ('BTC','ETH'):raise SystemExit('unsupported asset')
    if asset=='ETH':data=data/'eth'
    data.mkdir(parents=True,exist_ok=True)
    with (data/'worker.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        store=Store(data/'lab.sqlite',asset=asset)
        if asset=='ETH':store.set('model',{'status':'NOT_USED','samples':0,'reason':'Separate normalized-momentum PAPER hypothesis; no BTC-trained model.'})
        asyncio.run(Worker(store,data).run())

if __name__=='__main__': main()



