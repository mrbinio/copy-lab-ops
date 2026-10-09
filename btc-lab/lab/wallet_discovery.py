"""Find wallets from real BTC/ETH 5m/15m prints, then watch them in PAPER.

discovery-v1:
  The public CRYPTO month table is only a lead. It is not a score and it
  does not open a copy. The trades tape is the other lead: wallets that
  actually printed on our markets.

  A lead is admitted to `observed` only after the activity screen below.
  `paper_test` is a later roster step and uses our own hypothetical copies,
  not the source wallet's reported month. Live orders stay off.
"""
import asyncio
import json
import math
import re
import time
from collections import Counter
from decimal import Decimal
from urllib.parse import urlencode

from .wallet_copy import MAX_SOURCE_PRICE, MIN_SOURCE_PRICE
from .wallet_observer import SEED_WALLETS, ensure_active_wallets_table

SPEC = 'discovery-v1'
OUR_MARKETS = re.compile(r'^(btc|eth)-updown-(5m|15m)-')
WINDOW = re.compile(r'^(btc|eth)-updown-(5m|15m)-(\d+)$')
LOOKBACK = 30 * 86400
MIN_MONTH_VOLUME = 1000
# Leaderboard names still get a look, then the busiest tape wallets fill the rest.
LEADERBOARD_PROBES = 8
PROBE_CAP = 12
TAPE_PAGES = 3
MIN_OUR_TRADES = 10
MIN_OUR_SHARE = 0.25
MIN_HISTORY_SECONDS = 86400
ACTIVITY_PAGE_SIZE = 500
# data-api rejects offset 5500 with HTTP 400. A full last page is not the
# wallet's first trade, so the age behind that page is unknown.
ACTIVITY_OFFSET_CAP = 5000
# Same concentration cap the roster uses for one day of copy PnL.
MAX_ONE_TRADE_SHARE = 0.70
WALLET_RE = re.compile(r'0x[0-9a-f]{40}')


def our_slug(slug):
    return bool(OUR_MARKETS.match(str(slug or '')))


def window_end(slug):
    match = WINDOW.fullmatch(str(slug or ''))
    if not match:
        return None
    return int(match.group(3)) + (300 if match.group(2) == '5m' else 900)


def seen_while_market_open(item):
    """The market was still open when the trade happened and, if we know it, when we saw it.

    The copier's 90s limit is how old a signal may be at detection. It is not
    a requirement that 90s remain until the window ends. This function does
    not apply that limit.
    """
    end = window_end(item.get('slug'))
    ts = item.get('ts')
    if end is None or ts is None or ts >= end:
        return False
    detected = item.get('detected_at')
    if detected is None and item.get('detected_after') is not None:
        try:
            detected = ts + float(item['detected_after'])
        except (TypeError, ValueError):
            detected = None
    if detected is not None and not (ts <= detected < end):
        return False
    return True


def score_candidate(candidate):
    """Keep the old helper for tests that imported it; no longer used to promote."""
    month_pnl = candidate.get('month_reported_pnl') or candidate.get('week_reported_pnl') or 0
    month_vol = candidate.get('month_volume') or candidate.get('week_volume') or 1
    if month_vol <= 0:
        return 0.0
    return min(1.0, max(0, month_pnl / month_vol))


def promote(store, wallet, score=0.0):
    """No-op. A public-table score is not permission to copy."""
    return


def demote(store, wallet):
    """Remove a discovery wallet from active_wallets. Seed wallets cannot be demoted."""
    if wallet in SEED_WALLETS:
        return
    with store.connect() as db:
        db.execute("DELETE FROM active_wallets WHERE wallet=? AND source='discovery'",
                   (wallet,))


def prune_discovery_rows(store):
    """Drop leftover discovery rows. The roster, not this table, decides who is watched."""
    ensure_active_wallets_table(store)
    with store.connect() as db:
        db.execute("DELETE FROM active_wallets WHERE source='discovery'")


