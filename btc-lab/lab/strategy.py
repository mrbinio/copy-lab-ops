"""Causal research strategies. Legacy-inspired baselines are not exact replicas."""
import math
from decimal import Decimal

def sigmoid(x):
    return 1/(1+math.exp(-max(-30,min(30,x))))

def features(reference, opening, history, market_probability, seconds):
    # history is strictly past source-time data; never use future observations.
    changes = [math.log(b[1]/a[1])/math.sqrt(b[0]-a[0]) for a,b in zip(history,history[1:]) if 0 < b[0]-a[0] <= 10 and a[1]>0 and b[1]>0]
    if len(changes)<60 or not (reference>0 and opening>0 and 0<market_probability<1):
        return None
    sigma = max(1e-6,math.sqrt(sum(x*x for x in changes)/len(changes)))
    z = math.log(reference/opening)/(sigma*math.sqrt(max(1,seconds)))
    return [1.0,max(-8,min(8,z)),math.log(market_probability/(1-market_probability)),seconds/900]

def choose(strategy, market, reference, model, now):
    remaining = market['end']-now
    if not market.get('rule_supported'):
        return None,"RULE_UNVERIFIED"
    if not market.get('opening'):
        return None,"OPENING_REFERENCE_MISSING"
    if not reference or not (-.25 <= now-reference['source_ts'] <= 5):
        return None,"REFERENCE_STALE"
    if market.get('rule_kind')=='TWAP60' and reference.get('topic')!='crypto_prices_twap_sixty':
        return None,"REFERENCE_SOURCE_MISMATCH"
    if not market.get('accepting'):
        return None,"MARKET_CLOSED"
    if not market.get('fee_verified'):
        return None,"FEE_UNVERIFIED"
    current=Decimal(reference.get('price_decimal',str(reference['price'])))
    opening=Decimal(market.get('opening_decimal',str(market['opening'])))
    side = 'Up' if current>=opening else 'Down'
    book = market.get('books',{}).get(side,{})
    if not book.get('asks') or not (-.25 <= now-book['source_ts'] <= 3):
        return None,"BOOK_STALE"
    ask = min(float(x[0]) for x in book['asks'])
    if strategy == 'late-v1':
        if not 30 < remaining <= 300: return None,"OUTSIDE_ENTRY_WINDOW"
        if abs(current-opening) < 50: return None,"DISTANCE_TOO_SMALL"
        if not .8 <= ask <= .955: return None,"PRICE_OUTSIDE_RANGE"
        cap = min(.955,ask+.01)
        probability = None
    elif strategy == 'early-v1':
        if not 600 < remaining <= 780: return None,"OUTSIDE_ENTRY_WINDOW"
        if abs(current-opening) < 50: return None,"DISTANCE_TOO_SMALL"
        if not .6 <= ask <= .64: return None,"PRICE_OUTSIDE_RANGE"
        cap = min(.64,ask+.01)
        probability = None
    else:
        if not 115 <= remaining <= 125: return None,"OUTSIDE_MODEL_HORIZON"
        if model.get('status') != 'PAPER_CANDIDATE': return None,"MODEL_COLLECTING"
        if model.get('feature_schema','spot-v1')!=market.get('feature_schema','spot-v1'):
            return None,"MODEL_SCHEMA_MISMATCH"
        x = market.get('features')
        if not x: return None,"FEATURES_MISSING"
        up_p = sigmoid(sum(a*b for a,b in zip(model['weights'],x)))
        offers = []
        for candidate,p in [('Up',up_p),('Down',1-up_p)]:
            b = market.get('books',{}).get(candidate,{})
            if not b.get('asks') or not (-.25 <= now-b['source_ts'] <= 3): continue
            price = min(float(z[0]) for z in b['asks'])
            limit = min(.92,price+.01)
            # Conservative 3pp uncertainty margin, plus 2 cents net edge.
            if .80 <= price <= .92 and p-limit-market['fee_rate']*limit*(1-limit)-.03 >= .02:
                offers.append((p-limit,candidate,p,limit))
        if not offers: return None,"NO_NET_EDGE"
        _,side,probability,cap = max(offers)
    return {"side":side,"limit":cap,"probability":probability,"decision_at":now,
            "strategy":strategy,"market":market['slug'],"config_version":"v0.2.0","feature_schema":market.get('feature_schema','spot-v1')},"SIGNAL"
