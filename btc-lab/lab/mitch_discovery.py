"""Find wallets the way Mitch does: 90 days of history, then a copy replay.

Damian, 10 Oct 2026: the Mitch strategy is done exactly like Mitch. He looks
for wallets with 90 days of history and large profits, and judges a wallet
by replaying our copy of it at 2 cents over his price (his mihaXd 5m replay:
"don't copy him on 5m, at any size"). This module does that per wallet and
per market (BTC/ETH x 5m/15m). It never trades and never adds a wallet to
the Mitch book: the five wallets Mitch sent stay a fixed list; candidates
are shown for Damian or Mitch to decide.

Damian's own wallets (the qualifier) keep their 30-day discovery. This is
the Mitch track only.

Runs as its own process (com.btc-lab.mitch-discovery), writes
data/mitch_discovery.json, which the dashboard and Telegram read.
"""
import json
import logging
import re
import sys
import time
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

LOG = logging.getLogger('btc-lab.mitch-discovery')
STOCKHOLM = ZoneInfo('Europe/Stockholm')
SLUG = re.compile(r'^(btc|eth)-updown-(5m|15m)-(\d+)$')
SLIP = Decimal('0.02')          # Mitch: "at 2c over his price"
FEE_RATE = Decimal('0.07')      # crypto taker fee: rate * p * (1 - p) per share
DAYS = 90
MAX_PAGES = 200                 # 100k rows; a wallet over that is marked incomplete
LANES = {
    # Mitch's current 15m sizing: min(D, 15) + 5% above 15, window cap 20 USD.
    'mitch15': {'cap': Decimal('20'), 'formula': True},
    # "Our old 5 dollar lane rules": one ticket up to 5 USD, window cap 5 USD.
    'lane5': {'cap': Decimal('5'), 'formula': False},
}
# A verdict needs enough windows, a positive copy over 90 and over the last
# 30 days, and a positive copy without its single best window (Mitch: one
# lucky +1,494 window must not carry the day).
MIN_WINDOWS = 100


def fee(price, shares):
    return FEE_RATE * price * (1 - price) * shares


def notional(dollars, lane):
    if not LANES[lane]['formula']:
        return min(dollars, Decimal('5'))
    return min(dollars, Decimal('15')) + Decimal('0.05') * max(dollars - Decimal('15'), Decimal(0))


def market_of(slug):
    m = SLUG.match(str(slug or ''))
    if not m:
        return None
    return {'asset': m.group(1), 'interval': m.group(2), 'start': int(m.group(3)),
            'length': 300 if m.group(2) == '5m' else 900}


def fetch_activity(fetch, wallet, days=DAYS, now=None, max_pages=MAX_PAGES):
    from .data_api import fetch_rows
    now = int(now or time.time())
    rows, cursor, pages = [], None, 0
    while pages < max_pages:
        batch, cursor = fetch_rows(fetch, 'activity', user=wallet, start=now - days * 86400, end=now,
                                   limit=500, sortBy='TIMESTAMP', sortDirection='DESC', cursor=cursor)
        rows.extend(batch)
        pages += 1
        if not cursor:
            return rows, True
    return rows, False


def winners_from_redeems(rows):
    """conditionId -> winning outcomeIndex, from redeems that paid out."""
    out = {}
    for r in rows:
        if r.get('type') == 'REDEEM' and float(r.get('usdcSize') or 0) > 0 and r.get('conditionId') is not None:
            try:
                out[str(r['conditionId'])] = int(r.get('outcomeIndex'))
            except (TypeError, ValueError):
                continue
    return out


def resolve_slug(fetch, slug, cache):
    """Winning outcome index of a closed window from Gamma, cached."""
    if slug in cache:
        return cache[slug]
    try:
        market = fetch('https://gamma-api.polymarket.com/markets/slug/' + slug)
    except Exception:
        return None
    prices = market.get('outcomePrices') if isinstance(market, dict) else None
    if isinstance(prices, str):
        try:
            prices = json.loads(prices)
        except ValueError:
            prices = None
    winner = None
    if market and market.get('closed') and prices:
        values = [float(p) for p in prices]
        if max(values) >= 0.99:
            winner = values.index(max(values))
    if winner is not None:
        cache[slug] = winner
    return winner


def trades_by_window(rows):
    """Our-market trades grouped by window, oldest first."""
    windows = defaultdict(list)
    for r in rows:
        if r.get('type') != 'TRADE' or r.get('side') not in ('BUY', 'SELL'):
            continue
        meta = market_of(r.get('slug'))
        if not meta:
            continue
        try:
            item = {
                'ts': float(r['timestamp']), 'side': r['side'],
                'outcome': int(r.get('outcomeIndex')),
                'price': Decimal(str(r.get('price'))), 'size': Decimal(str(r.get('size'))),
                'usdc': Decimal(str(r.get('usdcSize') or 0)),
                'condition': str(r.get('conditionId') or ''),
            }
        except Exception:
            continue
        if item['price'] <= 0 or item['size'] <= 0:
            continue
        windows[r['slug']].append(item)
    for items in windows.values():
        items.sort(key=lambda x: x['ts'])
    return windows


