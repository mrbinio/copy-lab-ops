"""Trial book for new wallets, the way Mitch starts them. PAPER only.

Damian, 11 Oct 2026. Mitch starts a new wallet at 5 a window and keeps it
after a good week. Here the best new BTC 15m wallets from the daily
discovery (passed the 90-day replay, not in his book) are copied live
from the fast lane into their own ledger, with no effect on his desk:

  - his buy must reach us inside one second of the match
  - the copy takes the asks up to 10 cents worse than his price
  - 5 USD a window per wallet, Mitch's sizing min(D,15)+5% above 15
  - taker fee 0.07 * p * (1-p) per share
  - held to the official result (his sells are not copied here)

Nothing here can place an order. Wallets join or leave only through
discovery; the result is a list for Damian, never an automatic promotion.
"""
import json
import logging
import threading
import time
from decimal import Decimal, ROUND_DOWN
from pathlib import Path

LOG = logging.getLogger('btc-lab.trials')
MAX_TRIALS = 5
WINDOW_CAP = Decimal('5')
PRICE_WORSE = Decimal('0.10')
MAX_AGE_S = 1.0
FEE_RATE = Decimal('0.07')
SETTLE_AFTER_S = 120
_LOCK = threading.Lock()
WALLETS = {}


def ensure(db):
    db.execute('''CREATE TABLE IF NOT EXISTS mitch_trial_positions (
        id TEXT PRIMARY KEY, wallet TEXT, market TEXT, body TEXT)''')


def pick(discovery, mitch_wallets, limit=MAX_TRIALS):
    """Best new BTC 15m wallets from discovery, by 90-day copy result."""
    rows = [p for p in (discovery.get('passed') or [])
            if p.get('market') == 'BTC 15m' and str(p.get('wallet')).lower() not in mitch_wallets]
    rows.sort(key=lambda p: -(p.get('copy_90d') or 0))
    return {str(p['wallet']).lower(): {'label': p.get('label') or str(p['wallet'])[-6:],
                                       'copy_90d': p.get('copy_90d'), 'copy_30d': p.get('copy_30d')}
            for p in rows[:limit]}


def refresh(root, mitch_wallets):
    try:
        discovery = json.loads((Path(root) / 'data' / 'mitch_discovery.json').read_text())
    except (OSError, ValueError):
        discovery = {}
    chosen = pick(discovery, {w.lower() for w in mitch_wallets})
    with _LOCK:
        WALLETS.clear()
        WALLETS.update(chosen)
    return chosen


def notional(source_usd):
    d = Decimal(str(source_usd))
    return min(d, Decimal('15')) + Decimal('0.05') * max(d - Decimal('15'), Decimal('0'))


def fill(asks, limit_price, budget):
    """Walk the asks up to limit_price; spend at most budget including the fee."""
    levels = sorted(((Decimal(str(a['price'])), Decimal(str(a['size']))) for a in asks or []),
                    key=lambda x: x[0])
    shares = cost = fee = Decimal(0)
    for price, size in levels:
        if price > limit_price or budget - cost - fee <= 0:
            break
        unit = price + FEE_RATE * price * (1 - price)
        take = min(size, ((budget - cost - fee) / unit).quantize(Decimal('0.01'), rounding=ROUND_DOWN))
        if take <= 0:
            break
        shares += take
        cost += take * price
        fee += take * FEE_RATE * price * (1 - price)
    if shares <= 0:
        return None
    return {'shares': shares, 'cost': cost, 'fee': fee, 'vwap': cost / shares}


def spent(db, wallet, market):
    total = Decimal(0)
    for (body,) in db.execute('SELECT body FROM mitch_trial_positions WHERE wallet=? AND market=?', (wallet, market)):
        trade = json.loads(body)
        total += Decimal(trade['cost']) + Decimal(trade['fee'])
    return total


