"""Forward-only fixed-size wallet-signal PAPER copy. Never signs real orders."""
import asyncio
import json
import math
import re
import time
from datetime import datetime
from decimal import Decimal, ROUND_FLOOR
from urllib.parse import quote
from .core import simulate_fill
from .mid_window import simulate_sale
from .reference import classify_rule
from .wallet_observer import WALLETS

class CopyLedgerError(ValueError):pass

KEY='wallet_copy_execution'
INITIAL=500_000_000
BUDGET=5_000_000  # all-in paper cap; not a live allocation

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
    def __init__(self,store,fetch,paused=lambda:False,clock=time.time,sleep=asyncio.sleep):
        self.store,self.fetch,self.paused,self.clock,self.sleep=store,fetch,paused,clock,sleep
        with store.connect() as db:
            db.executescript('''
              CREATE TABLE IF NOT EXISTS wallet_copy_skip_reviews(wallet TEXT,event_key TEXT,end REAL,checked REAL DEFAULT 0,body TEXT,PRIMARY KEY(wallet,event_key));
              CREATE TABLE IF NOT EXISTS wallet_copy_accounts(wallet TEXT PRIMARY KEY,cash INTEGER NOT NULL);
              CREATE TABLE IF NOT EXISTS wallet_copy_events(wallet TEXT,event_key TEXT,ts REAL,reason TEXT,body TEXT,PRIMARY KEY(wallet,event_key));
              CREATE TABLE IF NOT EXISTS wallet_copy_positions(id TEXT PRIMARY KEY,wallet TEXT,body TEXT);
              CREATE TABLE IF NOT EXISTS wallet_copy_ledger(id TEXT PRIMARY KEY,wallet TEXT,amount INTEGER NOT NULL);
            ''')
            for wallet in WALLETS:db.execute('INSERT OR IGNORE INTO wallet_copy_accounts VALUES (?,?)',(wallet,INITIAL))
            db.execute("UPDATE wallet_copy_events SET reason='ABORTED_ON_RESTART' WHERE reason='PROCESSING'")
        if not store.get('wallet_copy_start',{}):store.set('wallet_copy_start',{'at':clock()})
        self.started=store.get('wallet_copy_start',{})['at']
        self.last_settlement=0
        self.review_task=None
        self.last_publish=0
        if not hasattr(store,"wallet_activity_ready"):store.wallet_activity_ready=asyncio.Event()
        self.publish('STARTED')

    def positions(self,db):return [json.loads(r[0]) for r in db.execute('SELECT body FROM wallet_copy_positions')]

    def publish(self,status,error=None):
        now=self.clock()
        with self.store.connect() as db:
            trades=self.positions(db);accounts=[]
            for wallet in WALLETS:
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
                accounts.append(dict(id='copy-'+wallet,wallet=wallet,name='Copy '+wallet[-8:]+' · PAPER',initial=500,cash=cash/1e6,pnl=pnl/1e6,
                    fees=sum(t['fee']+t.get('exit_fee',0) for t in rows)/1e6,open_cost=exposure/1e6,pending=0,
                    trades=len(rows),settled=len(closed),wins=sum(t['pnl_micro']>0 for t in closed),curve=curve[-300:],
                    max_drawdown_usd=dd/1e6,independent_windows=len({t['market'] for t in closed}),
                    current_block=self.risk_reason(db,wallet,now),last_reason=last['reason'] if last else 'NO_NEW_SOURCE_TRADE',last_decision_at=last['ts'] if last else None))
            reasons=[dict(r) for r in db.execute('SELECT wallet,reason,COUNT(*) AS count FROM wallet_copy_events GROUP BY wallet,reason')]
            recent=[]
            for r in db.execute('SELECT wallet,event_key,ts,reason,body FROM wallet_copy_events ORDER BY ts DESC,rowid DESC LIMIT 30'):
                e=json.loads(r['body']);recent.append({k:r[k] for k in ('wallet','event_key','ts','reason')}|{'error':e.get('error'),'copy_delay':e.get('copy_delay')})
            errors=[dict(r)|{'detail':json.loads(r['body']).get('error')} for r in db.execute("SELECT wallet,event_key,ts,body FROM wallet_copy_events WHERE reason='ERROR' ORDER BY ts DESC LIMIT 30")]
        self.store.set(KEY,dict(spec='wallet-signal-copy-v1',status=status,error=error,updated_at=now,started_at=self.started,
            mode='PAPER ONLY',accounts=accounts,recent_trades=[public_trade(t) for t in sorted(trades,key=lambda t:t['opened'],reverse=True)[:100]],
            trades_truncated=len(trades)>100,reasons=reasons,recent_decisions=recent,
            skip_review=self.skip_summary(),recent_errors=errors,entry_policy='source-band10c-age60s-v2',
            scope='BTC/ETH 5m and 15m only; fixed <=5USD all-in,500USD separate virtual scenarios; first SELL closes full copied lot',
            limitation='Not identical source sizing/partial exits. Public indexed activity,1s target polling,BUY<=60s age and +/-10c from source; SELL<=90s age; FOK at fresh delayed books with50% depth. No profitability guarantee.'))

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
        if any(t['status'] in ('OPEN','RESOLVED') for t in rows):return 'COPY_POSITION_ALREADY_OPEN'
        if db.execute('SELECT cash FROM wallet_copy_accounts WHERE wallet=?',(wallet,)).fetchone()[0]<BUDGET:return 'COPY_CASH_LIMIT'
        closed=[t for t in rows if t['status'] in ('CLOSED','SETTLED')]
        for h,cap,reason in [(86400,15_000_000,'COPY_DAY_LOSS_LIMIT'),(604800,30_000_000,'COPY_WEEK_LOSS_LIMIT')]:
            if sum(max(0,-t['pnl_micro']) for t in closed if now-h<=t['closed_at']<=now)+BUDGET>cap:return reason
        return None

    def risk(self,db,wallet,now):return self.risk_reason(db,wallet,now) is None

    async def book(self,token):
        from .worker import normalize_book
        raw=await asyncio.to_thread(self.fetch,'https://clob.polymarket.com/book?token_id='+quote(token,safe=''))
        return normalize_book(raw,token,self.clock())

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
            if self.paused() or review['reason'] in ('PAUSED','ERROR','SOURCE_TOO_OLD','SOURCE_IDENTITY_MISMATCH','SOURCE_PRICE_INVALID'):raise ValueError('NOT_ELIGIBLE_FOR_SHADOW')
            if not 0<=now-review['decision_at']<=5:raise ValueError('CAPTURE_TOO_LATE_NO_BACKFILL')
            raw=await asyncio.to_thread(self.fetch,'https://gamma-api.polymarket.com/markets/slug/'+quote(event['slug'],safe=''))
            m=market_spec(raw,event,self.clock())
            decision=await self.book(m['token']);at=self.clock()
            if not (0<=at-decision['source_ts']<=5 and decision['asks']):raise ValueError('DECISION_STALE_OR_EMPTY')
            limit=min(Decimal('.999999'),min(Decimal(p) for p,q in decision['asks'])+Decimal('.02'))
            shadow.update(decision_book=decision,decision_at=at,limit=str(limit))
            await self.sleep(.25)
            arrival=await self.book(m['token']);now=self.clock()
            shadow.update(arrival_book=arrival,arrival_at=now,source_to_arrival_seconds=now-row['source_ts'])
            if not (.25<=now-at<=5 and 0<=now-arrival['source_ts']<=5 and arrival['source_ts']>decision['source_ts']
                    and arrival['received_at']>=at+.25 and now<m['end']):raise ValueError('ARRIVAL_INVALID')
            notional=(Decimal(BUDGET)/1_000_000/(1+Decimal(str(m['fee_rate'])))).quantize(Decimal('.000001'),rounding=ROUND_FLOOR)
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
        now=self.clock();wallet=row['wallet'];key=row['event_key'];event=json.loads(row['body'])
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
            if not re.fullmatch(r'(btc|eth)-updown-(5m|15m)-\d+',str(event.get('slug',''))):self.reason(row,'UNSUPPORTED_MARKET');return
            raw=await asyncio.to_thread(self.fetch,'https://gamma-api.polymarket.com/markets/slug/'+quote(event['slug'],safe=''))
            m=market_spec(raw,event,self.clock());kind=event['side']
            with self.store.connect() as db:
                open_trade=next((t for t in self.positions(db) if t['wallet']==wallet and t['token']==m['token'] and t['status']=='OPEN'),None)
                blocked=self.risk_reason(db,wallet,self.clock()) if kind=='BUY' else None
                if blocked:self.reason(row,blocked);return
                if kind=='SELL' and not open_trade:self.reason(row,'NO_COPIED_POSITION');return
            decision=await self.book(m['token']);at=self.clock()
            if kind=='BUY':
                source_price=Decimal(str(event.get('price',0)))
                if not source_price.is_finite() or not 0<source_price<1:self.reason(row,'SOURCE_PRICE_INVALID');return
                if at-row['source_ts']>60:self.reason(row,'COPY_BUY_TOO_LATE',{'decision_book':decision});return
                if not decision['asks']:self.reason(row,'NO_ASK');return
                ask=min(Decimal(p) for p,q in decision['asks'])
                if ask-source_price>Decimal('.10') or source_price-ask>Decimal('.10'):self.reason(row,'SOURCE_PRICE_MOVED',{'decision_book':decision});return
                limit=min(Decimal('.999999'),ask+Decimal('.02'),source_price+Decimal('.10'))
            else:
                if not decision['bids']:self.reason(row,'NO_BID');return
                limit=max(Decimal(decision['tick']),max(Decimal(p) for p,q in decision['bids'])-Decimal('.02'))
            await self.sleep(.25)
            arrival=await self.book(m['token']);now=self.clock()
            if not (.25<=now-at<=5 and arrival['source_ts']>decision['source_ts'] and arrival['received_at']>=at+.25 and now<m['end'] and now-row['source_ts']<=90) or self.paused():self.reason(row,'ARRIVAL_REJECTED');return
            evidence=dict(source_event=event,source_timestamp=row['source_ts'],first_seen=row['first_seen'],decision_at=at,arrival_at=now,
                detection_delay=row['first_seen']-row['source_ts'],copy_delay=now-row['source_ts'],decision_book=decision,arrival_book=arrival,market_metadata=raw)
            if kind=='BUY':
                if now-row['source_ts']>60:self.reason(row,'COPY_BUY_TOO_LATE',evidence);return
                if not arrival['asks'] or (lambda a:a-source_price>Decimal('.10') or source_price-a>Decimal('.10'))(min(Decimal(p) for p,q in arrival['asks'])):self.reason(row,'SOURCE_PRICE_MOVED',evidence);return
                evidence['copy_policy']='source-band10c-age60s-v2'
                notional=(Decimal(BUDGET)/1_000_000/(1+Decimal(str(m['fee_rate'])))).quantize(Decimal('.000001'),rounding=ROUND_FLOOR)
                fill=simulate_fill(arrival['asks'],notional,limit,m['fee_rate'],arrival['min_shares'],arrival['tick'])
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
            else:
                fill=simulate_sale(arrival,open_trade['shares'],m['fee_rate'],limit)
                if not fill:self.reason(row,'SELL_NO_FULL_FILL',evidence);return
                self.close(open_trade,fill['proceeds'],fill['fee'],now,'CLOSED',{'fill':fill,'evidence':evidence},row)
        except Exception as error:self.reason(row,'ERROR',{'error':str(error)[:400]})

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

    async def step(self):
        try:
            # Observer wakes this loop immediately after persisting new activity.
            if self.clock()-self.last_settlement>=30:
                await self.settle();self.last_settlement=self.clock()
                if self.review_task is None or self.review_task.done():
                    if self.review_task is not None and not self.review_task.cancelled():
                        error=self.review_task.exception()
                        self.store.set('wallet_skip_review_error',{'at':self.clock(),'error':str(error)[:200]} if error else {})
                    self.review_task=asyncio.create_task(self.review_skips())
            with self.store.connect() as db:
                has=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='wallet_activity'").fetchone()
                if has:
                    db.execute("INSERT OR IGNORE INTO wallet_copy_events SELECT wallet,event_key,?,'PRE_ACTIVATION','{}' FROM wallet_activity WHERE source_ts<? OR first_seen<?",(self.clock(),self.started,self.started))
                rows=[dict(r) for r in db.execute('SELECT a.* FROM wallet_activity a LEFT JOIN wallet_copy_events e ON a.wallet=e.wallet AND a.event_key=e.event_key WHERE e.event_key IS NULL ORDER BY a.source_ts,a.first_seen LIMIT 100')] if has else []
            for row in rows:
                if row['wallet'] in WALLETS:await self.process(row)
            if rows or self.clock()-self.last_publish>=2:
                self.publish('RUNNING');self.last_publish=self.clock()
            self.store.set('wallet_copy_error',{})
        except Exception as error:
            # A ledger mismatch blocks further execution until process/operator review.
            self.store.set('wallet_copy_error',{'at':self.clock(),'error':str(error)[:400]})
            raise

    async def run(self):
        while True:
            self.store.wallet_activity_ready.clear()
            try:await self.step()
            except CopyLedgerError:return
            except Exception:
                await self.sleep(10)
                continue
            try:await asyncio.wait_for(self.store.wallet_activity_ready.wait(),timeout=1)
            except asyncio.TimeoutError:pass