def source_window(items, winner):
    """The source's own result in a window, held to settlement."""
    cash = Decimal(0)
    shares = defaultdict(Decimal)
    for t in items:
        if t['side'] == 'BUY':
            cash -= t['usdc'] or t['price'] * t['size']
            shares[t['outcome']] += t['size']
        else:
            cash += t['usdc'] or t['price'] * t['size']
            shares[t['outcome']] -= t['size']
    return cash + max(shares[winner], Decimal(0))


def replay_window(items, winner, lane):
    """Our copy of one window under Mitch's rules. Returns (pnl, spent)."""
    cap = LANES[lane]['cap']
    spent = Decimal(0)
    cash = Decimal(0)
    ours = defaultdict(Decimal)
    theirs = defaultdict(Decimal)
    for t in items:
        o = t['outcome']
        if t['side'] == 'BUY':
            theirs[o] += t['size']
            price = min(t['price'] + SLIP, Decimal('0.99'))
            want = notional(t['usdc'] or t['price'] * t['size'], lane)
            room = cap - spent
            if room <= Decimal('0.5'):
                continue
            dollars = min(want, room)
            shares = dollars / (price * (1 + FEE_RATE * (1 - price)))
            cost = price * shares + fee(price, shares)
            spent += cost
            cash -= cost
            ours[o] += shares
        else:
            before = theirs[o]
            theirs[o] -= t['size']
            if before <= 0 or ours[o] <= 0:
                continue
            fraction = min(t['size'] / before, Decimal(1))
            sold = ours[o] * fraction
            price = max(t['price'] - SLIP, Decimal('0.01'))
            cash += price * sold - fee(price, sold)
            ours[o] -= sold
    return cash + max(ours[winner], Decimal(0)), spent


def day_of(start):
    return datetime.fromtimestamp(start, STOCKHOLM).date().isoformat()


def summarize(per_window, now, days):
    """per_window: list of (start, pnl). Totals, days up/down, worst day, without best window."""
    cutoff = now - days * 86400
    rows = [(s, p) for s, p in per_window if s >= cutoff]
    by_day = defaultdict(Decimal)
    for s, p in rows:
        by_day[day_of(s)] += p
    total = sum((p for _, p in rows), Decimal(0))
    best = max((p for _, p in rows), default=Decimal(0))
    return {
        'windows': len(rows),
        'pnl': float(round(total, 2)),
        'pnl_without_best_window': float(round(total - max(best, Decimal(0)), 2)),
        'days_up': sum(1 for v in by_day.values() if v > 0),
        'days_down': sum(1 for v in by_day.values() if v < 0),
        'worst_day': float(round(min(by_day.values(), default=Decimal(0)), 2)),
        'best_window': float(round(best, 2)),
    }


def score_wallet(fetch, wallet, cache, now=None, days=DAYS, rows=None):
    now = now or time.time()
    complete = True
    if rows is None:
        rows, complete = fetch_activity(fetch, wallet, days, now)
    winners = winners_from_redeems(rows)
    windows = trades_by_window(rows)
    markets = defaultdict(lambda: {'source': [], 'mitch15': [], 'lane5': []})
    unresolved = 0
    for slug, items in windows.items():
        meta = market_of(slug)
        if meta['start'] + meta['length'] > now - 120:
            continue
        winner = winners.get(items[0]['condition'])
        if winner is None:
            winner = resolve_slug(fetch, slug, cache)
        if winner is None:
            unresolved += 1
            continue
        key = '%s %s' % (meta['asset'].upper(), meta['interval'])
        markets[key]['source'].append((meta['start'], source_window(items, winner)))
        for lane in LANES:
            markets[key][lane].append((meta['start'], replay_window(items, winner, lane)[0]))
    result = {'wallet': wallet, 'complete': complete, 'unresolved_windows': unresolved,
              'rows': len(rows), 'markets': {}}
    for key, series in markets.items():
        entry = {'source_90d': summarize(series['source'], now, days),
                 'source_30d': summarize(series['source'], now, 30)}
        for lane in LANES:
            entry['%s_90d' % lane] = summarize(series[lane], now, days)
            entry['%s_30d' % lane] = summarize(series[lane], now, 30)
            entry['%s_7d' % lane] = summarize(series[lane], now, 7)
        c90, c30 = entry['mitch15_90d'], entry['mitch15_30d']
        entry['verdict'] = bool(
            c90['windows'] >= MIN_WINDOWS and c90['pnl'] > 0 and c30['pnl'] > 0
            and c90['pnl_without_best_window'] > 0 and complete
        )
        entry['why'] = verdict_text(entry, complete)
        result['markets'][key] = entry
    return result


