"""Small chronological logistic challenger; paper-only, no automatic live promotion."""
import json
import math
import time
from .strategy import sigmoid

def fit(rows):
    weights=[0.,0.,1.,0.]  # initialise at book-implied log odds
    for _ in range(600):
        grad=[0.]*4
        for x,y,_ in rows:
            error=sigmoid(sum(a*b for a,b in zip(weights,x)))-y
            for j in range(4): grad[j] += error*x[j]
        for j in range(4): weights[j] -= .015*(grad[j]/len(rows)+(.02*weights[j] if j else 0))
    return weights

def train(store):
    schema=store.get('market',{}).get('feature_schema') or 'spot-v1'
    with store.connect() as db:
        rows=db.execute("SELECT e.body,l.winner FROM examples e JOIN labels l ON e.market=l.market ORDER BY e.ts").fetchall()
    examples=[]
    for r in rows:
        e=json.loads(r['body'])
        if e.get('features') and e.get('feature_schema','spot-v1')==schema:
            examples.append((e['features'],int(r['winner']=='Up'),e['book_probability']))
    n=len(examples)
    result={"status":"COLLECTING","samples":n,"required":200,"trained_at":time.time(),
            "feature_schema":schema,
            "notice":"Experimental paper challenger; no live promotion. Forward results are the evaluation."}
    if n >= 200:
        # Freeze the first 200-window model. Additional data is untouched forward evidence.
        split=140
        weights=fit(examples[:split])
        validation=examples[split:200]
        brier=sum((sigmoid(sum(a*b for a,b in zip(weights,x)))-y)**2 for x,y,_ in validation)/len(validation)
        baseline=sum((p-y)**2 for _,y,p in validation)/len(validation)
        result.update(status="PAPER_CANDIDATE" if brier<baseline else "VALIDATION_FAILED",weights=weights,
                      validation_brier=brier,book_brier=baseline,training_samples=140,validation_samples=60,
                      model_id="logistic-first200-"+schema,horizon_seconds=[115,125])
    store.set('model',result)
    return result

def report(store, monthly_cost_eur=15):
    s=store.snapshot()
    return {"generated_at":time.time(),"mode":"PAPER","monthly_infrastructure_allowance_eur":monthly_cost_eur,
            "observations":s['observations'],"official_labels":s['labels'],"model":s['model'],
            "accounts":s['accounts'],"promotion":"DISABLED",
            "limitations":["REST depth snapshots, not a full exchange replay","No Nautilus parity gate completed",
                "Daily profits are not established","Cash release is a five-minute paper assumption",
                "Research books use $500; $100 live feasibility must be evaluated independently"]}
