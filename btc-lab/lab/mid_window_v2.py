"""mid-window-v2 — frozen forward PAPER hypothesis, 2026-09-30.

Tighter parameters based on independent audit of v1 results (44 trades).
Key changes from v1:
  - Entry window narrowed: [180, 300] (3–5 min, matching Mitch's stated range)
  - Ask range tightened: [0.50, 0.70] (better EV at lower prices)
  - Z-score threshold raised: 1.5 (stronger filter, fewer but higher-quality entries)
  - Take profit raised: 15% (breakeven WR ≈ 40% vs 67% in v1)
  - Stop loss: 10% (unchanged from v1 protected)
  - Max spread tightened: 2.5 cents

NOT a reproduction of Mitch's undisclosed algorithm. This is a preregistered
research variant with frozen parameters. Do not optimize on forward data.
"""
import json
from decimal import Decimal, ROUND_FLOOR, ROUND_CEILING
from .core import number, units

SPEC_V2 = {
    'id': 'mid-window-v2',
    'entry_elapsed_seconds': [180, 300],       # 3–5 minutes (was 3–7)
    'ask_range': [0.50, 0.70],                 # tighter upper bound (was 0.80)
    'last_sale_elapsed_exclusive': 600,         # unchanged
    'deadline_exit_from': 590,                  # unchanged
    'momentum_seconds': 30,                     # unchanged
    'minimum_normalized_distance': 1.5,         # raised from 1.0
    'max_spread': 0.025,                        # tighter (was 0.03)
    'take_profit_net_fraction': 0.15,           # raised from 0.10
    'stop_loss_net_fraction': 0.10,             # unchanged from v1-protected
    'notional_usd': 5,                          # unchanged
    'status': 'FROZEN_PAPER_HYPOTHESIS',
}


def entry(m, reference, history, now):
    """Entry signal for mid-window-v2. Returns (intent, reason) tuple."""
    elapsed = now - m['start']
    if not 180 <= elapsed <= 300:
        return None, 'OUTSIDE_ENTRY_WINDOW'
    if not all(-0.25 <= now - b['source_ts'] <= 3 for b in m['books'].values()):
        return None, 'BOOK_STALE'
    if not m.get('features'):
        return None, 'FEATURES_MISSING'
    # z scales distance by trailing volatility and remaining time. Not a probability.
    z = m['features'][1]
    if abs(z) < 1.5:
        return None, 'NORMALIZED_DISTANCE_SMALL'
    side = 'Up' if reference['price'] >= m['opening'] else 'Down'
    # Momentum confirmation: 30 seconds of consistent directional movement.
    past = [(t, p) for t, p in history if now - 35 <= t <= now]
    if len(past) < 20 or now - past[0][0] < 30 or any(b[0] - a[0] > 5 for a, b in zip(past, past[1:])):
        return None, 'MOMENTUM_HISTORY_MISSING'
    direction = 1 if side == 'Up' else -1
    if any(direction * (p - m['opening']) <= 0 for _, p in past) or direction * (past[-1][1] - past[0][1]) <= 0:
        return None, 'MOMENTUM_UNCONFIRMED'
    b = m['books'][side]
    if not b.get('bids'):
        return None, 'BOOK_STALE'
    ask = min(float(x[0]) for x in b['asks'])
    bid = max(float(x[0]) for x in b['bids'])
    if not 0.50 <= ask <= 0.70:
        return None, 'PRICE_OUTSIDE_RANGE'
    spread = ask - bid
    if not 0 <= spread <= 0.025 + 1e-9:
        return None, 'SPREAD_TOO_WIDE'
    return {
        'side': side,
        'limit': min(0.70, ask + 0.01),
        'probability': None,
        'decision_at': now,
        'strategy': 'mid-window-v2',
        'market': m['slug'],
        'config_version': 'mid-window-v2',
        'feature_schema': m.get('feature_schema'),
        'hypothesis': SPEC_V2,
    }, 'SIGNAL'


def exit_intent_v2(position, market, now):
    """Exit signal for mid-window-v2. Same structure as v1 exit_intent, different thresholds."""
    from .mid_window import simulate_sale
    elapsed = now - market['start']
    protected = json.loads(position.get('evidence', '{}')).get('risk_policy') in (
        'btc-stop10-v1', 'eth-stop10-v1', 'btc-mid-v2-stop10', 'eth-mid-v2-stop10')
    if elapsed >= 900 or (elapsed >= 600 and not protected):
        return None, 'HOLD_TO_OFFICIAL_RESOLUTION'
    book = market['books'][position['side']]
    if not -0.25 <= now - book['source_ts'] <= 3:
        return None, 'EXIT_BOOK_STALE'
    fill = simulate_sale(book, position['shares'], market['fee_rate'])
    if not fill:
        return None, 'EXIT_NO_FULL_FILL'
    basis = position['cost'] + position['fee']
    net = fill['proceeds'] - fill['fee'] - basis
    # v2: TP 15%, SL 10% — breakeven WR ≈ 40%
    stop = 0.10 if protected else 0.10  # both paths use 10% in v2
    tp = 0.15
    mid = position.get('strategy', '') in ('mid-window-v2', 'eth-mid-window-v2')
    why = ('EXIT_STOP' if net <= -stop * basis
           else 'EXIT_DEADLINE' if mid and elapsed >= 590
           else 'EXIT_PROFIT' if mid and net >= tp * basis
           else None)
    if not why:
        return None, 'EXIT_HOLD'
    return {'reason': why, 'floor': fill['fills'][-1]['price'], 'decision_at': now}, why