def market_stats(rows):
    trades = [r for r in rows if isinstance(r, dict) and str(r.get('type', '')).upper() == 'TRADE']
    ours = [r for r in trades if our_slug(r.get('slug'))]
    n = len(trades)
    return {
        'trades_30d': n,
        'our_trades_30d': len(ours),
        'our_share_30d': (len(ours) / n) if n else 0.0,
    }


def parse_trades(rows):
    """Keep our-market prints. A bad page is empty, not fatal."""
    if not isinstance(rows, list):
        return []
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        wallet = str(row.get('proxyWallet', '')).lower()
        if not WALLET_RE.fullmatch(wallet) or not our_slug(row.get('slug')):
            continue
        out.append(row)
    return out


def screen_activity(rows, history_complete=True):
    """Reject thin, bursty, or one-trade histories. Does not invent PnL.

    `history_complete` is false when the activity API still had a full page
    or refused the next offset. The span of that slice is not the wallet's age.
    """
    stats = market_stats(rows)
    ours = [r for r in rows if isinstance(r, dict) and str(r.get('type', '')).upper() == 'TRADE' and our_slug(r.get('slug'))]
    parsed = []
    bad = 0
    for row in ours:
        try:
            price = float(row.get('price'))
            ts = float(row.get('timestamp'))
            size = float(0 if row.get('size') is None else row.get('size'))
        except (TypeError, ValueError):
            bad += 1
            continue
        if not all(math.isfinite(x) for x in (price, ts, size)) or not 0 < price < 1 or size < 0:
            bad += 1
            continue
        parsed.append({
            'ts': ts,
            'price': price,
            'size': size,
            'slug': str(row.get('slug')),
            'side': str(row.get('side') or '').upper(),
            'detected_at': row.get('detected_at'),
            'detected_after': row.get('detected_after'),
        })
    reasons = []
    if ours and bad / len(ours) > 0.2:
        reasons.append('suspicious_activity')
    if (stats['our_share_30d'] or 0) < MIN_OUR_SHARE:
        reasons.append('wrong_markets')
    span = (max(p['ts'] for p in parsed) - min(p['ts'] for p in parsed)) if len(parsed) >= 2 else None
    # A cut-off page can still prove a long history. It cannot prove a short one.
    age_known = span is not None and (history_complete or span >= MIN_HISTORY_SECONDS)
    if history_complete and (stats['our_trades_30d'] or 0) < MIN_OUR_TRADES:
        reasons.append('too_little_history')
    if age_known and span < MIN_HISTORY_SECONDS and 'too_little_history' not in reasons:
        reasons.append('too_little_history')
    if len(parsed) >= MIN_OUR_TRADES:
        burst = max(Counter(int(p['ts']) for p in parsed).values())
        if burst / len(parsed) > 0.5:
            reasons.append('suspicious_activity')
    in_band = []
    timely = []
    for item in parsed:
        if item['side'] != 'BUY':
            continue
        price = Decimal(str(item['price']))
        if price < MIN_SOURCE_PRICE or price > MAX_SOURCE_PRICE:
            continue
        in_band.append(item)
        if seen_while_market_open(item):
            timely.append(item)
    our_n = stats['our_trades_30d'] or 0
    buys = [item for item in parsed if item['side'] == 'BUY']
    band_share = (len(in_band) / our_n) if our_n else 0.0
    timely_share = (len(timely) / our_n) if our_n else 0.0
    if our_n and not buys:
        reasons.append('no_copyable_buys')
    elif our_n and band_share < MIN_OUR_SHARE:
        reasons.append('poor_liquidity_or_price_band')
    elif our_n and timely_share < MIN_OUR_SHARE:
        reasons.append('cannot_copy_in_time')
    notionals = [p['price'] * p['size'] for p in parsed if p['size'] > 0]
    one_share = (max(notionals) / sum(notionals)) if notionals else None
    if one_share is not None and one_share > MAX_ONE_TRADE_SHARE:
        reasons.append('one_trade_dominates')
    deduped = []
    for reason in reasons:
        if reason not in deduped:
            deduped.append(reason)
    qualified = (stats['our_trades_30d'] or 0) >= MIN_OUR_TRADES and (stats['our_share_30d'] or 0) >= MIN_OUR_SHARE
    return {
        **stats,
        'history_complete': bool(history_complete),
        'age_known': age_known,
        'history_span_seconds': span,
        'history_span_is_lower_bound': not history_complete and span is not None,
        # Same gates the copier already applies. Not a result after fees.
        'passes_copy_filters_share': timely_share,
        'price_band_share': band_share,
        'copyable_after_costs': None,
        'copyable_after_costs_known': False,
        'best_trade_notional_share': one_share,
        'reject_reasons': deduped,
        'status': 'TRADES_OUR_MARKETS' if qualified else 'WRONG_MARKETS',
        'decision': 'REJECTED' if deduped or not qualified else 'ADMITTED',
    }


