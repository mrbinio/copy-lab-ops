"""Separate copy results. Virtual $500 books are not one real wallet."""
from datetime import datetime
from statistics import median
from zoneinfo import ZoneInfo

SPEC = 'copy-totals-v1'
BOARD = 'paper-board-v1'
STOCKHOLM = ZoneInfo('Europe/Stockholm')


def _pnl(trade):
    if trade.get('pnl_micro') is not None:
        return trade['pnl_micro'] / 1e6
    return None


def _closed(trade):
    return trade.get('status') in ('CLOSED', 'SETTLED') and trade.get('closed_at')


def summarize(trades, pauses, now, observed=0, copy_wallets=None, roster=None):
    """Lifetime copy totals. Missing mark-to-market is None, not zero."""
    pauses = pauses or {}
    closed = [t for t in trades if _closed(t)]
    open_rows = [t for t in trades if t.get('status') in ('OPEN', 'RESOLVED')]
    by_wallet = {}
    for t in closed:
        by_wallet.setdefault(t['wallet'], []).append(t)

    def wallet_net(wallet):
        rows = by_wallet.get(wallet, [])
        return sum(_pnl(t) or 0 for t in rows)

    if copy_wallets is None:
        copy_wallets = []
        for t in trades:
            w = t.get('wallet')
            if w and w not in copy_wallets:
                copy_wallets.append(w)
    active_wallets = [w for w in copy_wallets if not pauses.get('copy-' + w)]
    paused_wallets = [w for w in copy_wallets if pauses.get('copy-' + w)]

    active_net = sum(wallet_net(w) for w in active_wallets) if active_wallets else 0.0
    all_net = sum(_pnl(t) or 0 for t in closed) if closed else 0.0
    known = set(copy_wallets)
    omitted = []
    for wallet, rows in by_wallet.items():
        if wallet in known:
            continue
        omitted.append({
            'wallet': wallet,
            'net_usd': round(wallet_net(wallet), 6),
            'trades': len(rows),
        })
    omitted.sort(key=lambda row: row['net_usd'])
    omitted_net = round(sum(row['net_usd'] for row in omitted), 6)
    open_cost = sum((t.get('cost') or 0) + (t.get('fee') or 0) for t in open_rows) / 1e6
    if open_rows:
        unrealized = None
        unrealized_reason = 'są pozycje OPEN albo RESOLVED, a księga nie ma osobnej wyceny rynkowej'
    else:
        unrealized = 0.0
        unrealized_reason = 'księga: zero pozycji OPEN i RESOLVED'
    counts = _roster_counts(roster, paused_wallets)
    return {
        'spec': SPEC,
        'generated_at': now,
        'source': 'wallet_copy_positions',
        'period': 'lifetime',
        'period_note': 'Od pierwszej kopii PAPER. Konta po 500 USD są osobne, nie jeden portfel.',
        'active_net_usd': round(active_net, 6),
        'all_copies_net_usd': round(all_net, 6),
        'historical_net_usd': round(all_net, 6),
        'omitted_net_usd': omitted_net,
        'omitted_wallets': omitted,
        'omitted_trades': sum(row['trades'] for row in omitted),
        'reconcile_note': 'all = włączone + wstrzymane z listy + portfele historyczne spoza listy. Te ostatnie zostają w księdze.',
        'open_count': len(open_rows),
        'open_cost_usd': round(open_cost, 6),
        'open_unrealized_usd': unrealized,
        'unrealized_reason': unrealized_reason,
        'wallets_active': len(active_wallets),
        'wallets_paused': counts['wallets_paused'],
        'wallets_observed': counts['wallets_observed_only'],
        'wallets_paper_active': counts['wallets_paper_active'],
        'wallets_paper_test': counts['wallets_paper_test'],
        'wallets_observed_only': counts['wallets_observed_only'],
        'counts_are_disjoint': counts['counts_are_disjoint'],
        'counts_note': counts['counts_note'],
        'active_wallets': active_wallets,
        'paused_wallets': paused_wallets,
        'separate_books': True,
    }


def _closed_row(trade):
    return trade.get('status') in ('CLOSED', 'SETTLED') and trade.get('closed_at')


def _copying_now(wallet, roster_wallets, pauses):
    state = (roster_wallets.get(wallet) or {}).get('state')
    if (pauses or {}).get('copy-' + wallet):
        return False
    return state in ('paper_active', 'paper_test')


def _pause_reason(wallet, roster_wallets, pauses):
    if _copying_now(wallet, roster_wallets, pauses):
        return None
    row = roster_wallets.get(wallet) or {}
    state = row.get('state')
    if state == 'paused':
        return row.get('reason') or 'wstrzymany'
    if state == 'observed':
        return 'obserwacja, bez nowych zakupów'
    if state in ('paper_active', 'paper_test'):
        return row.get('reason') or 'pauza kopii'
    return 'poza obecną listą'