def verdict_text(entry, complete):
    c90, c30 = entry['mitch15_90d'], entry['mitch15_30d']
    if not complete:
        return 'historia niepełna (ponad %d stron)' % MAX_PAGES
    if c90['windows'] < MIN_WINDOWS:
        return 'za mało okien (%d < %d)' % (c90['windows'], MIN_WINDOWS)
    if c90['pnl'] <= 0:
        return 'kopia na minusie przez 90 dni (%+.0f USD)' % c90['pnl']
    if c30['pnl'] <= 0:
        return 'kopia na minusie w ostatnich 30 dniach (%+.0f USD)' % c30['pnl']
    if c90['pnl_without_best_window'] <= 0:
        return 'zysk z jednego szczęśliwego okna (bez niego %+.0f USD)' % c90['pnl_without_best_window']
    return 'kopia na plusie 90 i 30 dni, także bez najlepszego okna'


def candidate_wallets(fetch, limit=60):
    """Leads: the CRYPTO leaderboard (all time and month) and wallets on our markets now."""
    from .data_api import fetch_rows
    seen = {}
    for period in ('ALL', 'MONTH'):
        try:
            rows, _ = fetch_rows(fetch, 'leaderboard', category='CRYPTO', timePeriod=period, orderBy='PNL', limit=50)
        except Exception:
            rows = []
        for r in rows:
            w = str(r.get('proxyWallet') or '').lower()
            if re.fullmatch(r'0x[0-9a-f]{40}', w):
                seen.setdefault(w, {'source': 'leaderboard ' + period, 'pnl': r.get('pnl')})
    cursor = None
    for _ in range(4):
        try:
            rows, cursor = fetch_rows(fetch, 'trades', limit=500, cursor=cursor)
        except Exception:
            break
        for r in rows:
            if market_of(r.get('slug')):
                w = str(r.get('proxyWallet') or '').lower()
                if re.fullmatch(r'0x[0-9a-f]{40}', w):
                    seen.setdefault(w, {'source': 'tape'})
        if not cursor:
            break
    return dict(list(seen.items())[:limit])


def run(root, fetch=None, wallets=None, limit=40):
    from .worker import get_json
    from .mitch_copy import WALLETS as MITCH
    fetch = fetch or get_json
    base = Path(root)
    out_path = base / 'data' / 'mitch_discovery.json'
    cache_path = base / 'data' / 'mitch_discovery_resolutions.json'
    try:
        cache = json.loads(cache_path.read_text())
    except (OSError, ValueError):
        cache = {}
    started = time.time()
    leads = {w: {'source': 'Mitch (lista)', 'label': MITCH[w]['label']} for w in MITCH}
    if wallets is None:
        for w, meta in candidate_wallets(fetch, limit).items():
            leads.setdefault(w, meta)
    else:
        for w in wallets:
            leads.setdefault(w, {'source': 'ręcznie'})
    results = []
    for i, (wallet, meta) in enumerate(leads.items()):
        try:
            scored = score_wallet(fetch, wallet, cache, now=started)
        except Exception as error:
            LOG.warning('score %s: %s', wallet[-8:], str(error)[:160])
            continue
        scored.update(meta)
        scored['in_mitch_book'] = wallet in MITCH
        results.append(scored)
        LOG.info('%d/%d %s %s', i + 1, len(leads), wallet[-8:],
                 {k: v['why'] for k, v in scored['markets'].items()})
        cache_path.write_text(json.dumps(cache))
    passed = [{'wallet': r['wallet'], 'label': r.get('label'), 'market': k,
               'copy_90d': v['mitch15_90d']['pnl'], 'copy_30d': v['mitch15_30d']['pnl'],
               'windows': v['mitch15_90d']['windows'], 'in_mitch_book': r['in_mitch_book']}
              for r in results for k, v in r['markets'].items() if v['verdict']]
    passed.sort(key=lambda x: -x['copy_90d'])
    body = {'spec': 'mitch-discovery-v1', 'started_at': started, 'finished_at': time.time(),
            'days': DAYS, 'slip_usd': float(SLIP), 'min_windows': MIN_WINDOWS,
            'note': 'Kopia o 2 centy gorzej od jego ceny, z opłatami, rozmiar i limit jak u Mitcha. '
                    'Nowe portfele nie trafiają same do księgi Mitcha.',
            'passed': passed, 'wallets': results}
    tmp = out_path.with_suffix('.tmp')
    tmp.write_text(json.dumps(body))
    tmp.replace(out_path)
    return body


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s:%(name)s:%(message)s')
    run(sys.argv[1] if len(sys.argv) > 1 else str(Path.home() / 'Library/Application Support/BTC Lab'))