class WalletDiscovery:
    def __init__(self, store, fetch):
        self.store, self.fetch = store, fetch
        with store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS wallet_discovery_scans (ts REAL PRIMARY KEY, body TEXT NOT NULL)')

    @staticmethod
    def parse(rows):
        if not isinstance(rows, list): raise ValueError('Invalid leaderboard response')
        out = {}
        for row in rows:
            wallet = str(row.get('proxyWallet', '')).lower()
            if not re.fullmatch(r'0x[0-9a-f]{40}', wallet): raise ValueError('Invalid wallet')
            pnl, vol = float(row['pnl']), float(row['vol'])
            if not math.isfinite(pnl) or not math.isfinite(vol) or vol < 0: raise ValueError('Invalid leaderboard amount')
            out[wallet] = {'wallet': wallet, 'name': str(row.get('userName', ''))[:100], 'pnl': pnl, 'volume': vol}
        return out

    async def probe_activity(self, wallet, now):
        start, end = int(now - LOOKBACK), int(now)
        collected = []
        complete = False
        offset = 0
        cursor = None
        from .data_api import fetch_rows
        try:
            while offset <= ACTIVITY_OFFSET_CAP:
                rows, cursor = await asyncio.to_thread(
                    fetch_rows, self.fetch, 'activity', user=wallet, start=start, end=end,
                    limit=ACTIVITY_PAGE_SIZE, sortBy='TIMESTAMP', sortDirection='DESC', cursor=cursor,
                )
                collected.extend(rows)
                if not cursor:
                    complete = True
                    break
                stamps = []
                for row in collected:
                    try:
                        stamps.append(float(row.get('timestamp')))
                    except (TypeError, ValueError):
                        continue
                if len(stamps) >= 2 and max(stamps) - min(stamps) >= MIN_HISTORY_SECONDS:
                    break
                offset += ACTIVITY_PAGE_SIZE
        except Exception:
            if not collected:
                return {'trades_30d': None, 'our_trades_30d': None, 'our_share_30d': None, 'probe': 'ERROR'}
            complete = False
        stats = screen_activity(collected, history_complete=complete)
        stats['probe'] = 'OK'
        return stats

    async def recent_tape(self):
        from .data_api import fetch_rows
        found = []
        cursor = None
        for page in range(TAPE_PAGES):
            try:
                batch, cursor = await asyncio.to_thread(fetch_rows, self.fetch, 'trades', limit=500, cursor=cursor)
            except Exception:
                break
            found.extend(parse_trades(batch))
            if not cursor:
                break
        return found

    async def scan(self):
        previous = self.store.get('wallet_discovery', {})
        try:
            now = time.time()
            from .data_api import fetch_rows
            def board(period):
                return fetch_rows(self.fetch, 'leaderboard', category='CRYPTO', timePeriod=period,
                                  orderBy='PNL', limit=50)[0]
            month = self.parse(await asyncio.to_thread(board, 'MONTH'))
            week = {}
            try:
                week = self.parse(await asyncio.to_thread(board, 'WEEK'))
            except Exception:
                week = {}
            tape = await self.recent_tape()
            tape_counts = Counter(str(row.get('proxyWallet', '')).lower() for row in tape)
            ranked = sorted((w for w in month.values() if w['pnl'] > 0 and w['volume'] > MIN_MONTH_VOLUME),
                            key=lambda w: w['pnl'], reverse=True)
            probe = []
            for item in ranked[:LEADERBOARD_PROBES]:
                probe.append(item['wallet'])
            for wallet, _count in tape_counts.most_common():
                if wallet not in probe:
                    probe.append(wallet)
                if len(probe) >= PROBE_CAP:
                    break
            by_wallet = {}
            for index, item in enumerate(ranked[:20]):
                wk = week.get(item['wallet'], {})
                by_wallet[item['wallet']] = {
                    'wallet': item['wallet'], 'name': item['name'], 'source': 'leaderboard',
                    'month_reported_pnl': item['pnl'], 'month_volume': item['volume'],
                    'week_reported_pnl': wk.get('pnl'), 'week_volume': wk.get('volume'),
                    'qualify_days': 30, 'copy_enabled': False, 'status': 'SHORTLIST_30D',
                    'decision': 'NOT_PROBED', 'reject_reasons': [],
                }
                if index < LEADERBOARD_PROBES:
                    by_wallet[item['wallet']]['on_probe_list'] = True
            for wallet in probe:
                row = by_wallet.get(wallet) or {
                    'wallet': wallet, 'name': '', 'source': 'market_trades',
                    'month_reported_pnl': None, 'month_volume': None,
                    'week_reported_pnl': None, 'week_volume': None,
                    'qualify_days': 30, 'copy_enabled': False, 'status': 'SHORTLIST_30D',
                    'decision': 'NOT_PROBED', 'reject_reasons': [],
                }
                if wallet in by_wallet and tape_counts.get(wallet):
                    row['source'] = 'both'
                stats = await self.probe_activity(wallet, now)
                row.update({k: v for k, v in stats.items() if k != 'status' and k != 'decision'})
                if stats.get('probe') == 'OK':
                    row['status'] = stats['status']
                    row['decision'] = stats['decision']
                    row['reject_reasons'] = stats['reject_reasons']
                else:
                    row['status'] = 'PROBE_ERROR'
                    row['decision'] = 'REJECTED'
                    row['reject_reasons'] = ['probe_error']
                row['score'] = {
                    'net_pnl_usd': None,
                    'net_pnl_note': 'no settled copy evidence yet',
                    'win_rate': None,
                    'trades': row.get('our_trades_30d'),
                    'consistency_best_trade_share': row.get('best_trade_notional_share'),
                    'drawdown_usd': None,
                    'recent_7d_usd': None,
                    'fees_usd': None,
                    'fee_known': False,
                    'passes_copy_filters_share': row.get('passes_copy_filters_share'),
                    'copyable_after_costs': None,
                    'copyable_after_costs_known': False,
                }
                by_wallet[wallet] = row
            candidates = list(by_wallet.values())
            prune_discovery_rows(self.store)
            from .wallet_roster import (
                AUDIT_KEY, admit_observed, bootstrap, copy_evidence, tick as roster_tick,
            )
            roster = bootstrap(self.store, now)
            known = set((roster.get('wallets') or {}))
            observe_stats = {
                wallet: copy_evidence(self.store, wallet, now)
                for wallet, row in (roster.get('wallets') or {}).items()
                if row.get('state') == 'observed'
            }
            try:
                roster_tick(self.store, now, observe_stats)
            except Exception as error:
                self.store.set('wallet_discovery_roster_error', {'error': str(error)[:300], 'at': now})
            roster = self.store.get('wallet_roster', roster)
            known = set((roster.get('wallets') or {}))
            admitted = []
            from .wallet_roster import audit
            for row in candidates:
                wallet = row['wallet']
                if wallet in known:
                    row['decision'] = 'already_on_roster'
                    continue
                if row.get('decision') != 'ADMITTED':
                    if row.get('decision') == 'REJECTED':
                        audit(self.store, now, wallet, 'rejected', ','.join(row.get('reject_reasons') or ['rejected']), {
                            'status': row.get('status'),
                            'our_trades_30d': row.get('our_trades_30d'),
                            'age_known': row.get('age_known'),
                            'history_complete': row.get('history_complete'),
                            'passes_copy_filters_share': row.get('passes_copy_filters_share'),
                            'copyable_after_costs': None,
                            'best_trade_notional_share': row.get('best_trade_notional_share'),
                        })
                    continue
                evidence = {
                    'source': row.get('source'),
                    'our_trades_30d': row.get('our_trades_30d'),
                    'our_share_30d': row.get('our_share_30d'),
                    'history_span_seconds': row.get('history_span_seconds'),
                    'age_known': row.get('age_known'),
                    'history_complete': row.get('history_complete'),
                    'passes_copy_filters_share': row.get('passes_copy_filters_share'),
                    'copyable_after_costs': None,
                    'best_trade_notional_share': row.get('best_trade_notional_share'),
                    'copy_sim_net_usd': None,
                }
                _state, added = admit_observed(
                    self.store, wallet, now, evidence,
                    'discovery-v1 observed: our-market activity passed the screen; paper test not open',
                )
                if added:
                    admitted.append(wallet)
            for row in candidates:
                evidence = copy_evidence(self.store, row['wallet'], now)
                if evidence['our_trades'] and isinstance(row.get('score'), dict):
                    after_costs = evidence['copy_sim_net_usd'] if evidence['fee_known'] else None
                    row['score'].update({
                        'net_pnl_usd': evidence['copy_sim_net_usd'],
                        'net_pnl_note': 'settled hypothetical copies',
                        'win_rate': evidence['win_rate'],
                        'drawdown_usd': evidence['max_drawdown_usd'],
                        'recent_7d_usd': evidence['net_7d'],
                        'fees_usd': evidence['fees_usd'],
                        'fee_known': evidence['fee_known'],
                        'copyable_after_costs': after_costs,
                        'copyable_after_costs_known': evidence['fee_known'],
                    })
            audit_log = self.store.get(AUDIT_KEY, [])
            state = {
                'spec': SPEC, 'status': 'SCAN_OK', 'checked_at': now, 'last_success_at': now,
                'interval_seconds': 3600, 'category': 'CRYPTO', 'qualify_days': 30,
                'scope': (
                    'CRYPTO month top 50 is a lead only. Up to 8 of those are probed, '
                    'then the busiest wallets on the live BTC/ETH 5m/15m trades tape, 12 probes max. '
                    'A complete activity pull must cover at least a day. A pull cut by the API limit '
                    'does not prove the wallet is young. The 20-70c band is the copier price gate. '
                    'The copier 90s limit is signal age at detection, not time left in the market. '
                    'Neither number is a result after fees. PAPER_TEST uses the existing roster rules on our hypothetical copies.'
                ),
                'candidates': candidates, 'copy_enabled': False,
                'tape_wallets': len(tape_counts), 'tape_prints': len(tape),
                'probed': len(probe), 'admitted_observed': admitted,
                'limitation': (
                    'Reported month PnL is not copy profit. Passing the copier price and time gates is not '
                    'a fill after fees; that number stays empty until a hypothetical ticket settles with a fee. '
                    'Admitted wallets are watched with buys paused. '
                    'PAPER_TEST starts only after 20 settled hypothetical copies, 5 windows, '
                    'positive copy net and no single day above 70% of gains. There is no calendar-day wait. Live trading is off.'
                ),
                'recent_audit': audit_log[-12:] if isinstance(audit_log, list) else [],
                'error': None,
            }
            with self.store.connect() as db:
                db.execute('INSERT INTO wallet_discovery_scans VALUES (?,?)', (now, json.dumps(state, allow_nan=False)))
            self.store.set('wallet_discovery', state)
        except Exception as error:
            self.store.set('wallet_discovery', {**previous, 'status': 'ERROR', 'checked_at': time.time(),
                                                'error': str(error)[:300], 'copy_enabled': False})

    async def run(self):
        while True:
            await self.scan()
            await asyncio.sleep(3600)
