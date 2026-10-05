"""Versioned PAPER roster. History is never rewritten. Not live money.

paper-roster-v1 states:
  observed    — watched, no new copy buys
  paper_test  — isolated PAPER copy, low confidence if under 30 days
  paper_active— isolated PAPER copy after a longer paper_test
  paused      — no new buys; open tickets still settle; losses stay

Rules were fixed before this morning's book and are not refit to it.
Pause at -15 USD / 7 days is several min-lot losses, not one unlucky ticket.
Return needs +8 USD, 10 hypothetical trades and 14 days, so one green day cannot flip the wallet.
This is a PAPER experiment. It does not prove an edge and it does not raise risk limits.
"""
import json
import time
from .wallet_observer import SEED_WALLETS, PAPER_EXTRA
from .strategy_control import set_paused

SPEC = 'paper-roster-v1'
KEY = 'wallet_roster'
STATES = ('observed', 'paper_test', 'paper_active', 'paused')

RULES = {
    'spec': SPEC,
    'observed_to_paper_test': {
        'min_our_trades': 20,
        'min_windows': 5,
        'min_days': 7,
        'min_copy_sim_net_usd': 0.01,
        'max_best_day_share': 0.70,
    },
    'paper_test_to_paper_active': {
        'min_copy_trades': 30,
        'min_days': 14,
        'min_net_usd': 0.01,
        'max_best_day_share': 0.70,
    },
    'paper_active_to_paused': {
        'rolling_7d_net_usd': -15.0,
        'loss_streak': 8,
    },
    'paused_to_paper_test': {
        'min_pause_days': 14,
        'hyp_7d_net_usd': 8.0,
        'min_hyp_trades': 10,
    },
}

SEED_STATE = {
    '0x16217458b59b3458149918058754cd234096b159': 'paper_active',
    '0xeda9247a2b3c99a9e0bf46cdac6e1974365cf589': 'paused',
    '0x943cea746e701823b6902a6f4eaeed58207e77c2': 'paused',
    '0xeebde7a0e019a63e6b476eb425505b7b3e6eba30': 'paused',
    '0x84389cfc4a652ea14d8d8be969769b1f69de3680': 'paper_test',
    '0xce50c96b976203b53342a0a801067d2cdcfcf46e': 'paper_test',
}


def _row(wallet, state, now, **extra):
    return {'wallet': wallet, 'state': state, 'since': now, 'confidence': extra.pop('confidence', 'unknown'), **extra}


def bootstrap(store, now=None):
    now = now if now is not None else time.time()
    current = store.get(KEY, {})
    if current.get('spec') == SPEC and current.get('wallets'):
        return current
    wallets = {}
    for w, state in SEED_STATE.items():
        wallets[w] = _row(w, state, now, confidence='manual_seed', source='seed' if w in SEED_WALLETS else 'paper_pick')
    state = {'spec': SPEC, 'rules': RULES, 'updated_at': now, 'wallets': wallets}
    store.set(KEY, state)
    _apply_pauses(store, state)
    return state


def _apply_pauses(store, roster):
    for w, row in roster.get('wallets', {}).items():
        paused = row['state'] in ('observed', 'paused')
        try:
            set_paused(store, 'copy-' + w, paused)
        except ValueError:
            pass


def roster_watch_wallets(store):
    """Seeds, extras, and roster names we still evaluate — including paused."""
    from .wallet_observer import get_active_wallets
    seen = list(get_active_wallets(store))
    for w, row in bootstrap(store).get('wallets', {}).items():
        if w not in seen:
            seen.append(w)
    return tuple(seen)


