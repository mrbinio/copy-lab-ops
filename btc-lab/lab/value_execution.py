"""Isolated 100 USD PAPER ledger for value-surface-v1; no signed requests."""
import json
from decimal import Decimal, ROUND_FLOOR
from .core import simulate_fill
from .mid_window import simulate_sale

SPEC='value-surface-paper-v1'
INITIAL=100_000_000
KEY='value_surface_execution'

class ValueExecution:
    def __init__(self,store):
        self.store=store
        with store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS value_surface_positions (market TEXT PRIMARY KEY, body TEXT NOT NULL)')

    def _load(self,db):
        row=db.execute('SELECT body FROM state WHERE key=?',(KEY,)).fetchone()
        state=json.loads(row[0]) if row else dict(spec=SPEC,mode='PAPER ONLY',cash_micro=INITIAL,pending=None)
        trades=[json.loads(r[0]) for r in db.execute('SELECT body FROM value_surface_positions')]
        return state,trades

    def _save(self,db,s,trades,now,reason):
        closed=sorted((t for t in trades if t['status']!='OPEN'),key=lambda t:t['closed_at'])
        pnl=sum(t['pnl_micro'] for t in closed)
        exposure=sum(t['cost']+t['fee'] for t in trades if t['status']=='OPEN')
        if s['cash_micro']+exposure!=INITIAL+pnl:raise ValueError('value ledger invariant failed')
        peak=cumulative=dd=0;curve=[]
        for t in closed:
            cumulative+=t['pnl_micro'];peak=max(peak,cumulative);dd=max(dd,peak-cumulative)
            curve.append({'ts':t['closed_at'],'pnl':cumulative/1e6})
        s.update(updated_at=now,status=reason,initial_usd=100,cash_usd=s['cash_micro']/1e6,
            net_pnl_usd=pnl/1e6,open_cost_usd=exposure/1e6,max_drawdown_usd=dd/1e6,
            curve=curve[-300:],trades=len(trades),closed=len(closed),wins=sum(t['pnl_micro']>0 for t in closed),
            fees_usd=sum(t['fee']+t.get('exit_fee',0) for t in trades)/1e6,
            recent_trades=sorted(trades,key=lambda t:t['opened'],reverse=True)[:100],
            trades_truncated=len(trades)>100,execution_assumption='Delayed polling FOK, 50% displayed depth; no queue model')
        for t in trades:
            db.execute('INSERT OR REPLACE INTO value_surface_positions VALUES (?,?)',(t['market'],json.dumps(t,allow_nan=False)))
        db.execute('INSERT OR REPLACE INTO state VALUES (?,?)',(KEY,json.dumps(s,allow_nan=False)))

    def _risk(self,s,trades,budget,now):
        closed=[t for t in trades if t['status']!='OPEN']
        if any(t['status']=='OPEN' for t in trades):return False
        equity=INITIAL+sum(t['pnl_micro'] for t in closed)
        limit=min(INITIAL,equity)//100
        if not 0<budget<=min(limit,s['cash_micro']):return False
        if any(sum(max(0,-t['pnl_micro']) for t in closed if now-h<=t['closed_at']<=now)+budget>cap
               for h,cap in [(86400,3_000_000),(7*86400,6_000_000)]):return False
        cumulative=peak=0
        for t in sorted(closed,key=lambda t:t['closed_at']):
            cumulative+=t['pnl_micro'];peak=max(peak,cumulative)
        return peak-cumulative+budget<=8_000_000

    def settle(self,now):
        # Independent of live market collection, including on feed/REST failures.
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            s,trades=self._load(db);changed=False
            for t in trades:
                if t['status']!='OPEN':continue
                row=db.execute('SELECT winner,ts FROM labels WHERE market=?',(t['market'],)).fetchone()
                if not row or row['ts']>now or now<t['end']:continue
                payout=t['shares'] if row['winner']==t['side'] else 0
                t.update(status='SETTLED',payout=payout,exit_fee=0,closed_at=now,
                    pnl_micro=payout-t['cost']-t['fee'],exit_reason='OFFICIAL_RESOLUTION')
                s['cash_micro']+=payout;changed=True
            if changed:self._save(db,s,trades,now,'SETTLED')

    def step(self,m,reference,now,allowed=True):
        self.settle(now)
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            s,trades=self._load(db);reason='NO_SIGNAL'
            researchrow=db.execute("SELECT body FROM state WHERE key='opportunity_research'").fetchone()
            r=json.loads(researchrow[0]) if researchrow else {}
            ref_ok=(reference and 0<=now-reference['source_ts']<=5 and reference.get('topic')==m.get('reference_topic'))
            market_ok=m.get('rule_supported') and m.get('fee_verified') and m.get('accepting') and m['start']<=now<m['end']
            pending=s.get('pending')
            if pending:
                s['pending']=None
                b=m.get('books',{}).get(pending['side'],{})
                arrived=(pending['market']==m['slug'] and .25<=now-pending['at']<=5 and
                    b.get('source_ts',0)>pending['source_ts'] and b.get('received_at',0)>=pending['at']+.25 and
                    0<=now-b.get('source_ts',0)<=3 and 0<=now-b.get('received_at',0)<=3)
                if now-pending['at']<.25:
                    s['pending']=pending;reason='WAITING_ARRIVAL'
                elif not (arrived and market_ok and ref_ok and allowed and pending['rule_hash']==m.get('rule_hash')):reason='ARRIVAL_REJECTED'
                elif pending['kind']=='BUY':
                    budget=pending['budget_micro']
                    if any(t['market']==m['slug'] for t in trades) or not self._risk(s,trades,budget,now):reason='RISK_OR_DUPLICATE'
                    else:
                        # fee/cost <= rate; reserve conservatively, reject micro-rounding excess.
                        notional=(Decimal(budget)/1_000_000/(1+Decimal(str(m['fee_rate'])))).quantize(Decimal('.000001'),rounding=ROUND_FLOOR)
                        fill=simulate_fill(b['asks'],notional,pending['limit'],m['fee_rate'],b['min_shares'],b['tick'])
                        if not fill or fill['cost']+fill['fee']>budget:reason='BUY_NO_FULL_FILL'
                        else:
                            t=dict(market=m['slug'],side=pending['side'],status='OPEN',opened=now,end=m['end'],
                                shares=fill['shares'],cost=fill['cost'],fee=fill['fee'],entry_fill=fill,
                                decision=pending,exit_fee=0)
                            trades.append(t);s['cash_micro']-=t['cost']+t['fee'];reason='BOUGHT_PAPER'
                else:
                    t=next((t for t in trades if t['market']==m['slug'] and t['status']=='OPEN'),None)
                    fill=simulate_sale(b,t['shares'],m['fee_rate'],pending['floor']) if t else None
                    if not fill:reason='SELL_NO_FULL_FILL'
                    else:
                        t.update(status='CLOSED',payout=fill['proceeds'],exit_fee=fill['fee'],closed_at=now,
                            pnl_micro=fill['proceeds']-fill['fee']-t['cost']-t['fee'],exit_reason='VALUE_EXIT',exit_fill=fill)
                        s['cash_micro']+=fill['proceeds']-fill['fee'];reason='SOLD_PAPER'
                self._save(db,s,trades,now,reason);return
            current=(r.get('status')=='ESTIMATED_UNVALIDATED' and r.get('market')==m['slug'] and
                     r.get('rule_hash')==m.get('rule_hash') and 0<=now-r.get('updated_at',0)<=3)
            if not allowed:reason='PAUSED_OR_RECONCILIATION_BLOCK'
            elif not (market_ok and ref_ok and current):reason='WAITING_VALID_PROBABILITY'
            else:
                open_trade=next((t for t in trades if t['status']=='OPEN' and t['market']==m['slug']),None)
                if open_trade:
                    side=open_trade['side'];c=r.get('candidates',{}).get(side,{})
                    b=m['books'][side]
                    if 0<=now-b['source_ts']<=3 and 0<=now-b['received_at']<=3:
                        fill=simulate_sale(b,open_trade['shares'],m['fee_rate'])
                        if fill and (fill['proceeds']-fill['fee'])/open_trade['shares']>c.get('probability_high',1)+.01:
                            s['pending']=dict(kind='SELL',rule_hash=m.get('rule_hash'),market=m['slug'],side=side,at=now,source_ts=b['source_ts'],floor=fill['fills'][-1]['price'])
                            reason='SELL_PENDING'
                        else:reason='HOLD_VALUE_OR_NO_DEPTH'
                elif any(t['market']==m['slug'] for t in trades):reason='ALREADY_TRADED_WINDOW'
                else:
                    offers=[(c['conservative_edge_per_share'],side,c) for side,c in r.get('candidates',{}).items() if c.get('reason')=='RESEARCH_BUY_CANDIDATE']
                    if offers:
                        _,side,c=max(offers);budget=int(c['all_in_budget_usd']*1e6)
                        budget=min(budget,max(0,(INITIAL+sum(t.get('pnl_micro',0) for t in trades))//100))
                        b=m['books'][side]
                        if self._risk(s,trades,budget,now) and 0<=now-b['source_ts']<=3 and 0<=now-b['received_at']<=3:
                            s['pending']=dict(kind='BUY',rule_hash=m.get('rule_hash'),market=m['slug'],side=side,at=now,source_ts=b['source_ts'],
                                limit=c['max_price'],budget_micro=budget,model_id=r['model_id'],training_cutoff=r['training_cutoff'])
                            reason='BUY_PENDING'
                        else:reason='RISK_OR_STALE_BOOK'
                    else:reason='NO_NET_EDGE_OR_MINIMUM_SIZE'
            self._save(db,s,trades,now,reason)
