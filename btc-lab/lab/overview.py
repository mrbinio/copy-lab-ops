"""Numbers for the dashboard's first screen. PAPER only; it never trades.

Damian, 16 Oct 2026: "I want the dashboard to show the truth and be easy to
understand". Each number carries the date it is counted from. Days are
calendar days in Stockholm and a trade counts on the day it closed, the same
as the "Dzisiaj, zamknięte" cards.
"""
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo('Europe/Stockholm')
DAYS = 14
# 16 Oct 2026 08:10: Damian's wallets are copied on BTC 15m only (commit 7faafdf).
WALLETS_RULE_SINCE = datetime(2026, 10, 16, 8, 10, tzinfo=TZ).timestamp()
WALLETS_RULE = 'tylko BTC 15m, kopia w 1 s, pauza gdy portfel traci'


def _day(ts):
    return datetime.fromtimestamp(ts, TZ).date()


def _closed(rows):
    """(closed_at, pnl_micro) of every closed row with a known result."""
    out = []
    for body in rows:
        trade = json.loads(body)
        if trade.get('pnl_micro') is None or not trade.get('closed_at'):
            continue
        out.append((float(trade['closed_at']), int(trade['pnl_micro']), trade))
    return out


def series(closed, now, since=None):
    """Daily closed result for the last DAYS days, today, 7 days and since a date."""
    today = _day(now)
    first = today - timedelta(days=DAYS - 1)
    by_day = {first + timedelta(days=i): [0, 0, 0] for i in range(DAYS)}
    for at, pnl, _ in closed:
        d = _day(at)
        if d in by_day:
            row = by_day[d]
            row[0] += pnl
            row[1] += 1
            row[2] += pnl > 0
    days = [{'day': d.isoformat(), 'net_micro': v[0], 'closed': v[1], 'won': v[2]} for d, v in sorted(by_day.items())]
    week = days[-7:]
    out = {
        'days': days,
        'today_micro': days[-1]['net_micro'],
        'today_closed': days[-1]['closed'],
        'week_micro': sum(d['net_micro'] for d in week),
        'week_closed': sum(d['closed'] for d in week),
        'week_days_up': sum(d['net_micro'] > 0 for d in week),
        'week_days_down': sum(d['net_micro'] < 0 for d in week),
    }
    if since is not None:
        rows = [p for at, p, t in closed if float(t.get('opened') or at) >= since]
        out['since'] = since
        out['since_micro'] = sum(rows)
        out['since_closed'] = len(rows)
    return out


def readiness(root):
    try:
        audit = json.loads((Path(root) / 'logs' / 'daily-audit.json').read_text())
    except (OSError, ValueError):
        return {}
    problems = [c.get('detail') for c in audit.get('checks') or [] if c.get('status') == 'PROBLEM']
    return {'at': audit.get('at'), 'ok': audit.get('ok'), 'streak': audit.get('streak') or 0,
            'need': 3, 'problems': problems}


def build(store, root, now=None):
    now = now or time.time()
    out = {'at': now, 'tz': 'Europe/Stockholm', 'counted_by': 'dzień zamknięcia transakcji'}
    desk = store.get('mitch_desk') or {}
    with store.connect() as db:
        mitch = _closed(b for (b,) in db.execute('SELECT body FROM mitch_positions'))
        wallets = _closed(b for (b,) in db.execute('SELECT body FROM wallet_copy_positions'))
    out['mitch'] = series(mitch, now, desk.get('start_at'))
    out['mitch']['desk_start'] = desk.get('start_at')
    out['wallets'] = series(wallets, now, WALLETS_RULE_SINCE)
    out['wallets']['rule'] = WALLETS_RULE
    roster = ((store.get('wallet_roster') or {}).get('wallets') or {}).values()
    counts = {}
    for row in roster:
        state = (row or {}).get('state') or 'other'
        counts[state] = counts.get(state, 0) + 1
    out['wallets']['roster'] = counts
    out['readiness'] = readiness(root)
    return out
