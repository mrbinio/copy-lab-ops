"""Per-wallet observation summary for the dashboard.

Read-only. Called off the copier thread. It does not place buys, change
roster rules, or replay old signals. A missing measurement stays None so
the screen can say "brak danych" instead of a confirmed zero.
"""
import json

from .wallet_observer import get_active_wallets
from .wallet_roster import RULES, evaluate_copy_book

FEED_OK = ('POLL_OK', 'INCOMPLETE_PAGE_LIMIT', 'SCAN_OK')
FRESH_SOURCE_SECONDS = 120
# A check older than this is a dead poll, not "no trades".
FEED_STALE_SECONDS = 180


def _table(db, name):
    return db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()


def _feed(observer, now):
    if not observer or observer.get('checked_at') is None:
        return 'unknown'
    status = observer.get('status') or ''
    age = now - observer['checked_at']
    if status == 'ERROR' or age > FEED_STALE_SECONDS:
        return 'down'
    if status in FEED_OK:
        return 'ok'
    return 'unknown'


def _intake(feed, activity_count, last_source_at, last_reason, now):
    if feed == 'down':
        return 'feed_down'
    if feed != 'ok':
        return 'unknown'
    fresh = last_source_at is not None and 0 <= now - last_source_at <= FRESH_SOURCE_SECONDS
    if activity_count == 0:
        return 'no_source_trades'
    if not fresh:
        return 'no_fresh_source_trades'
    if last_reason is None:
        return 'unprocessed'
    return 'receiving'


def _policy_view(db, wallet, now, meta):
    """Versioned observation. Missing table stays unknown, not a zero profit."""
    meta = meta or {}
    empty = {
        'known': False, 'version': meta.get('version'), 'started_at': meta.get('started_at'),
        'open': None, 'settled': None, 'net': None, 'windows': None, 'evidence_days': None,
        'share': None, 'journal': [],
    }
    if not meta.get('version') or meta.get('started_at') is None or not _table(db, 'wallet_observation_positions'):
        return empty
    rows = []
    for (body,) in db.execute('SELECT body FROM wallet_observation_positions WHERE wallet=?', (wallet,)):
        trade = json.loads(body)
        accepted = {meta.get('version'), 'copy-observe-v1', 'copy-observe-v2'}
        if meta.get('previous_version'):
            accepted.add(meta.get('previous_version'))
        if trade.get('policy') not in accepted or (trade.get('opened') or 0) < meta['started_at']:
            continue
        rows.append(trade)
    open_n = sum(1 for trade in rows if trade.get('status') == 'OPEN')
    closed = [trade for trade in rows if trade.get('status') in ('CLOSED', 'SETTLED') and trade.get('pnl_micro') is not None]
    fees = [trade.get('fee') for trade in closed if isinstance(trade.get('fee'), (int, float))]
    net = None
    windows = evidence = share = None
    if closed and len(fees) == len(closed):
        book = evaluate_copy_book(
            [{**trade, 'fee_micro': trade.get('fee')} for trade in closed],
            now, min(trade.get('opened') or trade.get('closed_at') or now for trade in closed),
        )
        net = book['net_usd']
        windows = book['windows']
        evidence = book['age_days']
        share = book['best_day_share']
    elif not closed:
        windows = 0
    journal = [
        {
            'opened': trade.get('opened'),
            'closed_at': trade.get('closed_at'),
            'market': trade.get('market'),
            'side': trade.get('side') or '',
            'cost_micro': trade.get('cost'),
            'fee_micro': trade.get('fee'),
            'pnl_micro': trade.get('pnl_micro'),
            'policy': meta['version'],
        }
        for trade in sorted(closed, key=lambda item: item.get('closed_at') or 0, reverse=True)[:12]
    ]
    return {
        'known': True, 'version': meta['version'], 'started_at': meta['started_at'],
        'open': open_n, 'settled': len(closed), 'net': net, 'windows': windows,
        'evidence_days': evidence, 'share': share, 'journal': journal,
    }


