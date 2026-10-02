"""Frozen PAPER hypothesis, not Mitch's proprietary model or calibrated probability."""
import json
from decimal import Decimal, ROUND_FLOOR, ROUND_CEILING
from .core import number, units

SPEC = {'id':'mid-window-v1','entry_elapsed_seconds':[180,420],
        'ask_range':[.50,.60], 'last_sale_elapsed_exclusive':600,
        'deadline_exit_from':590, 'momentum_seconds':30,
        'minimum_normalized_distance':1.0, 'max_spread':.03,
        'take_profit_net_fraction':.10,'stop_loss_net_fraction':.20,
        'notional_usd':5,'status':'UNVALIDATED_PAPER_HYPOTHESIS'}

def entry(m, reference, history, now):
    elapsed=now-m['start']
    if not 180 <= elapsed <= 420: return None,'OUTSIDE_ENTRY_WINDOW'
    if not all(-.25<=now-b['source_ts']<=3 for b in m['books'].values()):return None,'BOOK_STALE'
    if not m.get('features'): return None,'FEATURES_MISSING'
    z=m['features'][1]
    if abs(z)<1: return None,'NORMALIZED_DISTANCE_SMALL'
    # Side = book favorite (lower ask), same as v2
    up_book = m['books'].get('Up', {})
    down_book = m['books'].get('Down', {})
    if not up_book.get('asks') or not down_book.get('asks'):
        return None, 'BOOK_STALE'
    up_ask = min(float(x[0]) for x in up_book['asks'])
    down_ask = min(float(x[0]) for x in down_book['asks'])
    side = 'Up' if up_ask <= down_ask else 'Down'
    b=m['books'][side]
    if not b.get('bids'): return None,'BOOK_STALE'
    ask=min(float(x[0]) for x in b['asks']);bid=max(float(x[0]) for x in b['bids'])
    if not .50<=ask<=.60: return None,'PRICE_OUTSIDE_RANGE'
    if not 0<=ask-bid<=.030000001: return None,'SPREAD_TOO_WIDE'
    return {'side':side,'limit':min(.60,ask+.01),'probability':None,
            'decision_at':now,'strategy':'mid-window-v1','market':m['slug'],
            'config_version':'mid-window-v1','feature_schema':m.get('feature_schema'),
            'hypothesis':SPEC},'SIGNAL'

def simulate_sale(book, shares_micro, fee_rate, floor=None):
    """Full-quantity FOK approximation: fresh arrival bids, 50% depth, both fees."""
    shares=Decimal(shares_micro)/1_000_000
    tick=number(book['tick']);minimum=number(book['min_shares']);rate=number(fee_rate)
    if shares<=0 or tick<=0 or minimum<=0 or not 0<=rate<=1: raise ValueError('sale parameters')
    if shares<minimum:return None
    floor=number(floor) if floor is not None else tick
    remaining=shares;gross=Decimal(0);fee=0;fills=[]
    levels=sorted(((number(p),number(q)) for p,q in book['bids']),reverse=True)
    if any(not (0<p<1 and q>=0 and p%tick==0) for p,q in levels):raise ValueError('sale book')
    for p,q in levels:
        if p<floor:break
        take=min(remaining,q/2).quantize(Decimal('.000001'),rounding=ROUND_FLOOR)
        if take<=0:continue
        gross+=p*take;f=units(take*rate*p*(1-p),ROUND_CEILING);fee+=f
        fills.append({'price':str(p),'shares':str(take),'fee_micro':f});remaining-=take
        if remaining==0:break
    if remaining>0:return None
    return {'shares':shares_micro,'proceeds':units(gross),'fee':fee,'fills':fills,'floor':str(floor)}

def exit_intent(position, market, now):
    """v1 mid-window / eth: hold to official resolution.
    early-v1 retains the original stop-loss / deadline exit."""
    strategy = position.get('strategy', 'mid-window-v1')
    if strategy in ('mid-window-v1', 'eth-mid-window-v1'):
        return None, 'HOLD_TO_OFFICIAL_RESOLUTION'
    # early-v1: preserve original exit logic
    elapsed = now - market['start']
    protected = json.loads(position.get('evidence', '{}')).get('risk_policy') in ('btc-stop10-v1', 'eth-stop10-v1')
    if elapsed >= 900 or (elapsed >= 600 and not protected):
        return None, 'HOLD_TO_OFFICIAL_RESOLUTION'
    book = market['books'][position['side']]
    if not -.25 <= now - book['source_ts'] <= 3:
        return None, 'EXIT_BOOK_STALE'
    fill = simulate_sale(book, position['shares'], market['fee_rate'])
    if not fill:
        return None, 'EXIT_NO_FULL_FILL'
    basis = position['cost'] + position['fee']
    net = fill['proceeds'] - fill['fee'] - basis
    stop = .10 if protected else .20
    why = 'EXIT_STOP' if net <= -stop * basis else 'EXIT_DEADLINE' if elapsed >= 590 else 'EXIT_PROFIT' if net >= .10 * basis else None
    if not why:
        return None, 'EXIT_HOLD'
    return {'reason': why, 'floor': fill['fills'][-1]['price'], 'decision_at': now}, why

