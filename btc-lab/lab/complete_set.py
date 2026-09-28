"""Read-only opportunity measurements. No orders, ledger fills or profit claims."""
import json
from decimal import Decimal as D, ROUND_CEILING
from .core import number
from .mid_window import simulate_sale

SPEC = 'complete-set-observer-v1'

def quote(book, quantity, rate, cap=None):
    """Equal share quantity, half displayed depth, conservative micro-fees."""
    tick=number(book['tick']); minimum=number(book['min_shares'])
    if tick<=0 or minimum<=0 or quantity<minimum: return None
    left=quantity; cost=D(0); fee=D(0); last=None
    for p,q in sorted((number(p),number(q)) for p,q in book['asks']):
        if not 0<p<1 or q<0 or p%tick: raise ValueError('invalid level')
        if cap is not None and p>cap: break
        take=min(left,q/2).quantize(D('.000001'),rounding='ROUND_FLOOR')
        cost+=take*p
        fee+=(take*rate*p*(1-p)).quantize(D('.000001'),rounding=ROUND_CEILING)
        left-=take;last=p
        if left==0:return {'cost':cost,'fee':fee,'cap':last}
    return None

def valid(m,now):
    if not m.get('rule_supported') or not m.get('fee_verified'):return False
    if not m['start']<=now<m['end']:return False
    books=[m['books'][s] for s in ('Up','Down')]
    if any(not 0<=now-b['source_ts']<=1 or not 0<=now-b['received_at']<=1 for b in books):return False
    return abs(books[0]['source_ts']-books[1]['source_ts'])<=.25 and abs(books[0]['received_at']-books[1]['received_at'])<=.25

class CompleteSetObserver:
    def __init__(self,store):
        self.store=store;self.pending=None
        with store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS complete_set_windows (market TEXT PRIMARY KEY, body TEXT NOT NULL)')

    def step(self,m,now):
        with self.store.connect() as db:
            r=db.execute('SELECT body FROM complete_set_windows WHERE market=?',(m['slug'],)).fetchone()
        row=json.loads(r[0]) if r else {'market':m['slug'],'first_at':now,'samples':0,'valid_samples':0,'positive_samples':0,'delayed_checks':0,'both_available':0,'one_leg_only':0,'neither_available':0,'expired_checks':0,'best_net_usd':None}
        row['samples']+=1;row['last_at']=now
        row['status']='INVALID_OR_UNSYNCHRONIZED'
        if valid(m,now):
            rate=number(m['fee_rate'])
            if not 0<=rate<=1:raise ValueError('fee')
            row['valid_samples']+=1
            q=max(D(5),*(number(m['books'][s]['min_shares']) for s in ('Up','Down')))
            fills={s:quote(m['books'][s],q,rate) for s in ('Up','Down')}
            row['status']='INSUFFICIENT_DEPTH'
            if all(fills.values()):
                cost=sum(f['cost']+f['fee'] for f in fills.values())
                net=q-cost-D('.02') # assumed operational reserve, not measured chain cost
                row['status']='OVER_BUDGET' if cost>10 else 'NO_NET_EDGE'
                if cost<=10:
                    row['best_net_usd']=max(row['best_net_usd'],float(net)) if row['best_net_usd'] is not None else float(net)
                    row['latest']={'quantity':str(q),'total_cost_usd':str(cost),'net_after_assumed_reserve_usd':str(net),'reserve_usd':'.02','source_ts':{s:m['books'][s]['source_ts'] for s in fills}}
                    if net>0:
                        row['positive_samples']+=1;row['status']='POSITIVE_QUOTE_NOT_A_FILL'
            p=self.pending
            if p and p['market']==m['slug'] and .25<=now-p['at']<=5 and all(m['books'][s]['source_ts']>p['sources'][s] and m['books'][s]['received_at']>=p['at']+.25 for s in fills):
                arrivals={s:quote(m['books'][s],p['q'],rate,p['caps'][s]) for s in fills}
                n=sum(f is not None for f in arrivals.values());row['delayed_checks']+=1
                row[{0:'neither_available',1:'one_leg_only',2:'both_available'}[n]]+=1
                row['last_delay_seconds']=now-p['at']
                if n==1:
                    side=next(s for s in arrivals if arrivals[s]);f=arrivals[side]
                    sale=simulate_sale(m['books'][side],int(p['q']*1000000),rate)
                    row['last_orphan']={'side':side,'full_loss_usd':str(f['cost']+f['fee']),'same_snapshot_unwind_net_usd':str(D(sale['proceeds']-sale['fee'])/1000000-f['cost']-f['fee']) if sale else None,'warning':'Diagnostic only; liquidation would require another delayed book.'}
                if n==2:row['last_delayed_net_usd']=str(p['q']-sum(f['cost']+f['fee'] for f in arrivals.values())-D('.02'))
                self.pending=None
            if self.pending and (self.pending['market']!=m['slug'] or now-self.pending['at']>5):
                row['expired_checks']+=1;self.pending=None
            if self.pending is None and row['status']=='POSITIVE_QUOTE_NOT_A_FILL':
                self.pending={'market':m['slug'],'at':now,'q':q,'caps':{s:fills[s]['cap'] for s in fills},'sources':{s:m['books'][s]['source_ts'] for s in fills}}
        with self.store.connect() as db:
            db.execute('INSERT OR REPLACE INTO complete_set_windows VALUES (?,?)',(m['slug'],json.dumps(row,allow_nan=False)))
            recent=[json.loads(r[0]) for r in db.execute('SELECT body FROM complete_set_windows ORDER BY market DESC LIMIT 192')]
        self.store.set('complete_set_observer',{'spec':SPEC,'asset':self.store.asset,'updated_at':now,'mode':'OBSERVATION_ONLY','current':row,'recent_windows':recent,'window_limit':192,'limitations':['Polling is not synchronized exchange execution.','Repeated samples are not independent opportunities.','Both available is not atomic execution or realised profit.','Assumed 0.02 USD reserve; actual merge costs and collateral route unverified.','10 USD total budget is measurement size, not approved live risk.','Pending probes are discarded on restart; no historical backfill.']})
