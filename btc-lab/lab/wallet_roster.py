"""Versioned PAPER roster. History is never rewritten. Not live money.

paper-roster-v3 states:
  observed    — watched, no new copy buys
  paper_test  — isolated PAPER copy, low confidence if under 30 days
  paper_active— isolated PAPER copy after a longer paper_test
  paused      — no new buys; open tickets still settle; losses stay

The current copying period is the closed PAPER copies opened since this
wallet entered its current paper_test or paper_active stint. A known
negative net in that period pauses new buys. A missing close result is
not zero and does not pause. Open positions are not part of that net.
Return uses only observations opened after the pause. A positive net
after costs is enough. Fewer than 10 such closes is an uncertain sample:
the wallet can return, and the old losses stay in the book.
There is no calendar wait on observation, activation, or return.
A day that holds more than 70% of the gains is recorded as uncertainty.
It does not block entry or promotion.
paper-roster-v1 and paper-roster-v2 are kept below. Their results are not rewritten.
This is a PAPER experiment. It does not prove an edge and it does not raise risk limits.
"""
import json
import time
from .wallet_observer import SEED_WALLETS, PAPER_EXTRA
from .strategy_control import set_paused

SPEC = 'paper-roster-v3'
PREVIOUS_SPEC = 'paper-roster-v1'
SPEC_V2 = 'paper-roster-v2'
ACCEPTED_SPECS = (SPEC, SPEC_V2, PREVIOUS_SPEC)
KEY = 'wallet_roster'
AUDIT_KEY = 'wallet_selection_audit'
AUDIT_TABLE = 'wallet_selection_audit'
AUDIT_MIGRATED = 'wallet_selection_audit_migrated'
# The state blob is only what the dashboard shows. The table keeps every row.
AUDIT_DISPLAY_LIMIT = 200
STATES = ('observed', 'paper_test', 'paper_active', 'paused')
# How many isolated PAPER tests run at once. Not fit to a PnL curve.
PAPER_TEST_SLOTS = 3

# Frozen previous definition. Do not use these numbers for new decisions.
RULES_V1 = {
    'spec': PREVIOUS_SPEC,
    'observed_to_paper_test': {
        'min_our_trades': 20,
        'min_windows': 5,
        'min_days': 7,
        'min_copy_sim_net_usd': 0.01,
        'max_best_day_share': 0.70,
    },
    'paper_test_to_paper_active': {
        'min_copy_trades': 30,
        'min_days': 0,
        'min_net_usd': 0.01,
        'max_best_day_share': 0.70,
    },
    'paper_active_to_paused': {
        'rolling_7d_net_usd': -15.0,
        'loss_streak': 8,
    },
    'paused_to_paper_test': {
        'min_pause_days': 0,
        'hyp_7d_net_usd': 8.0,
        'min_hyp_trades': 10,
    },
}

RULES_V2 = {
    'spec': SPEC_V2,
    'observed_to_paper_test': {
        'min_our_trades': 20,
        'min_windows': 5,
        'min_days': 0,
        'min_copy_sim_net_usd': 0.01,
        'max_best_day_share': 0.70,
    },
    'paper_test_to_paper_active': {
        'min_copy_trades': 30,
        'min_days': 0,
        'min_net_usd': 0.01,
        'max_best_day_share': 0.70,
    },
    'paper_active_to_paused': {
        'period_net_negative_blocks_buys': True,
    },
    'paused_to_paper_test': {
        'min_pause_days': 0,
        'uncertain_below_trades': 10,
    },
}
# 0.70 remains a concentration note. It is not an entry or promotion gate.
RULES = {
    'spec': SPEC,
    'observed_to_paper_test': {
        'min_our_trades': 20,
        'min_windows': 5,
        'min_days': 0,
        'min_copy_sim_net_usd': 0.01,
    },
    'paper_test_to_paper_active': {
        'min_copy_trades': 30,
        'min_days': 0,
        'min_net_usd': 0.01,
    },
    'paper_active_to_paused': {
        'period_net_negative_blocks_buys': True,
    },
    'paused_to_paper_test': {
        'min_pause_days': 0,
        'uncertain_below_trades': 10,
    },
    'concentration_uncertain_above': 0.70,
}
_RULES_FOR = {PREVIOUS_SPEC: RULES_V1, SPEC_V2: RULES_V2}
PAUSE_REASON = 'paper-roster-v3 pause: current period closed net is negative'
RETEST_REASON = 'paper-roster-v3 retest'
PROMOTE_REASON = 'paper-roster-v3 paper_test'

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


def _audit_row(ts, wallet, action, reason, evidence):
    return {'ts': ts, 'wallet': wallet, 'action': action, 'reason': reason, 'evidence': evidence or {}}