def paper_board(trades, roster, pauses, now):
    """Closed PAPER copy book for today, 7 days and lifetime.

    Later-disabled wallets stay in the period that contains their closes.
    A missing pnl is missing, not zero. Open positions are not marked here:
    this book has no fresh sale quote.
    """
    roster_wallets = (roster or {}).get('wallets') or {}
    pauses = pauses or {}
    closed = [trade for trade in trades if _closed_row(trade)]
    open_rows = [trade for trade in trades if trade.get('status') in ('OPEN', 'RESOLVED')]
    today = datetime.fromtimestamp(now, STOCKHOLM).date().isoformat()
    week_start = now - 7 * 86400

    def included(trade, period):
        if period == 'all':
            return True
        if period == 'week':
            return trade['closed_at'] >= week_start
        return datetime.fromtimestamp(trade['closed_at'], STOCKHOLM).date().isoformat() == today

    periods = {}
    for period in ('today', 'week', 'all'):
        rows = [trade for trade in closed if included(trade, period)]
        missing = any(trade.get('pnl_micro') is None for trade in rows)
        by_wallet = {}
        for trade in rows:
            by_wallet.setdefault(trade['wallet'], []).append(trade)
        show = set(by_wallet)
        for wallet in roster_wallets:
            if _copying_now(wallet, roster_wallets, pauses):
                show.add(wallet)
        wallet_rows = []
        for wallet in show:
            items = by_wallet.get(wallet, [])
            known = all(item.get('pnl_micro') is not None for item in items)
            wallet_rows.append({
                'wallet': wallet,
                'copying': _copying_now(wallet, roster_wallets, pauses),
                'net_micro': None if not known else sum(item['pnl_micro'] for item in items),
                'closed': len(items),
                'pause_reason': _pause_reason(wallet, roster_wallets, pauses),
            })
        wallet_rows.sort(key=lambda row: (not row['copying'], row['net_micro'] is None, row['net_micro'] or 0, row['wallet']))
        net_micro = None if missing else sum(trade['pnl_micro'] for trade in rows)
        periods[period] = {
            'net_micro': net_micro,
            'closed': None if missing else len(rows),
            'wallets': wallet_rows,
        }
    journal = [{
        'wallet': trade.get('wallet'),
        'closed_at': trade.get('closed_at'),
        'opened': trade.get('opened'),
        'side': trade.get('side'),
        'market': trade.get('market'),
        'cost': trade.get('cost'),
        'fee': trade.get('fee'),
        'exit_fee': trade.get('exit_fee') or 0,
        'pnl_micro': trade.get('pnl_micro'),
        'status': trade.get('status'),
    } for trade in sorted(closed, key=lambda trade: trade.get('closed_at') or 0, reverse=True)]
    return {
        'spec': BOARD,
        'book': 'wallet_copy_positions',
        'generated_at': now,
        'timezone': 'Europe/Stockholm',
        'today': today,
        'week_start': week_start,
        'periods': periods,
        'journal': journal,
        'open': {
            'count': len(open_rows),
            'mark_micro': 0 if not open_rows else None,
            'mark_note': 'zero otwartych pozycji' if not open_rows else 'brak aktualnej wyceny',
        },
    }


def _roster_counts(roster, paused_wallets):
    wallets = (roster or {}).get('wallets') or {}
    if not wallets:
        return {
            'wallets_paper_active': None,
            'wallets_paper_test': None,
            'wallets_paused': len(paused_wallets),
            'wallets_observed_only': 0,
            'counts_are_disjoint': False,
            'counts_note': 'Brak listy paper-roster. Wstrzymane liczone z pauz, bez rozróżnienia paper_test.',
        }
    buckets = {'paper_active': 0, 'paper_test': 0, 'paused': 0, 'observed': 0}
    for row in wallets.values():
        state = row.get('state')
        if state in buckets:
            buckets[state] += 1
    return {
        'wallets_paper_active': buckets['paper_active'],
        'wallets_paper_test': buckets['paper_test'],
        'wallets_paused': buckets['paused'],
        'wallets_observed_only': buckets['observed'],
        'counts_are_disjoint': True,
        'counts_note': 'paper_active, paper_test, paused i observed są rozłączne. Jeden portfel jest w dokładnie jednym stanie.',
    }


