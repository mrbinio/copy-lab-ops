"""Forward-only fixed-size wallet-signal copy with optional CLOB live orders."""
import asyncio
import copy
import json
import logging
import math
import re
import time
from datetime import datetime
from decimal import Decimal, ROUND_FLOOR
from urllib.parse import quote
from .core import VenueClock, simulate_fill
from .mid_window import simulate_sale
from .reference import classify_rule
from .wallet_observer import get_active_wallets, wallet_label
from .strategy_control import is_paused as copy_paused, pauses as copy_pauses
from .copy_totals import summarize as copy_summarize, path_stats, path_record

log = logging.getLogger(__name__)

class CopyLedgerError(ValueError):pass

KEY='wallet_copy_execution'
INITIAL=500_000_000
BUDGET=5_000_000  # hard cap; the ticket itself is one market minimum
MIN_SOURCE_PRICE=Decimal('0.20')
MAX_SOURCE_PRICE=Decimal('0.70')

def market_spec(raw, event, now):
    slug=str(event.get('slug',''))
    match=re.fullmatch(r'(btc|eth)-updown-(5m|15m)-(\d+)',slug)
    if not match or raw.get('slug')!=slug:raise ValueError('UNSUPPORTED_MARKET')
    asset,interval,start=match.groups();start=int(start);end=start+(300 if interval=='5m' else 900)
    def timestamp(value):
        d=datetime.fromisoformat(value.replace('Z','+00:00'))
        if d.tzinfo is None:raise ValueError('MISSING_TIMEZONE')
        return d.timestamp()
    if timestamp(raw['eventStartTime'])!=start or timestamp(raw['endDate'])!=end:raise ValueError('WINDOW_MISMATCH')
    if not start<=now<end or raw.get('active') is not True or raw.get('closed') is not False or raw.get('acceptingOrders') is not True:raise ValueError('MARKET_CLOSED')
    if str(raw.get('conditionId'))!=str(event.get('conditionId')):raise ValueError('CONDITION_MISMATCH')
    names=raw['outcomes'];tokens=raw['clobTokenIds']
    names=json.loads(names) if isinstance(names,str) else names
    tokens=json.loads(tokens) if isinstance(tokens,str) else tokens
    if len(names)!=2 or set(names)!={'Up','Down'} or len(tokens)!=2 or len(set(tokens))!=2:raise ValueError('TOKEN_MAPPING')
    mapping=dict(zip(map(str,tokens),names));token=str(event.get('asset',''))
    if token not in mapping:raise ValueError('TOKEN_MISMATCH')
    kind,topic,schema=classify_rule(raw.get('description',''),asset.upper())
    if topic is None:raise ValueError('RULE_UNVERIFIED')
    fees=raw.get('feeSchedule') or {}
    if raw.get('feesEnabled') is False:rate=0
    elif raw.get('feesEnabled') is True and fees.get('exponent')==1 and 'rate' in fees:rate=float(fees['rate'])
    else:raise ValueError('FEE_UNVERIFIED')
    if not math.isfinite(rate) or not 0<=rate<=1:raise ValueError('FEE_INVALID')
    return dict(slug=slug,asset=asset.upper(),interval=interval,start=start,end=end,condition=raw['conditionId'],
                token=token,side=mapping[token],fee_rate=rate,rule_kind=kind,description=raw.get('description',''))

def public_trade(t):
    fields='id wallet strategy market condition asset interval token side end status opened shares cost fee exit_fee payout closed_at resolved pnl_micro official_seen_at'.split()
    result={k:t[k] for k in fields if k in t}
    e=t.get('entry_evidence',{})
    result.update(source_transaction=e.get('source_event',{}).get('transactionHash'),source_price=e.get('source_event',{}).get('price'),
        source_timestamp=e.get('source_timestamp'),first_seen=e.get('first_seen'),copy_delay=e.get('copy_delay'),
        entry_fill=t.get('entry_fill'),exit_fill=t.get('exit_evidence',{}).get('fill'))
    return result

