"""Versioned full-window causal value research. Advisory only, no ledger writes.

One observation per market/minute. Probability uses only previously resolved
markets, separated by asset (database), elapsed minute and signed z bucket.
No importing the 120-second model into other horizons.
"""
import hashlib
import json
import math

SPEC='value-surface-v1'

def wilson(wins,n):
    if not n:return (0.,1.)
    z=1.96;p=wins/n;den=1+z*z/n
    center=(p+z*z/(2*n))/den
    radius=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return max(0.,center-radius),min(1.,center+radius)

def value_decision(p_low,p_high,ask,bid,fee_rate,minimum,capital=100.,risk_fraction=.01):
    vals=(p_low,p_high,ask,bid,fee_rate,minimum,capital,risk_fraction)
    if not all(math.isfinite(x) for x in vals) or not (0<=p_low<=p_high<=1 and 0<bid<=ask<1 and 0<=fee_rate<=1 and minimum>0 and capital>0 and 0<risk_fraction<=.01):
        raise ValueError('invalid value inputs')
    # Conservative ask cap and allowance per share; actual arrival fill required later.
    cap=min(.999,ask+.01)
    unit_cost=cap+fee_rate*cap*(1-cap)
    edge=p_low-unit_cost-.01
    budget=min(capital*risk_fraction,capital*max(0.,(p_low-unit_cost)/(1-unit_cost))*.25)
    shares=math.floor(budget/unit_cost*1e6)/1e6
    reason='RESEARCH_BUY_CANDIDATE' if edge>.02 and shares>=minimum else 'NO_NET_EDGE' if edge<=.02 else 'MINIMUM_EXCEEDS_BUDGET'
    return dict(reason=reason,probability_low=p_low,probability_high=p_high,
        max_price=cap,all_in_budget_usd=budget,shares=shares if reason=='RESEARCH_BUY_CANDIDATE' else 0,
        conservative_edge_per_share=edge,
        exit_assessment='SELL_VALUE_EXCEEDS_HOLD' if bid-fee_rate*bid*(1-bid)>p_high+.01 else 'NO_CONFIRMED_EXIT_EDGE',
        executable=False)

class OpportunityResearch:
    def __init__(self,store):
        self.store=store
        self.last_slot=None
        with store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS opportunity_samples (market TEXT, minute INTEGER, bucket INTEGER, ts REAL, body TEXT, PRIMARY KEY(market,minute))')
            db.execute('CREATE INDEX IF NOT EXISTS opportunity_cell ON opportunity_samples(minute,bucket,ts)')

    def step(self,m,reference,now):
        minute=int((now-m['start'])//60)
        if not 0<=minute<15:return
        slot=(m['slug'],minute)
        if slot==self.last_slot:return
        state=dict(spec=SPEC,updated_at=now,mode='RESEARCH_ONLY',market=m['slug'],minute=minute,executable=False)
        books=m.get('books',{})
        valid=(m.get('rule_supported') and m.get('fee_verified') and m.get('accepting') and m.get('features')
            and reference and 0<=now-reference['source_ts']<=5 and reference.get('topic')==m.get('reference_topic')
            and len(books)==2 and all(b.get('asks') and b.get('bids') and 0<=now-b['source_ts']<=3 and 0<=now-b['received_at']<=3 for b in books.values()))
        if not valid:
            self.store.set('opportunity_research',{**state,'status':'DATA_NOT_READY'})
            return
        z=float(m['features'][1]);bucket=max(-4,min(4,math.floor(z)))
        with self.store.connect() as db:
            # Each market contributes once to a cell. Labels must have been available
            # BEFORE the new market opens; no same-window or future settlement leakage.
            rows=db.execute('SELECT s.market,l.winner FROM opportunity_samples s JOIN labels l ON s.market=l.market WHERE s.minute=? AND s.bucket=? AND s.ts<? AND l.ts<? AND s.market<>? AND json_extract(s.body,"$.rule_hash")=? ORDER BY s.ts',
                (minute,bucket,m['start'],m['start'],m['slug'],m.get('rule_hash'))).fetchall()
            n=len(rows);wins=sum(r['winner']=='Up' for r in rows)
            lo,hi=wilson(wins,n)
            digest=hashlib.sha256(json.dumps([(r['market'],r['winner']) for r in rows]).encode()).hexdigest()[:16]
            candidates={}
            if n>=50:
                for side in ('Up','Down'):
                    b=books[side];ask=min(float(p) for p,q in b['asks']);bid=max(float(p) for p,q in b['bids'])
                    candidates[side]=value_decision(lo if side=='Up' else 1-hi,hi if side=='Up' else 1-lo,ask,bid,float(m['fee_rate']),float(b['min_shares']))
            body={**state,'status':'ESTIMATED_UNVALIDATED' if n>=50 else 'COLLECTING_BY_HORIZON',
                'training_windows':n,'training_cutoff':m['start'],'model_id':SPEC+'-'+digest,
                'bucket':bucket,'z':z,'candidates':candidates,'reference':reference,
                'books':books,'rule_hash':m.get('rule_hash'),'capital_scenario_usd':100,
                'required_windows_per_cell':50,'validation':'Forward validation required; Wilson interval is not a profitability guarantee.'}
            db.execute('INSERT OR IGNORE INTO opportunity_samples VALUES (?,?,?,?,?)',(m['slug'],minute,bucket,now,json.dumps(body,allow_nan=False)))
        self.last_slot=slot
        self.store.set('opportunity_research',body)