def summarize_wallet(db, wallet, roster_row, observer, now, meta=None):
    """One wallet. Counts are None until the matching table was read."""
    roster_row = roster_row or {}
    shadow_known = False
    open_n = settled_n = other_n = None
    settled_rows = []
    if _table(db, 'wallet_copy_skip_reviews'):
        shadow_known = True
        counts = db.execute(
            """SELECT
                 SUM(json_extract(body,'$.shadow.status')='FILLED_PENDING_SETTLEMENT'
                     AND json_extract(body,'$.reason') IN ('COPY_PAUSED','PAUSED')),
                 SUM(json_extract(body,'$.shadow.status')='SETTLED'
                     AND json_extract(body,'$.reason') IN ('COPY_PAUSED','PAUSED')
                     AND json_extract(body,'$.shadow.pnl_micro') IS NOT NULL),
                 SUM(json_extract(body,'$.shadow.status')='SETTLED'
                     AND IFNULL(json_extract(body,'$.reason'),'') NOT IN ('COPY_PAUSED','PAUSED')
                     AND json_extract(body,'$.shadow.pnl_micro') IS NOT NULL)
               FROM wallet_copy_skip_reviews WHERE wallet=?""",
            (wallet,),
        ).fetchone()
        open_n = int(counts[0] or 0)
        settled_n = int(counts[1] or 0)
        other_n = int(counts[2] or 0)
        if settled_n:
            settled_rows = [
                {
                    'status': 'SETTLED',
                    'pnl_micro': row[0],
                    'fee_micro': row[1],
                    'closed_at': row[2] or 0,
                    'market': row[3] or wallet,
                    'cost_micro': row[4],
                    'side': row[5] or '',
                    'opened': row[6] or row[2] or 0,
                }
                for row in db.execute(
                    """SELECT json_extract(body,'$.shadow.pnl_micro'),
                              json_extract(body,'$.shadow.fill.fee'),
                              COALESCE(json_extract(body,'$.official_seen_at'),
                                       json_extract(body,'$.decision_at'), 0),
                              COALESCE(json_extract(body,'$.source_event.slug'),
                                       json_extract(body,'$.source_event.conditionId')),
                              json_extract(body,'$.shadow.fill.cost'),
                              json_extract(body,'$.source_event.side'),
                              COALESCE(json_extract(body,'$.source_event.timestamp'),
                                       json_extract(body,'$.decision_at'), 0)
                       FROM wallet_copy_skip_reviews
                       WHERE wallet=?
                         AND json_extract(body,'$.shadow.status')='SETTLED'
                         AND json_extract(body,'$.reason') IN ('COPY_PAUSED','PAUSED')
                         AND json_extract(body,'$.shadow.pnl_micro') IS NOT NULL""",
                    (wallet,),
                )
            ]
    activity_count = last_source_at = last_buy_at = None
    if _table(db, 'wallet_activity'):
        activity = db.execute(
            'SELECT COUNT(*), MAX(source_ts) FROM wallet_activity WHERE wallet=?',
            (wallet,),
        ).fetchone()
        activity_count = int(activity[0] or 0)
        last_source_at = activity[1]
        last_buy_at = db.execute(
            """SELECT MAX(source_ts) FROM wallet_activity
               WHERE wallet=? AND json_extract(body,'$.side')='BUY'""",
            (wallet,),
        ).fetchone()[0]
    last_reason = last_decision_at = None
    if _table(db, 'wallet_copy_events'):
        last = db.execute(
            'SELECT ts, reason FROM wallet_copy_events WHERE wallet=? ORDER BY ts DESC, rowid DESC LIMIT 1',
            (wallet,),
        ).fetchone()
        if last:
            last_decision_at, last_reason = last['ts'], last['reason']
    feed = _feed(observer, now)
    since = roster_row.get('since')
    observation_days = None if since is None else (now - since) / 86400
    need = RULES['observed_to_paper_test']
    evidence_days = net = share = None
    windows = 0 if shadow_known else None
    fees_known = False
    other_net = None
    if other_n:
        other_rows = [
            {'status': 'SETTLED', 'pnl_micro': row[0], 'fee_micro': row[1], 'closed_at': row[2] or 0, 'market': wallet}
            for row in db.execute(
                """SELECT json_extract(body,'$.shadow.pnl_micro'),
                          json_extract(body,'$.shadow.fill.fee'),
                          COALESCE(json_extract(body,'$.official_seen_at'), 0)
                   FROM wallet_copy_skip_reviews
                   WHERE wallet=?
                     AND json_extract(body,'$.shadow.status')='SETTLED'
                     AND IFNULL(json_extract(body,'$.reason'),'') NOT IN ('COPY_PAUSED','PAUSED')
                     AND json_extract(body,'$.shadow.pnl_micro') IS NOT NULL""",
                (wallet,),
            )
        ]
        other_fees = [row['fee_micro'] for row in other_rows if isinstance(row['fee_micro'], (int, float))]
        if other_rows and len(other_fees) == len(other_rows):
            other_net = sum(row['pnl_micro'] for row in other_rows) / 1e6
    if settled_rows:
        fees = [row['fee_micro'] for row in settled_rows if isinstance(row['fee_micro'], (int, float))]
        fees_known = len(fees) == len(settled_rows)
        book = evaluate_copy_book(settled_rows, now, min(row['closed_at'] for row in settled_rows))
        windows = book['windows']
        evidence_days = book['age_days']
        share = book['best_day_share']
        if fees_known:
            net = book['net_usd']
    policy = _policy_view(db, wallet, now, meta)
    journal = [
        {
            'opened': row['opened'],
            'closed_at': row['closed_at'],
            'market': row['market'],
            'side': row['side'],
            'cost_micro': row['cost_micro'] if isinstance(row['cost_micro'], (int, float)) else None,
            'fee_micro': row['fee_micro'] if isinstance(row['fee_micro'], (int, float)) else None,
            'pnl_micro': row['pnl_micro'],
        }
        for row in sorted(settled_rows, key=lambda item: item['closed_at'], reverse=True)[:12]
    ]
    progress = {
        'settled': policy['settled'],
        'need_settled': need['min_our_trades'],
        'windows': policy['windows'],
        'need_windows': need['min_windows'],
        'observation_days': observation_days,
        'evidence_days': policy['evidence_days'],
        'need_days': need['min_days'],
        'net_usd': policy['net'],
        'need_net_usd': need['min_copy_sim_net_usd'],
        'best_day_share': policy['share'],
        'max_best_day_share': need.get('concentration_uncertain_above', need.get('max_best_day_share')),
    }
    return {
        'wallet': wallet,
        'state': roster_row.get('state'),
        'feed': feed,
        'intake': _intake(feed, activity_count, last_source_at, last_reason, now),
        'observer_status': (observer or {}).get('status'),
        'observer_error': (observer or {}).get('error'),
        'history_page_capped': (observer or {}).get('status') == 'INCOMPLETE_PAGE_LIMIT',
        'checked_at': (observer or {}).get('checked_at'),
        'last_source_at': last_source_at,
        'last_buy_at': last_buy_at,
        'activity_count': activity_count,
        'last_reason': last_reason,
        'last_decision_at': last_decision_at,
        'shadow_known': shadow_known,
        'hypothetical_open': open_n,
        'hypothetical_settled': settled_n,
        'hypothetical_net_usd': net,
        'hypothetical_fees_known': fees_known if settled_n else False,
        'other_hypothetical_settled': other_n if shadow_known else None,
        'other_net_usd': other_net,
        'journal': journal,
        'policy_known': policy['known'],
        'policy_version': policy['version'],
        'policy_started_at': policy['started_at'],
        'policy_open': policy['open'],
        'policy_settled': policy['settled'],
        'policy_net_usd': policy['net'],
        'policy_journal': policy['journal'],
        'progress': progress,
    }


def build_watch(store, now):
    """One connection. Does not call store.get while that connection is open."""
    roster = (store.get('wallet_roster') or {}).get('wallets') or {}
    meta = store.get('wallet_observation_meta') or {}
    names = list(dict.fromkeys([*roster.keys(), *get_active_wallets(store)]))
    out = {}
    with store.connect() as db:
        observers = {}
        if names:
            keys = ['wallet_observer:' + wallet for wallet in names]
            marks = ','.join('?' * len(keys))
            for row in db.execute(f'SELECT key, body FROM state WHERE key IN ({marks})', keys):
                observers[row['key']] = json.loads(row['body'])
        for wallet in names:
            out[wallet] = summarize_wallet(
                db, wallet, roster.get(wallet), observers.get('wallet_observer:' + wallet), now, meta
            )
    return out