class WalletCopy:
    # Max total CLOB exposure across all open orders (safety cap)
    CLOB_MAX_EXPOSURE_USD = 10.0

    def __init__(self,store,fetch,paused=lambda:False,clock=time.time,sleep=asyncio.sleep,clob_client=None):
        self.store,self.fetch,self.paused,self.clock,self.sleep=store,fetch,paused,clock,sleep
        self.clob_client = clob_client
        self._clob_exposure_usd = 0.0  # running total of CLOB orders placed
        self._market_cache={}
        with store.connect() as db:
            db.executescript('''
              CREATE TABLE IF NOT EXISTS wallet_copy_skip_reviews(wallet TEXT,event_key TEXT,end REAL,checked REAL DEFAULT 0,body TEXT,PRIMARY KEY(wallet,event_key));
              CREATE TABLE IF NOT EXISTS wallet_copy_accounts(wallet TEXT PRIMARY KEY,cash INTEGER NOT NULL);
              CREATE TABLE IF NOT EXISTS wallet_copy_events(wallet TEXT,event_key TEXT,ts REAL,reason TEXT,body TEXT,PRIMARY KEY(wallet,event_key));
              CREATE TABLE IF NOT EXISTS wallet_copy_positions(id TEXT PRIMARY KEY,wallet TEXT,body TEXT);
              CREATE TABLE IF NOT EXISTS wallet_copy_ledger(id TEXT PRIMARY KEY,wallet TEXT,amount INTEGER NOT NULL);
            ''')
            for wallet in get_active_wallets(store):db.execute('INSERT OR IGNORE INTO wallet_copy_accounts VALUES (?,?)',(wallet,INITIAL))
            db.execute("UPDATE wallet_copy_events SET reason='ABORTED_ON_RESTART' WHERE reason='PROCESSING'")
        if not store.get('wallet_copy_start',{}):store.set('wallet_copy_start',{'at':clock()})
        self.started=store.get('wallet_copy_start',{})['at']
        try:
            from .wallet_roster import tick as roster_tick
            roster_tick(store, clock())
        except Exception:
            pass
        self.last_publish=0
        self.book_clock=VenueClock()
        if not hasattr(store,"wallet_activity_ready"):store.wallet_activity_ready=asyncio.Event()
        self.publish('STARTED')

    def positions(self,db):return [json.loads(r[0]) for r in db.execute('SELECT body FROM wallet_copy_positions')]

    def publish(self,status,error=None):
        now=self.clock()
        with self.store.connect() as db:
            trades=self.positions(db);accounts=[]
            for wallet in get_active_wallets(self.store):
                db.execute('INSERT OR IGNORE INTO wallet_copy_accounts VALUES (?,?)',(wallet,INITIAL))
                rows=[t for t in trades if t['wallet']==wallet]
                closed=sorted((t for t in rows if t['status'] in ('CLOSED','SETTLED')),key=lambda t:t['closed_at'])
                pnl=sum(t['pnl_micro'] for t in closed);exposure=sum(t['cost']+t['fee'] for t in rows if t['status'] in ('OPEN','RESOLVED'))
                cash=db.execute('SELECT cash FROM wallet_copy_accounts WHERE wallet=?',(wallet,)).fetchone()[0]
                ledger=db.execute('SELECT COALESCE(SUM(amount),0) FROM wallet_copy_ledger WHERE wallet=?',(wallet,)).fetchone()[0]
                if cash<0 or cash!=INITIAL+ledger or cash+exposure!=INITIAL+pnl:raise CopyLedgerError('COPY_LEDGER_MISMATCH')
                curve=[];total=peak=dd=0
                for t in closed:
                    total+=t['pnl_micro'];peak=max(peak,total);dd=max(dd,peak-total);curve.append({'ts':t['closed_at'],'pnl':total/1e6})
                last=db.execute('SELECT ts,reason FROM wallet_copy_events WHERE wallet=? ORDER BY ts DESC,rowid DESC LIMIT 1',(wallet,)).fetchone()
                accounts.append(dict(id='copy-'+wallet,wallet=wallet,name='Copy '+wallet_label(wallet)+' · PAPER',initial=500,cash=cash/1e6,pnl=pnl/1e6,
                    fees=sum(t['fee']+t.get('exit_fee',0) for t in rows)/1e6,open_cost=exposure/1e6,pending=0,
                    trades=len(rows),settled=len(closed),wins=sum(t['pnl_micro']>0 for t in closed),curve=curve[-300:],
                    max_drawdown_usd=dd/1e6,independent_windows=len({t['market'] for t in closed}),
                    current_block=self.risk_reason(db,wallet,now),last_reason=last['reason'] if last else 'NO_NEW_SOURCE_TRADE',last_decision_at=last['ts'] if last else None))
            reasons=[dict(r) for r in db.execute('SELECT wallet,reason,COUNT(*) AS count FROM wallet_copy_events GROUP BY wallet,reason')]
            recent=[]
            for r in db.execute('SELECT wallet,event_key,ts,reason,body FROM wallet_copy_events ORDER BY ts DESC,rowid DESC LIMIT 30'):
                e=json.loads(r['body']);recent.append({k:r[k] for k in ('wallet','event_key','ts','reason')}|{'error':e.get('error'),'copy_delay':e.get('copy_delay')})
            errors=[dict(r)|{'detail':json.loads(r['body']).get('error')} for r in db.execute("SELECT wallet,event_key,ts,body FROM wallet_copy_events WHERE reason='ERROR' ORDER BY ts DESC LIMIT 30")]
        samples=[]
        for t in trades:
            path=(t.get('entry_evidence') or {}).get('path_ms')
            if path:samples.append(path)
        totals=copy_summarize(trades,copy_pauses(self.store),now,observed=len(get_active_wallets(self.store)),copy_wallets=list(get_active_wallets(self.store)),roster=self.store.get('wallet_roster',{}))
        self.store.set(KEY,dict(spec='wallet-signal-copy-v1',status=status,error=error,updated_at=now,started_at=self.started,
            mode='PAPER + CLOB' if self.clob_client else 'PAPER ONLY',accounts=accounts,recent_trades=[public_trade(t) for t in sorted(trades,key=lambda t:t['opened'],reverse=True)[:100]],
            trades_truncated=len(trades)>100,reasons=reasons,recent_decisions=recent,
            skip_review=self.skip_summary(),recent_errors=errors,entry_policy='copy-immediate-v7',
            totals=totals,path_ms=path_stats(samples[-200:]),
            clock_skew={'book':round(self.book_clock.skew(),3),'samples':len(self.book_clock.offsets)},
            scope='BTC/ETH 5m and 15m only; one market minimum (not $5 all-in), source price 20-70c; 500USD separate virtual scenarios; first SELL closes full copied lot',
            limitation='Not identical source sizing/partial exits. Public indexed activity,1s target polling,BUY<=30s age and +/-3c from source; SELL<=90s age; FOK at fresh delayed books with50% depth. No profitability guarantee.'))

    def skip_summary(self):
        with self.store.connect() as db:
            rows=[json.loads(r[0]) for r in db.execute('SELECT body FROM wallet_copy_skip_reviews ORDER BY end DESC LIMIT 100')]
            total=db.execute('SELECT COUNT(*) FROM wallet_copy_skip_reviews').fetchone()[0]
        return dict(spec='skip-outcome-v1',total=total,recent=rows,truncated=total>100,
            limitation='Shadow hold-to-settlement PnL only with recorded delayed full fill; otherwise null. Independent tickets, not portfolio or copied SELL returns.')

    def reason(self,row,reason,extra=None):
        event=json.loads(row['body']);now=self.clock()
        evidence=dict(source_event=event,source_timestamp=row['source_ts'],first_seen=row['first_seen'],
            decision_at=now,detection_delay=row['first_seen']-row['source_ts'],decision_delay=now-row['source_ts'],
            policy='source-band10c-age60s-v2',reason=reason,decision_book=None)
        evidence.update(extra or {})
        with self.store.connect() as db:
            db.execute('UPDATE wallet_copy_events SET reason=?,body=? WHERE wallet=? AND event_key=?',
                (reason,json.dumps(evidence,allow_nan=False),row['wallet'],row['event_key']))
            match=re.fullmatch(r'(btc|eth)-updown-(5m|15m)-(\d+)',str(event.get('slug','')))
            if (match and event.get('type')=='TRADE' and event.get('side')=='BUY'
                and reason not in ('PRE_ACTIVATION','SOURCE_IDENTITY_MISMATCH','NOT_BUY_OR_SELL')
                and row['source_ts']>=self.started and event.get('conditionId') and event.get('asset')):
                end=int(match[3])+(300 if match[2]=='5m' else 900)
                review=dict(evidence,status='PENDING',source_side_won=None,counterfactual_pnl=None)
                db.execute('INSERT OR IGNORE INTO wallet_copy_skip_reviews(wallet,event_key,end,body) VALUES (?,?,?,?)',
                    (row['wallet'],row['event_key'],end,json.dumps(review,allow_nan=False)))

    async def review_skips(self):
        now=self.clock()
        with self.store.connect() as db:
            rows=[dict(r) for r in db.execute('SELECT * FROM wallet_copy_skip_reviews WHERE end<=? AND checked<=? ORDER BY checked,end LIMIT 5',(now,now-60))]
        for row in rows:
            review=json.loads(row['body'])
            if review['status']=='RESOLVED':continue
            event=review['source_event']
            try:
                raw=await asyncio.to_thread(self.fetch,'https://clob.polymarket.com/markets/'+quote(str(event['conditionId']),safe=''))
                if raw.get('condition_id')!=event['conditionId']:raise ValueError('REVIEW_CONDITION_MISMATCH')
                tokens=raw.get('tokens',[]);winners=[t for t in tokens if t.get('winner') is True]
                if raw.get('closed') is True and len(winners)==1:
                    if str(event['asset']) not in {str(t['token_id']) for t in tokens}:raise ValueError('REVIEW_TOKEN_MISMATCH')
                    review.update(status='RESOLVED',source_side_won=str(winners[0]['token_id'])==str(event['asset']),official_seen_at=self.clock())
                self.score_shadow(review)
                review.pop('error',None)
            except Exception as error:
                review['error']=str(error)[:200]
            with self.store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                current=json.loads(db.execute('SELECT body FROM wallet_copy_skip_reviews WHERE wallet=? AND event_key=?',(row['wallet'],row['event_key'])).fetchone()[0])
                if 'shadow' in current:review['shadow']=current['shadow']
                self.score_shadow(review)
                db.execute('UPDATE wallet_copy_skip_reviews SET checked=?,body=? WHERE wallet=? AND event_key=?',
                    (1e30 if review['status']=='RESOLVED' else now,json.dumps(review),row['wallet'],row['event_key']))

    def risk_reason(self,db,wallet,now):
        rows=[t for t in self.positions(db) if t['wallet']==wallet]
        if sum(1 for t in rows if t['status'] in ('OPEN','RESOLVED'))>=5:return 'COPY_POSITION_ALREADY_OPEN'
        if db.execute('SELECT cash FROM wallet_copy_accounts WHERE wallet=?',(wallet,)).fetchone()[0]<BUDGET:return 'COPY_CASH_LIMIT'
        return None

    def risk(self,db,wallet,now):return self.risk_reason(db,wallet,now) is None

    def paper_pnl_micro(self,db,wallet):
        return sum(t['pnl_micro'] for t in self.positions(db) if t['wallet']==wallet and t['status'] in ('CLOSED','SETTLED'))

    async def book(self,token):
        from .worker import normalize_book
        raw=await asyncio.to_thread(self.fetch,'https://clob.polymarket.com/book?token_id='+quote(token,safe=''))
        return normalize_book(raw,token,self.clock(),max_age=15,venue_clock=self.book_clock)

    def pending_activity(self,db,active=None):
        """Only fresh rows. A full-table INSERT every second blocked the event loop
        and the WebSocket handshakes timed out while SQLite held the thread."""
        active=list(active if active is not None else get_active_wallets(self.store))
        now=self.clock()
        if not active:
            return []
        db.execute('CREATE INDEX IF NOT EXISTS wallet_activity_seen ON wallet_activity(first_seen)')
        marks=','.join('?'*len(active))
        return [dict(r) for r in db.execute(
            f"SELECT a.* FROM wallet_activity a LEFT JOIN wallet_copy_events e "
            f"ON a.wallet=e.wallet AND a.event_key=e.event_key "
            f"WHERE e.event_key IS NULL AND a.wallet IN ({marks}) AND a.first_seen>=? "
            f"ORDER BY a.first_seen ASC LIMIT 20",(*active, now-90))]

    async def process(self,row):
        await self._process(row)
        # Independent diagnostic; never changes cash, risk or the actual copy decision.
        with self.store.connect() as db:
            saved=db.execute('SELECT body FROM wallet_copy_skip_reviews WHERE wallet=? AND event_key=?',
                (row['wallet'],row['event_key'])).fetchone()
        if not saved:return
        review=json.loads(saved[0])
        if 'shadow' in review:return
        shadow=dict(policy='skip-hold-arrival-v1',status='UNAVAILABLE',pnl_micro=None,
            limitation='Independent 5USD hypothetical ticket held to official settlement; not source SELL replication or portfolio returns.')
        event=review['source_event']
        try:
            now=self.clock()
            # COPY_PAUSED still gets a hypothetical ticket. Real buys stay blocked.
            # SOURCE_TOO_OLD does not: a reboot must not invent late copies.
            if self.paused() or review['reason'] in ('PAUSED','ERROR','SOURCE_TOO_OLD','SOURCE_IDENTITY_MISMATCH','SOURCE_PRICE_INVALID'):raise ValueError('NOT_ELIGIBLE_FOR_SHADOW')
            if not 0<=now-review['decision_at']<=5:raise ValueError('CAPTURE_TOO_LATE_NO_BACKFILL')
            raw=await asyncio.to_thread(self.fetch,'https://gamma-api.polymarket.com/markets/slug/'+quote(event['slug'],safe=''))
            m=market_spec(raw,event,self.clock())
            decision=await self.book(m['token']);at=self.clock()
            if not (0<=self.book_clock.age(decision['source_ts'],at)<=5 and decision['asks']):raise ValueError('DECISION_STALE_OR_EMPTY')
            limit=min(Decimal('.999999'),min(Decimal(p) for p,q in decision['asks'])+Decimal('.02'))
            shadow.update(decision_book=decision,decision_at=at,limit=str(limit))
            await self.sleep(.25)
            arrival=await self.book(m['token']);now=self.clock()
            shadow.update(arrival_book=arrival,arrival_at=now,source_to_arrival_seconds=now-row['source_ts'])
            if not (.25<=now-at<=5 and 0<=self.book_clock.age(arrival['source_ts'],now)<=5 and arrival['source_ts']>decision['source_ts']
                    and arrival['received_at']>=at+.25 and now<m['end']):raise ValueError('ARRIVAL_INVALID')
            ask=min(Decimal(p) for p,q in arrival['asks'])
            notional=(Decimal(str(arrival['min_shares']))*ask).quantize(Decimal('.000001'),rounding=ROUND_FLOOR)
            fill=simulate_fill(arrival['asks'],notional,limit,m['fee_rate'],arrival['min_shares'],arrival['tick'])
            if fill and fill['cost']+fill['fee']<=BUDGET:
                shadow.update(status='FILLED_PENDING_SETTLEMENT',fill=fill,fee_rate=m['fee_rate'])
            else:shadow['status']='NO_FULL_FILL'
        except Exception as error:shadow['error']=str(error)[:200]
        # Merge with latest review so background settlement cannot be overwritten.
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            latest=json.loads(db.execute('SELECT body FROM wallet_copy_skip_reviews WHERE wallet=? AND event_key=?',
                (row['wallet'],row['event_key'])).fetchone()[0])
            latest['shadow']=shadow
            self.score_shadow(latest)
            db.execute('UPDATE wallet_copy_skip_reviews SET body=? WHERE wallet=? AND event_key=?',
                (json.dumps(latest),row['wallet'],row['event_key']))

    @staticmethod
    def score_shadow(review):
        shadow=review.get('shadow',{})
        if review.get('status')=='RESOLVED' and shadow.get('status')=='FILLED_PENDING_SETTLEMENT':
            fill=shadow['fill'];payout=fill['shares'] if review['source_side_won'] else 0
            shadow.update(status='SETTLED',payout_micro=payout,pnl_micro=payout-fill['cost']-fill['fee'])
            review['counterfactual_pnl']=shadow['pnl_micro']/1e6

    async def _process(self,row):
        queued_at=self.clock();wallet=row['wallet'];key=row['event_key'];event=json.loads(row['body'])
        now=queued_at
        with self.store.connect() as db:
            inserted=db.execute('INSERT OR IGNORE INTO wallet_copy_events VALUES (?,?,?,?,?)',(wallet,key,now,'PROCESSING','{}')).rowcount
        if not inserted:return
        try:
            if row['first_seen']<self.started or row['source_ts']<self.started:self.reason(row,'PRE_ACTIVATION');return
            if not 0<=now-row['source_ts']<=90 or not 0<=now-row['first_seen']<=90:self.reason(row,'SOURCE_TOO_OLD');return
            if str(event.get('proxyWallet','')).lower()!=wallet or float(event.get('timestamp',0))!=row['source_ts']:
                self.reason(row,'SOURCE_IDENTITY_MISMATCH');return
            if event.get('type')!='TRADE' or event.get('side') not in ('BUY','SELL'):self.reason(row,'NOT_BUY_OR_SELL');return
            if self.paused():self.reason(row,'PAUSED');return
            if copy_paused(self.store,'copy-'+wallet):self.reason(row,'COPY_PAUSED');return
            if not re.fullmatch(r'(btc|eth)-updown-(5m|15m)-\d+',str(event.get('slug',''))):self.reason(row,'UNSUPPORTED_MARKET');return
            slug=str(event['slug'])
            raw=await asyncio.to_thread(self.fetch,'https://gamma-api.polymarket.com/markets/slug/'+quote(slug,safe=''))
            m=market_spec(raw,event,self.clock());kind=event['side']
            with self.store.connect() as db:
                open_trade=next((t for t in self.positions(db) if t['wallet']==wallet and t['token']==m['token'] and t['status']=='OPEN'),None)
                blocked=self.risk_reason(db,wallet,self.clock()) if kind=='BUY' else None
                if blocked:self.reason(row,blocked);return
                if kind=='BUY' and any(t for t in self.positions(db) if t['wallet']==wallet and t['market']==m['slug'] and t['status'] in ('OPEN','RESOLVED')):self.reason(row,'COPY_POSITION_ALREADY_OPEN');return
                if kind=='SELL' and not open_trade:self.reason(row,'NO_COPIED_POSITION');return
            if kind=='BUY':
                source_price=Decimal(str(event.get('price',0)))
                if not source_price.is_finite() or not 0<source_price<1:self.reason(row,'SOURCE_PRICE_INVALID');return
                if source_price<MIN_SOURCE_PRICE:self.reason(row,'COPY_PRICE_TOO_LOW');return
                if source_price>MAX_SOURCE_PRICE:self.reason(row,'COPY_PRICE_TOO_HIGH');return
            t_book=self.clock();decision=await self.book(m['token']);at=self.clock()
            if kind=='BUY':
                if not decision['asks']:self.reason(row,'NO_ASK');return
                ask=min(Decimal(p) for p,q in decision['asks'])
                limit=min(Decimal('.999999'),ask+Decimal('.02'))
            else:
                if not decision['bids']:self.reason(row,'NO_BID');return
                limit=max(Decimal(decision['tick']),max(Decimal(p) for p,q in decision['bids'])-Decimal('.02'))
            now=self.clock()
            timing=path_record(event,row,queued_at,t_book,at,now)
            # From the API timestamp only. chain_fast has no source-trade clock.
            copy_delay=None if timing['detect_from_trade_ms'] is None else now-row['source_ts']
            evidence=dict(source_event=event,source_timestamp=row['source_ts'],first_seen=row['first_seen'],decision_at=at,arrival_at=now,
                detection_delay=None if timing['detect_from_trade_ms'] is None else timing['detect_from_trade_ms']/1000,
                copy_delay=copy_delay,
                path_ms=timing,
                decision_book=decision,arrival_book=decision,market_metadata=raw)
            if kind=='BUY':
                evidence['copy_policy']='copy-min-lot-20-70c-v1'
                # One market minimum, not $5 every time. Cheap losers were a $5 hole.
                notional=(Decimal(str(decision['min_shares']))*ask).quantize(Decimal('.000001'),rounding=ROUND_FLOOR)
                fill=simulate_fill(decision['asks'],notional,limit,m['fee_rate'],decision['min_shares'],decision['tick'])
                evidence['path_ms']['paper_ms']=round((self.clock()-now)*1000,1)
                if not fill or fill['cost']+fill['fee']>BUDGET:self.reason(row,'BUY_NO_FULL_FILL_OR_MINIMUM',evidence);return
                trade=dict(id=wallet+':'+key,wallet=wallet,strategy='copy-'+wallet,market=m['slug'],condition=m['condition'],asset=m['asset'],interval=m['interval'],
                    token=m['token'],side=m['side'],end=m['end'],status='OPEN',opened=now,shares=fill['shares'],cost=fill['cost'],fee=fill['fee'],exit_fee=0,
                    entry_evidence=evidence,entry_fill=fill)
                with self.store.connect() as db:
                    db.execute('BEGIN IMMEDIATE')
                    if not self.risk(db,wallet,now):raise ValueError('RISK_CHANGED')
                    db.execute('INSERT INTO wallet_copy_positions VALUES (?,?,?)',(trade['id'],wallet,json.dumps(trade)))
                    debit=-(trade['cost']+trade['fee'])
                    db.execute('UPDATE wallet_copy_accounts SET cash=cash+? WHERE wallet=?',(debit,wallet))
                    db.execute('INSERT INTO wallet_copy_ledger VALUES (?,?,?)',('buy:'+trade['id'],wallet,debit))
                    db.execute("UPDATE wallet_copy_events SET reason='COPIED_BUY',body=? WHERE wallet=? AND event_key=?",(json.dumps(evidence),wallet,key))
                if self.clob_client:
                    evidence['clob_order']=await self.place_clob_buy(wallet,m['token'],limit,fill)
                    with self.store.connect() as db:
                        db.execute("UPDATE wallet_copy_events SET body=? WHERE wallet=? AND event_key=?",
                            (json.dumps(evidence),wallet,key))
            else:
                fill=simulate_sale(decision,open_trade['shares'],m['fee_rate'],limit)
                if not fill:self.reason(row,'SELL_NO_FULL_FILL',evidence);return
                self.close(open_trade,fill['proceeds'],fill['fee'],now,'CLOSED',{'fill':fill,'evidence':evidence},row)
        except Exception as error:self.reason(row,'ERROR',{'error':str(error)[:400]})

    async def place_clob_buy(self,wallet,token,limit,fill):
        with self.store.connect() as db:
            pnl=self.paper_pnl_micro(db,wallet)
        if pnl<0:
            log.info('CLOB skipped %s: paper result is negative',wallet[-8:])
            return {'ok':False,'reason':'PAPER_NEGATIVE','pnl_usd':pnl/1e6}
        clob_budget=min(5.0,float(fill['cost']+fill['fee'])/1e6)
        clob_price=float(limit)
        clob_size=clob_budget/clob_price if clob_price>0 else 0
        remaining=self.CLOB_MAX_EXPOSURE_USD-self._clob_exposure_usd
        if clob_budget>remaining:
            clob_budget=max(0,remaining)
            clob_size=clob_budget/clob_price if clob_price>0 else 0
        log.info('CLOB BUY attempt: token=%s price=%.4f size=%.2f budget=$%.2f exposure=$%.2f/%s',
                 token[:16],clob_price,clob_size,clob_budget,self._clob_exposure_usd,self.CLOB_MAX_EXPOSURE_USD)
        if clob_budget<0.50 or clob_size<5:
            return {'ok':False,'reason':'BELOW_MINIMUM','budget':clob_budget,'size':clob_size,'remaining_exposure':remaining}
        try:
            result=await asyncio.to_thread(self.clob_client.buy,token,clob_price,round(clob_size,2))
            if result.get('ok'):
                self._clob_exposure_usd+=clob_budget
            log.info('CLOB order result: %s',json.dumps(result,default=str)[:500])
            return result
        except Exception as error:
            log.error('CLOB order error: %s',error)
            return {'ok':False,'error':str(error)[:400]}

    def close(self,trade,payout,fee,now,status,evidence,row=None):
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            current=json.loads(db.execute('SELECT body FROM wallet_copy_positions WHERE id=?',(trade['id'],)).fetchone()[0])
            if current['status'] not in ('OPEN','RESOLVED'):return
            current.update(status=status,payout=payout,exit_fee=fee,closed_at=now,resolved=now,
                pnl_micro=payout-fee-current['cost']-current['fee'],exit_evidence=evidence)
            db.execute('UPDATE wallet_copy_positions SET body=? WHERE id=?',(json.dumps(current),trade['id']))
            db.execute('UPDATE wallet_copy_accounts SET cash=cash+? WHERE wallet=?',(payout-fee,trade['wallet']))
            db.execute('INSERT INTO wallet_copy_ledger VALUES (?,?,?)',('close:'+trade['id'],trade['wallet'],payout-fee))
            if row:db.execute("UPDATE wallet_copy_events SET reason='COPIED_SELL',body=? WHERE wallet=? AND event_key=?",(json.dumps(evidence),row['wallet'],row['event_key']))

    async def settle(self):
        now=self.clock()
        with self.store.connect() as db:trades=self.positions(db)
        for trade in trades:
            if trade['status']=='RESOLVED':
                if now>=trade['official_seen_at']+300:self.close(trade,trade['official_payout'],0,now,'SETTLED',trade['official_evidence'])
                continue
            if trade['status']!='OPEN' or now<trade['end']:continue
            raw=await asyncio.to_thread(self.fetch,'https://clob.polymarket.com/markets/'+quote(trade['condition'],safe=''))
            if raw.get('condition_id')!=trade['condition']:raise ValueError('SETTLEMENT_CONDITION_MISMATCH')
            winners=[t for t in raw.get('tokens',[]) if t.get('winner') is True]
            if raw.get('closed') is not True or len(winners)!=1:continue
            tokens={str(t['token_id']) for t in raw['tokens']}
            if trade['token'] not in tokens:raise ValueError('SETTLEMENT_TOKEN_MISMATCH')
            trade.update(status='RESOLVED',official_seen_at=self.clock(),official_evidence=raw,
                official_payout=trade['shares'] if str(winners[0]['token_id'])==trade['token'] else 0)
            with self.store.connect() as db:db.execute('UPDATE wallet_copy_positions SET body=? WHERE id=?',(json.dumps(trade),trade['id']))

    async def upkeep(self):
        """Settlement and skip review, beside the copy path instead of inside it.

        Settling an ended window costs one request per position. Running that
        before new activity delayed a fresh copy by up to three seconds.
        """
        while True:
            for job, key, width in ((self.settle, 'wallet_copy_settlement_error', 400),
                                    (self.review_skips, 'wallet_skip_review_error', 200)):
                try:
                    await job()
                    self.store.set(key, {})
                except Exception as error:
                    self.store.set(key, {'at': self.clock(), 'error': str(error)[:width]})
            await self.sleep(30)

    def _load_pending(self, active):
        with self.store.connect() as db:
            has=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='wallet_activity'").fetchone()
            return self.pending_activity(db, active) if has else []

    async def step(self):
        try:
            # Observer wakes this loop immediately after persisting new activity.
            # The read runs off the event loop so a slow query cannot freeze RTDS.
            active=list(get_active_wallets(self.store))
            rows=await asyncio.to_thread(self._load_pending, active)
            for row in rows:
                await self.process(row)
            if rows or self.clock()-self.last_publish>=2:
                self.publish('RUNNING');self.last_publish=self.clock()
            self.store.set('wallet_copy_error',{})
        except Exception as error:
            # A ledger mismatch blocks further execution until process/operator review.
            self.store.set('wallet_copy_error',{'at':self.clock(),'error':str(error)[:400]})
            raise

    async def run(self):
        upkeep=asyncio.create_task(self.upkeep())
        try:
            while True:
                self.store.wallet_activity_ready.clear()
                try:await self.step()
                except CopyLedgerError:
                    log.error('copy ledger mismatch; retrying in 30s')
                    await self.sleep(30)
                    continue
                except Exception:
                    await self.sleep(10)
                    continue
                try:await asyncio.wait_for(self.store.wallet_activity_ready.wait(),timeout=1)
                except asyncio.TimeoutError:pass
        finally:
            upkeep.cancel()
