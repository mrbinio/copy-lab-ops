"""Frozen PAPER hypothesis, not Mitch's proprietary model or calibrated probability."""
from decimal import Decimal, ROUND_FLOOR, ROUND_CEILING
from .core import number, units

SPEC = {'id':'mid-window-v1','entry_elapsed_seconds':[180,420],
        'ask_range':[.50,.80], 'last_sale_elapsed_exclusive':600,
        'deadline_exit_from':590, 'momentum_seconds':30,
        'minimum_normalized_distance':1.0, 'max_spread':.03,
        'take_profit_net_fraction':.10,'stop_loss_net_fraction':.20,
        'notional_usd':5,'status':'UNVALIDATED_PAPER_HYPOTHESIS'}

def entry(m, reference, history, now):
    elapsed=now-m['start']
    if not 180 <= elapsed <= 420: return None,'OUTSIDE_ENTRY_WINDOW'
    if not all(-.25<=now-b['source_ts']<=3 for b in m['books'].values()):return None,'BOOK_STALE'
    if not m.get('features'): return None,'FEATURES_MISSING'
    # z scales distance by trailing volatility and remaining time. Not a win probability.
    z=m['features'][1]
    if abs(z)<1: return None,'NORMALIZED_DISTANCE_SMALL'
    side='Up' if reference['price']>=m['opening'] else 'Down'
    past=[(t,p) for t,p in history if now-35<=t<=now]
    if len(past)<20 or now-past[0][0]<30 or any(b[0]-a[0]>5 for a,b in zip(past,past[1:])):
        return None,'MOMENTUM_HISTORY_MISSING'
    direction=1 if side=='Up' else -1
    if any(direction*(p-m['opening'])<=0 for _,p in past) or direction*(past[-1][1]-past[0][1])<=0:
        return None,'MOMENTUM_UNCONFIRMED'
    b=m['books'][side]
    if not b.get('bids'): return None,'BOOK_STALE'
    ask=min(float(x[0]) for x in b['asks']);bid=max(float(x[0]) for x in b['bids'])
    if not .50<=ask<=.80: return None,'PRICE_OUTSIDE_RANGE'
    if not 0<=ask-bid<=.030000001: return None,'SPREAD_TOO_WIDE'
    return {'side':side,'limit':min(.80,ask+.01),'probability':None,
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
    elapsed=now-market['start']
    if elapsed>=600:return None,'HOLD_TO_OFFICIAL_RESOLUTION'
    book=market['books'][position['side']]
    if not -.25<=now-book['source_ts']<=3:return None,'EXIT_BOOK_STALE'
    fill=simulate_sale(book,position['shares'],market['fee_rate'])
    if not fill:return None,'EXIT_NO_FULL_FILL'
    basis=position['cost']+position['fee']
    net=fill['proceeds']-fill['fee']-basis
    why='EXIT_DEADLINE' if elapsed>=590 else 'EXIT_STOP' if net<=-.20*basis else 'EXIT_PROFIT' if net>=.10*basis else None
    if not why:return None,'EXIT_HOLD'
    # Fixed floor from decision depth: no chasing a deteriorating arrival quote.
    return {'reason':why,'floor':fill['fills'][-1]['price'],'decision_at':now},why