def concentration(closed):
    """Share of profit sitting in the single best calendar day. None if no gains."""
    days = {}
    for t in closed:
        day = int(t['closed_at'] // 86400)
        days[day] = days.get(day, 0) + (t.get('pnl_micro') or 0) / 1e6
    gains = {k: v for k, v in days.items() if v > 0}
    total = sum(gains.values())
    if total <= 0:
        return None
    return max(gains.values()) / total


def loss_streak(closed):
    streak = 0
    for t in sorted(closed, key=lambda x: x['closed_at'], reverse=True):
        if (t.get('pnl_micro') or 0) < 0:
            streak += 1
        else:
            break
    return streak


def rolling_net(closed, now, days):
    start = now - days * 86400
    return sum((t.get('pnl_micro') or 0) / 1e6 for t in closed if t.get('closed_at', 0) >= start)


def evaluate_copy_book(closed, now, first_open):
    """Decide from OUR copy book, not the source wallet's public month."""
    rules = RULES
    settled = [t for t in closed if t.get('status') in ('CLOSED', 'SETTLED')]
    net = sum((t.get('pnl_micro') or 0) / 1e6 for t in settled)
    windows = len({t.get('market') for t in settled})
    age_days = (now - first_open) / 86400 if first_open else 0
    share = concentration(settled)
    return {
        'net_usd': net,
        'trades': len(settled),
        'windows': windows,
        'age_days': age_days,
        'best_day_share': share,
        'loss_streak': loss_streak(settled),
        'net_7d': rolling_net(settled, now, 7),
        'can_activate': (
            len(settled) >= rules['paper_test_to_paper_active']['min_copy_trades']
            and age_days >= rules['paper_test_to_paper_active']['min_days']
            and net >= rules['paper_test_to_paper_active']['min_net_usd']
            and (share is None or share <= rules['paper_test_to_paper_active']['max_best_day_share'])
        ),
        'should_pause': (
            rolling_net(settled, now, 7) <= rules['paper_active_to_paused']['rolling_7d_net_usd']
            or loss_streak(settled) >= rules['paper_active_to_paused']['loss_streak']
        ),
        'can_retest': (
            rolling_net(settled, now, 7) >= rules['paused_to_paper_test']['hyp_7d_net_usd']
            and sum(1 for t in settled if t.get('closed_at', 0) >= now - 7 * 86400) >= rules['paused_to_paper_test']['min_hyp_trades']
        ),
    }


def can_observe_to_test(stats):
    r = RULES['observed_to_paper_test']
    share = stats.get('best_day_share')
    return (
        (stats.get('our_trades') or 0) >= r['min_our_trades']
        and (stats.get('windows') or 0) >= r['min_windows']
        and (stats.get('age_days') or 0) >= r['min_days']
        and (stats.get('copy_sim_net_usd') or 0) >= r['min_copy_sim_net_usd']
        and (share is None or share <= r['max_best_day_share'])
    )


def hypothetical_settled(store):
    """Settled shadow tickets for paused wallets. Real losses are not rewritten."""
    found = {}
    with store.connect() as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='wallet_copy_skip_reviews'").fetchone():
            return found
        for wallet, body in db.execute('SELECT wallet, body FROM wallet_copy_skip_reviews'):
            review = json.loads(body)
            if review.get('reason') not in ('COPY_PAUSED', 'PAUSED'):
                continue
            shadow = review.get('shadow') or {}
            if shadow.get('status') != 'SETTLED' or shadow.get('pnl_micro') is None:
                continue
            event = review.get('source_event') or {}
            found.setdefault(wallet, []).append({
                'status': 'CLOSED',
                'closed_at': review.get('official_seen_at') or review.get('decision_at') or 0,
                'pnl_micro': shadow['pnl_micro'],
                'market': event.get('slug') or event.get('conditionId') or wallet,
                'hypothetical': True,
            })
    return found


def tick(store, now=None, candidate_stats=None):
    """Apply hysteresis. candidate_stats maps wallet -> observe metrics."""
    now = now if now is not None else time.time()
    state = bootstrap(store, now)
    closed_by = {}
    first_by = {}
    with store.connect() as db:
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='wallet_copy_positions'").fetchone():
            for (body,) in db.execute('SELECT body FROM wallet_copy_positions'):
                t = json.loads(body)
                closed_by.setdefault(t['wallet'], []).append(t)
                opened = t.get('opened') or t.get('closed_at')
                if opened:
                    first_by[t['wallet']] = min(first_by.get(t['wallet'], opened), opened)
    hyp = hypothetical_settled(store)
    changed = []
    for w, row in list(state['wallets'].items()):
        closed = closed_by.get(w, [])
        first = first_by.get(w) or row.get('since')
        book = evaluate_copy_book(closed, now, first) if row['state'] in ('paper_test', 'paper_active', 'paused') else None
        if row['state'] in ('paper_active', 'paper_test') and book and book['should_pause']:
            row['state'] = 'paused'
            row['since'] = now
            row['reason'] = 'paper-roster-v1 pause'
            changed.append(w)
        elif row['state'] == 'paper_test' and book and book['can_activate']:
            row['state'] = 'paper_active'
            row['since'] = now
            row['reason'] = 'paper-roster-v1 activate'
            changed.append(w)
        elif row['state'] == 'paused':
            # Return looks at hypothetical copies after the pause, not the old losses.
            hyp_book = evaluate_copy_book(hyp.get(w, []), now, row.get('since') or now)
            if hyp_book['can_retest'] and now - row.get('since', now) >= RULES['paused_to_paper_test']['min_pause_days'] * 86400:
                row['state'] = 'paper_test'
                row['since'] = now
                row['reason'] = 'paper-roster-v1 retest'
                changed.append(w)
    for w, stats in (candidate_stats or {}).items():
        if w in state['wallets']:
            continue
        if can_observe_to_test(stats):
            conf = 'low' if (stats.get('age_days') or 0) < 30 else 'medium'
            state['wallets'][w] = _row(w, 'paper_test', now, confidence=conf, source='roster', stats=stats)
            changed.append(w)
    state['updated_at'] = now
    store.set(KEY, state)
    _apply_pauses(store, state)
    return state, changed