def decide(store, fetch_book, wallet, row, arrived, now=None):
    """One fill of a trial wallet. Returns the reason; writes a position on a copy."""
    now = now or time.time()
    side = row.get('side')
    slug = str(row.get('slug') or '')
    if side != 'BUY' or not slug.startswith('btc-updown-15m-'):
        return 'NOT_A_BTC15_BUY'
    age = float(arrived) - float(row.get('timestamp') or 0)
    if age > MAX_AGE_S:
        return 'LATE'
    try:
        price = Decimal(str(row['price']))
        source_usd = Decimal(str(row.get('usdcSize') or 0))
    except Exception:
        return 'NO_PRICE'
    book = fetch_book(str(row.get('asset')))
    with store.connect() as db:
        ensure(db)
        room = WINDOW_CAP - spent(db, wallet, slug)
    budget = min(room, notional(source_usd))
    if budget <= Decimal('0.5'):
        return 'WINDOW_LIMIT'
    got = fill((book or {}).get('asks'), price + PRICE_WORSE, budget)
    if not got:
        return 'NO_LIQUIDITY'
    key = '%s:%s' % (row.get('transactionHash'), str(row.get('asset'))[-8:])
    trade = {'id': key, 'wallet': wallet, 'market': slug, 'token': str(row.get('asset')),
             'outcome': row.get('outcome'), 'source_price': str(price),
             'shares': str(got['shares']), 'cost': str(got['cost'].quantize(Decimal('0.000001'))),
             'fee': str(got['fee'].quantize(Decimal('0.000001'))), 'vwap': str(got['vwap'].quantize(Decimal('0.0001'))),
             'age_s': round(age, 3), 'opened': now, 'end': int(slug.rsplit('-', 1)[1]) + 900, 'status': 'OPEN'}
    with store.connect() as db:
        db.execute('INSERT OR IGNORE INTO mitch_trial_positions VALUES (?,?,?,?)',
                   (key, wallet, slug, json.dumps(trade)))
    return 'COPIED'


def settle(store, fetch, now=None):
    """Settle open trial positions on the official result. Returns how many closed."""
    now = now or time.time()
    with store.connect() as db:
        ensure(db)
        rows = [json.loads(b) for (b,) in db.execute('SELECT body FROM mitch_trial_positions')]
    due = [t for t in rows if t['status'] == 'OPEN' and now >= t['end'] + SETTLE_AFTER_S]
    winners = {}
    closed = 0
    for trade in due:
        market = trade['market']
        if market not in winners:
            try:
                raw = fetch('https://gamma-api.polymarket.com/markets/slug/' + market)
                tokens = json.loads(raw['clobTokenIds']) if isinstance(raw.get('clobTokenIds'), str) else raw.get('clobTokenIds')
                prices = json.loads(raw['outcomePrices']) if isinstance(raw.get('outcomePrices'), str) else raw.get('outcomePrices')
                won = [t for t, p in zip(tokens or [], prices or []) if str(p) in ('1', '1.0')]
                winners[market] = str(won[0]) if raw.get('closed') and len(won) == 1 else None
            except Exception:
                winners[market] = None
        winner = winners[market]
        if winner is None:
            continue
        payout = Decimal(trade['shares']) if winner == trade['token'] else Decimal(0)
        trade.update(status='SETTLED', payout=str(payout), closed_at=now,
                     pnl=str((payout - Decimal(trade['cost']) - Decimal(trade['fee'])).quantize(Decimal('0.000001'))))
        with store.connect() as db:
            db.execute('UPDATE mitch_trial_positions SET body=? WHERE id=?', (json.dumps(trade), trade['id']))
        closed += 1
    return closed


def summary(store, now=None):
    now = now or time.time()
    with store.connect() as db:
        ensure(db)
        rows = [json.loads(b) for (b,) in db.execute('SELECT body FROM mitch_trial_positions')]
    with _LOCK:
        current = dict(WALLETS)
    per = {}
    for t in rows:
        p = per.setdefault(t['wallet'], {'wallet': t['wallet'], 'copies': 0, 'settled': 0, 'won': 0,
                                         'pnl': 0.0, 'pnl_7d': 0.0, 'in_play': 0.0, 'windows': set()})
        p['copies'] += 1
        p['windows'].add(t['market'])
        if t['status'] == 'SETTLED':
            p['settled'] += 1
            p['pnl'] += float(t['pnl'])
            p['won'] += 1 if float(t['pnl']) > 0 else 0
            if now - float(t.get('closed_at') or 0) <= 7 * 86400:
                p['pnl_7d'] += float(t['pnl'])
        else:
            p['in_play'] += float(t['cost']) + float(t['fee'])
    out = []
    for wallet in set(per) | set(current):
        p = per.get(wallet) or {'wallet': wallet, 'copies': 0, 'settled': 0, 'won': 0, 'pnl': 0.0,
                                'pnl_7d': 0.0, 'in_play': 0.0, 'windows': set()}
        meta = current.get(wallet) or {}
        out.append(dict(p, windows=len(p['windows']), label=meta.get('label') or wallet[-6:],
                        active=wallet in current, copy_90d=meta.get('copy_90d'),
                        pnl=round(p['pnl'], 2), pnl_7d=round(p['pnl_7d'], 2), in_play=round(p['in_play'], 2)))
    out.sort(key=lambda x: (not x['active'], -x['pnl']))
    return {'at': now, 'rule': 'mitch-trial-5usd-v1', 'wallets': out,
            'note': 'Próba jak u Mitcha: 5 USD na okno, kopia w 1 s, do rozliczenia. Osobna księga PAPER, '
                    'bez wpływu na biurko Mitcha. Dodanie do Mitcha tylko decyzją Damiana.'}