def audit(store, now, wallet, action, reason, evidence=None):
    """Append-only reason for discover, reject, promote, pause, restore, replace.

    Every row stays in wallet_selection_audit. The state key keeps the latest
    200 for display and is not the archive.
    """
    evidence = evidence or {}
    body = json.dumps(evidence, allow_nan=False)
    with store.connect() as db:
        db.execute(
            f'''CREATE TABLE IF NOT EXISTS {AUDIT_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                wallet TEXT NOT NULL,
                action TEXT NOT NULL,
                reason TEXT NOT NULL,
                evidence TEXT NOT NULL
            )'''
        )
        migrated = db.execute('SELECT body FROM state WHERE key=?', (AUDIT_MIGRATED,)).fetchone()
        if not migrated:
            raw = db.execute('SELECT body FROM state WHERE key=?', (AUDIT_KEY,)).fetchone()
            existing = json.loads(raw[0]) if raw else []
            if isinstance(existing, list):
                for row in existing:
                    if not isinstance(row, dict):
                        continue
                    db.execute(
                        f'INSERT INTO {AUDIT_TABLE} (ts, wallet, action, reason, evidence) VALUES (?,?,?,?,?)',
                        (
                            row.get('ts') or 0,
                            row.get('wallet') or '',
                            row.get('action') or '',
                            row.get('reason') or '',
                            json.dumps(row.get('evidence') or {}, allow_nan=False),
                        ),
                    )
            db.execute(
                'INSERT OR REPLACE INTO state VALUES (?,?)',
                (AUDIT_MIGRATED, json.dumps(True)),
            )
        db.execute(
            f'INSERT INTO {AUDIT_TABLE} (ts, wallet, action, reason, evidence) VALUES (?,?,?,?,?)',
            (now, wallet, action, reason, body),
        )
        stored = db.execute(
            f'SELECT ts, wallet, action, reason, evidence FROM {AUDIT_TABLE} ORDER BY id DESC LIMIT ?',
            (AUDIT_DISPLAY_LIMIT,),
        ).fetchall()
    display = [
        _audit_row(row['ts'], row['wallet'], row['action'], row['reason'], json.loads(row['evidence']))
        for row in reversed(stored)
    ]
    store.set(AUDIT_KEY, display)
    return display


def bootstrap(store, now=None):
    now = now if now is not None else time.time()
    current = store.get(KEY, {})
    if current.get('wallets') and current.get('spec') in ACCEPTED_SPECS:
        if current.get('spec') != SPEC:
            current = dict(current)
            history = list(current.get('rule_history') or [])
            if current.get('previous_spec'):
                history.append({
                    'spec': current.get('previous_spec'),
                    'rules': current.get('previous_rules') or _RULES_FOR.get(current.get('previous_spec')),
                })
            old_spec = current.get('spec')
            history.append({'spec': old_spec, 'rules': current.get('rules') or _RULES_FOR.get(old_spec)})
            current['rule_history'] = history
            current['previous_spec'] = old_spec
            current['previous_rules'] = current.get('rules') or _RULES_FOR.get(old_spec)
            current['spec'] = SPEC
            current['rules'] = RULES
            current['updated_at'] = now
            store.set(KEY, current)
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


def _known_net(settled):
    """Sum of known close results. A missing pnl is not zero."""
    if any(t.get('pnl_micro') is None for t in settled):
        return None
    return sum(t.get('pnl_micro') for t in settled) / 1e6


def evaluate_copy_book(closed, now, first_open, opened_after=None):
    """Decide from OUR copy book, not the source wallet's public month.

    first_open is only the age of the book. It does not drop rows.
    opened_after drops every row that was not opened strictly later.
    The return path passes the pause timestamp there.
    """
    rules = RULES
    settled = [t for t in closed if t.get('status') in ('CLOSED', 'SETTLED')]
    if opened_after is not None:
        settled = [
            t for t in settled
            if t.get('opened') is not None and t.get('opened') > opened_after
        ]
    net = _known_net(settled)
    windows = len({t.get('market') for t in settled})
    age_days = (now - first_open) / 86400 if first_open else 0
    share = concentration(settled) if net is not None else None
    small = rules['paused_to_paper_test']['uncertain_below_trades']
    note = rules['concentration_uncertain_above']
    concentrated = share is not None and share > note
    return {
        'net_usd': net,
        'trades': len(settled),
        'windows': windows,
        'age_days': age_days,
        'best_day_share': share,
        'loss_streak': loss_streak(settled),
        'net_7d': rolling_net(settled, now, 7) if net is not None else None,
        'uncertain': len(settled) < small,
        'concentration_uncertain': concentrated,
        'can_activate': (
            net is not None
            and len(settled) >= rules['paper_test_to_paper_active']['min_copy_trades']
            and age_days >= rules['paper_test_to_paper_active']['min_days']
            and net >= rules['paper_test_to_paper_active']['min_net_usd']
        ),
        'should_pause': net is not None and net < 0,
        'can_retest': net is not None and net > 0,
    }