def path_record(event, row, queued_at, book_started, book_done, decided_at):
    """Timing for one decision. Missing stages stay None. Never zero-fill them.

    data_api source_ts is the activity API timestamp, not a block time.
    chain_fast writes local detection into timestamp, so it is not time-from-trade.
    """
    source = event.get('_source') or 'data_api'
    trade_known = source != 'chain_fast'
    detect = None
    insert_lag = None
    if trade_known and row.get('source_ts') is not None and row.get('first_seen') is not None:
        detect = round((row['first_seen'] - row['source_ts']) * 1000, 1)
    elif row.get('source_ts') is not None and row.get('first_seen') is not None:
        insert_lag = round((row['first_seen'] - row['source_ts']) * 1000, 1)
    return {
        'source': source,
        'detect_from_trade_ms': detect,
        'local_insert_lag_ms': insert_lag,
        'queue_ms': round((queued_at - row['first_seen']) * 1000, 1) if row.get('first_seen') is not None else None,
        'book_ms': round((book_done - book_started) * 1000, 1) if book_started is not None and book_done is not None else None,
        'decision_ms': round((decided_at - book_done) * 1000, 1) if book_done is not None else None,
        'paper_ms': None,
        'total_from_ingest_ms': round((decided_at - row['first_seen']) * 1000, 1) if row.get('first_seen') is not None else None,
        'total_ms': round((decided_at - row['first_seen']) * 1000, 1) if row.get('first_seen') is not None else None,
        'clob_sign_ms': None,
        'clob_send_ms': None,
        'clob_confirm_ms': None,
        'clob': 'inactive_paper',
    }


def path_stats(samples):
    """Median and p95. A missing sample is None, not zero."""
    samples = list(samples or [])
    if not samples:
        return _empty_path('brak pomiarów')

    def pct(xs, p):
        i = min(len(xs) - 1, max(0, int(round((p / 100) * (len(xs) - 1)))))
        return xs[i]

    def pack(vals):
        ordered = sorted(vals)
        return {'n': len(ordered), 'median_ms': median(ordered), 'p95_ms': pct(ordered, 95)}

    stage_keys = (
        'detect_from_trade_ms', 'local_insert_lag_ms', 'queue_ms', 'book_ms',
        'decision_ms', 'paper_ms', 'total_from_ingest_ms',
    )
    stages = {}
    for key in stage_keys:
        vals = [s[key] for s in samples if s.get(key) is not None]
        if vals:
            stages[key] = pack(vals)
    # Old tickets stored detect_ms / total_ms without a source. Keep them apart.
    legacy = [s['total_ms'] for s in samples if not s.get('source') and s.get('total_ms') is not None]
    by_source = {}
    for sample in samples:
        source = sample.get('source')
        if not source:
            continue
        bucket = by_source.setdefault(source, [])
        if sample.get('total_from_ingest_ms') is not None:
            bucket.append(sample['total_from_ingest_ms'])
    by_source = {name: pack(vals) for name, vals in by_source.items() if vals}
    fresh = [s.get('total_from_ingest_ms') for s in samples if s.get('source') and s.get('total_from_ingest_ms') is not None]
    fresh = [v for v in fresh if v is not None]
    operational = ('queue_ms', 'book_ms', 'decision_ms', 'paper_ms', 'detect_from_trade_ms')
    slowest = max(
        ((key, stages[key]['median_ms']) for key in operational if key in stages),
        key=lambda item: item[1], default=(None, None),
    )
    if fresh:
        summary = pack(fresh)
        note = None
    elif legacy:
        summary = pack(legacy)
        note = 'tylko stare bilety bez źródła REST/chain_fast; to nie jest czas od transakcji'
    else:
        summary = {'n': 0, 'median_ms': None, 'p95_ms': None}
        note = 'brak pomiarów'
    return {
        'n': summary['n'],
        'median_ms': summary['median_ms'],
        'p95_ms': summary['p95_ms'],
        'slowest_stage': slowest[0],
        'stages': stages,
        'by_source': by_source,
        'legacy_n': len(legacy),
        'clob': 'inactive_paper',
        'note': note,
        'limitation': (
            'detect_from_trade_ms istnieje tylko dla data_api: first_seen minus timestamp API, nie czas bloku. '
            'chain_fast ma timestamp = lokalne wykrycie, więc czas od transakcji źródłowej jest nieznany. '
            'total_from_ingest_ms to decyzja PAPER od zapisu lokalnego. '
            'Podpis, wysłanie i potwierdzenie CLOB są nieaktywne.'
        ),
    }


def _empty_path(note):
    return {
        'n': 0, 'median_ms': None, 'p95_ms': None, 'slowest_stage': None,
        'stages': {}, 'by_source': {}, 'legacy_n': 0, 'clob': 'inactive_paper',
        'note': note,
        'limitation': 'brak próbek; zero nie zostało wpisane w miejsce braku pomiaru',
    }