def period_closes(closed, since):
    """Closed copies opened in the current stint. Open rows stay out."""
    return [
        t for t in closed
        if t.get('status') in ('CLOSED', 'SETTLED')
        and t.get('opened') is not None
        and t.get('opened') >= since
    ]


def can_observe_to_test(stats):
    r = RULES['observed_to_paper_test']
    return (
        (stats.get('our_trades') or 0) >= r['min_our_trades']
        and (stats.get('windows') or 0) >= r['min_windows']
        and (stats.get('age_days') or 0) >= r['min_days']
        and (stats.get('copy_sim_net_usd') or 0) >= r['min_copy_sim_net_usd']
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
            item = {
                'status': 'CLOSED',
                'closed_at': review.get('official_seen_at') or review.get('decision_at') or 0,
                'pnl_micro': shadow['pnl_micro'],
                'market': event.get('slug') or event.get('conditionId') or wallet,
                'hypothetical': True,
            }
            fee = (shadow.get('fill') or {}).get('fee')
            if isinstance(fee, (int, float)) and fee == fee:
                item['fee_micro'] = fee
            found.setdefault(wallet, []).append(item)
    return found


def observation_settled(store):
    """Closed rows from the versioned observation book. Not the independent tickets."""
    found = {}
    meta = store.get('wallet_observation_meta') or {}
    started = meta.get('started_at')
    version = meta.get('version')
    if not version or started is None:
        return found
    with store.connect() as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='wallet_observation_positions'").fetchone():
            return found
        for wallet, body in db.execute('SELECT wallet, body FROM wallet_observation_positions'):
            trade = json.loads(body)
            # Only the current observation rules qualify. An older book stays
            # in the table and still settles, but it is not evidence for this version.
            if trade.get('policy') != version or (trade.get('opened') or 0) < started:
                continue
            if trade.get('status') not in ('CLOSED', 'SETTLED') or trade.get('pnl_micro') is None:
                continue
            trade['fee_micro'] = trade.get('fee')
            found.setdefault(wallet, []).append(trade)
    return found


def copy_evidence(store, wallet, now):
    """Versioned observation only. Independent tickets are not promotion evidence."""
    rows = observation_settled(store).get(wallet, [])
    empty = {
        'our_trades': 0,
        'windows': 0,
        'age_days': 0,
        'copy_sim_net_usd': None,
        'best_day_share': None,
        'win_rate': None,
        'max_drawdown_usd': None,
        'net_7d': None,
        'fees_usd': None,
        'fee_known': False,
    }
    if not rows:
        return empty
    first = min(t.get('closed_at') or 0 for t in rows)
    book = evaluate_copy_book(rows, now, first)
    wins = sum(1 for t in rows if (t.get('pnl_micro') or 0) > 0)
    total = peak = drawdown = 0
    for t in sorted(rows, key=lambda item: item.get('closed_at') or 0):
        total += t.get('pnl_micro') or 0
        peak = max(peak, total)
        drawdown = max(drawdown, peak - total)
    fees = [t['fee_micro'] for t in rows if t.get('fee_micro') is not None]
    fee_known = len(fees) == len(rows)
    return {
        'our_trades': book['trades'],
        'windows': book['windows'],
        'age_days': book['age_days'],
        'copy_sim_net_usd': book['net_usd'],
        'best_day_share': book['best_day_share'],
        'win_rate': (wins / book['trades']) if book['trades'] else None,
        'max_drawdown_usd': drawdown / 1e6,
        'net_7d': book['net_7d'],
        'fees_usd': (sum(fees) / 1e6) if fee_known else None,
        'fee_known': fee_known,
    }


def _book_net(closed):
    return sum(
        (t.get('pnl_micro') or 0) / 1e6
        for t in closed
        if t.get('status') in ('CLOSED', 'SETTLED')
    )


def admit_observed(store, wallet, now, evidence, reason):
    """Start watching. Does not open a PAPER test."""
    state = bootstrap(store, now)
    if wallet in state['wallets']:
        return state, False
    state['wallets'][wallet] = _row(
        wallet, 'observed', now, confidence='low', source='discovery', reason=reason, stats=evidence,
    )
    state['updated_at'] = now
    store.set(KEY, state)
    _apply_pauses(store, state)
    audit(store, now, wallet, 'discovered', reason, evidence)
    return state, True


def _promote_paper_test(store, state, wallet, stats, now, closed_by):
    """Move observed → paper_test. A full slate drops the weakest test, not its history."""
    tests = [w for w, row in state['wallets'].items() if row['state'] == 'paper_test']
    if len(tests) >= PAPER_TEST_SLOTS:
        weakest = min(tests, key=lambda w: (_book_net(closed_by.get(w, [])), w))
        weak_net = _book_net(closed_by.get(weakest, []))
        if (stats.get('copy_sim_net_usd') or 0) <= weak_net:
            audit(store, now, wallet, 'rejected', 'weaker_than_current_paper_test', {
                'copy_sim_net_usd': stats.get('copy_sim_net_usd'),
                'weakest': weakest,
                'weakest_net_usd': weak_net,
            })
            return False
        state['wallets'][weakest]['state'] = 'observed'
        state['wallets'][weakest]['since'] = now
        state['wallets'][weakest]['reason'] = 'discovery-v1 replaced by stronger paper candidate'
        state['wallets'][weakest]['replaced_by'] = wallet
        audit(store, now, weakest, 'replaced', state['wallets'][weakest]['reason'], {
            'replaced_by': wallet,
            'net_usd': weak_net,
        })
    row = state['wallets'][wallet]
    row['state'] = 'paper_test'
    row['since'] = now
    row['confidence'] = 'low' if (stats.get('age_days') or 0) < 30 else 'medium'
    row['reason'] = PROMOTE_REASON
    share = stats.get('best_day_share')
    if share is not None and share > RULES['concentration_uncertain_above']:
        row['confidence'] = 'low'
        row['concentration'] = 'uncertain'
    row['stats'] = stats
    audit(store, now, wallet, 'promoted', row['reason'], stats)
    return True


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
    observed_book = observation_settled(store)
    changed = []
    already = set(state['wallets'])
    for w, row in list(state['wallets'].items()):
        closed = closed_by.get(w, [])
        first = first_by.get(w) or row.get('since')
        since = row.get('since') or first
        book = evaluate_copy_book(period_closes(closed, since), now, since) if row['state'] in ('paper_test', 'paper_active', 'paused') else None
        if row['state'] in ('paper_active', 'paper_test') and book and book['should_pause']:
            row['state'] = 'paused'
            row['since'] = now
            row['reason'] = PAUSE_REASON
            changed.append(w)
            audit(store, now, w, 'paused', row['reason'], {
                'net_usd': book['net_usd'], 'trades': book['trades'],
            })
        elif row['state'] == 'paper_test' and book and book['can_activate']:
            row['state'] = 'paper_active'
            row['since'] = now
            row['reason'] = 'paper-roster-v3 activate'
            if book.get('concentration_uncertain'):
                row['confidence'] = 'low'
                row['concentration'] = 'uncertain'
            changed.append(w)
            audit(store, now, w, 'promoted', row['reason'], {
                'net_usd': book['net_usd'], 'trades': book['trades'], 'best_day_share': book['best_day_share'],
            })
        elif row['state'] == 'paused':
            # opened_after cuts observations from before this pause.
            # first_open alone does not. Independent tickets are not in this book.
            pause_since = row.get('since') or now
            hyp_book = evaluate_copy_book(
                observed_book.get(w, []), now, pause_since, opened_after=pause_since,
            )
            if hyp_book['can_retest'] and now - pause_since >= RULES['paused_to_paper_test']['min_pause_days'] * 86400:
                row['state'] = 'paper_test'
                row['since'] = now
                row['confidence'] = 'low' if hyp_book['uncertain'] else 'medium'
                row['sample'] = 'uncertain' if hyp_book['uncertain'] else 'enough'
                row['reason'] = RETEST_REASON
                changed.append(w)
                audit(store, now, w, 'restored', row['reason'], {
                    'net_usd': hyp_book['net_usd'], 'trades': hyp_book['trades'],
                    'sample': row['sample'],
                })
        elif row['state'] == 'observed':
            stats = (candidate_stats or {}).get(w)
            if stats and can_observe_to_test(stats) and _promote_paper_test(store, state, w, stats, now, closed_by):
                changed.append(w)
    for w, stats in (candidate_stats or {}).items():
        if w in already:
            continue
        # A first sighting is only watched. PAPER_TEST waits for a later tick.
        if can_observe_to_test(stats):
            state['wallets'][w] = _row(
                w, 'observed', now, confidence='low', source='roster',
                reason='copy evidence recorded; paper test waits for the next pass', stats=stats,
            )
            changed.append(w)
            audit(store, now, w, 'discovered', state['wallets'][w]['reason'], stats)
    state['updated_at'] = now
    store.set(KEY, state)
    _apply_pauses(store, state)
    return state, changed
