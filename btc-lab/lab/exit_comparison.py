"""Paired PAPER exit research on future accepted baseline entries only.

No account, ledger, order or risk changes. Both arms use the same polling stream.
An intent fills only on a later received snapshot after >=250ms; actual polling
delay is recorded. Missing observation intervals invalidate the pair for ranking.
"""
import json
from .mid_window import simulate_sale

EXPERIMENT = 'paired-exits-v1'
ARMS = {'baseline-10-20': (.10, .20), 'candidate-15-10': (.15, .10)}

class ExitComparison:
    def __init__(self, store):
        self.store = store
        with store.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS exit_comparison (
                source_id INTEGER NOT NULL, arm TEXT NOT NULL, body TEXT NOT NULL,
                PRIMARY KEY(source_id, arm))''')

    def capture(self, market, now):
        """Called only immediately after a successfully accepted new entry."""
        with self.store.connect() as db:
            p = db.execute("SELECT * FROM positions WHERE strategy='mid-window-v1' AND market=?",
                           (market['slug'],)).fetchone()
            if not p or not 0 <= now-p['opened'] <= 5:
                return
            for arm in ARMS:
                body = {'experiment': EXPERIMENT, 'source_id': p['id'], 'arm': arm,
                        'market': p['market'], 'side': p['side'], 'shares': p['shares'],
                        'cost': p['cost'], 'entry_fee': p['fee'], 'opened': p['opened'],
                        'last_checked': now, 'status': 'OPEN', 'pending': None,
                        'invalid_reasons': [], 'attempts': 0}
                db.execute('INSERT OR IGNORE INTO exit_comparison VALUES (?,?,?)',
                           (p['id'], arm, json.dumps(body)))

    @staticmethod
    def advance(p, market, now, allowed=True):
        if p['status'] != 'OPEN':
            return
        cutoff = int(p['market'].rsplit('-', 1)[1])+600
        if p['last_checked'] < cutoff and now-p['last_checked'] > 10:
            if 'OBSERVATION_GAP' not in p['invalid_reasons']:
                p['invalid_reasons'].append('OBSERVATION_GAP')
        p['last_checked'] = now
        if now >= cutoff:
            p['pending'] = None
            return
        if market.get('slug') != p['market']:
            return
        if not allowed or not all(market.get(k) for k in ('accepting','fee_verified','rule_supported')):
            p['pending'] = None
            if 'EXECUTION_BLOCKED' not in p['invalid_reasons']:
                p['invalid_reasons'].append('EXECUTION_BLOCKED')
            return
        book = market['books'][p['side']]
        if not -.25 <= now-book['source_ts'] <= 3:
            if 'STALE_BOOK' not in p['invalid_reasons']:
                p['invalid_reasons'].append('STALE_BOOK')
            return
        pending = p['pending']
        if pending:
            if now-pending['at'] < .25:
                return
            p['pending'] = None
            p['attempts'] += 1
            # Must observe a new source snapshot, not reuse a decision quote.
            if book['source_ts'] <= pending['source_ts'] or book['received_at'] <= pending['at']:
                return
            fill = simulate_sale(book, p['shares'], market['fee_rate'], pending['floor'])
            if fill:
                p.update(status='SOLD', closed=now, proceeds=fill['proceeds'],
                         exit_fee=fill['fee'], pnl=fill['proceeds']-fill['fee']-p['cost']-p['entry_fee'],
                         exit_reason=pending['reason'], latency_seconds=now-pending['at'],
                         decision=pending, arrival={'source_ts':book['source_ts'],
                         'received_at':book['received_at'], 'fee_rate':market['fee_rate'],
                         'fills':fill['fills']})
            return
        fill = simulate_sale(book, p['shares'], market['fee_rate'])
        if not fill:
            return
        basis = p['cost']+p['entry_fee']
        net = fill['proceeds']-fill['fee']-basis
        tp, sl = ARMS[p['arm']]
        reason = ('TIME' if now >= cutoff-10 else 'STOP' if net <= -sl*basis
                  else 'PROFIT' if net >= tp*basis else None)
        if reason:
            p['pending'] = {'at':now, 'source_ts':book['source_ts'],
                            'floor':fill['fills'][-1]['price'], 'reason':reason,
                            'decision_net':net, 'fee_rate':market['fee_rate']}

    def step(self, market, now, allowed=True):
        with self.store.connect() as db:
            rows = db.execute('SELECT source_id,arm,body FROM exit_comparison').fetchall()
            for row in rows:
                p = json.loads(row['body'])
                if p['status'] != 'OPEN':
                    continue
                self.advance(p, market, now, allowed)
                if p['status'] == 'OPEN':
                    label = db.execute('SELECT winner,ts,evidence FROM labels WHERE market=?',
                                       (p['market'],)).fetchone()
                    if label and now >= int(p['market'].rsplit('-',1)[1])+900:
                        evidence = json.loads(label['evidence'])
                        if evidence.get('source') == 'clob_official_winner' and evidence.get('closed') is True:
                            proceeds = p['shares'] if label['winner'] == p['side'] else 0
                            p.update(status='SETTLED', closed=label['ts'], proceeds=proceeds,
                                     exit_fee=0, pnl=proceeds-p['cost']-p['entry_fee'], pending=None,
                                     exit_reason='OFFICIAL_SETTLEMENT')
                db.execute('UPDATE exit_comparison SET body=? WHERE source_id=? AND arm=?',
                           (json.dumps(p, allow_nan=False), row['source_id'], row['arm']))
            all_rows = [json.loads(r[0]) for r in db.execute('SELECT body FROM exit_comparison ORDER BY source_id,arm')]
        summary = summarize(all_rows)
        summary['updated_at'] = now
        self.store.set('exit_comparison', summary)

def summarize(rows):
    pairs = {}
    for r in rows:
        pairs.setdefault(r['source_id'], {})[r['arm']] = r
    valid = [p for p in pairs.values() if set(p) == set(ARMS) and
             all(r['status'] != 'OPEN' and not r['invalid_reasons'] for r in p.values())]
    results = {}
    for arm in ARMS:
        selected = sorted((p[arm] for p in valid), key=lambda r:(r['closed'],r['source_id']))
        equity = peak = drawdown = 0
        for r in selected:
            equity += r['pnl']; peak = max(peak,equity); drawdown = max(drawdown,peak-equity)
        results[arm] = {'net_usd':equity/1e6, 'max_realized_drawdown_usd':drawdown/1e6,
                        'fees_usd':sum(r['entry_fee']+r['exit_fee'] for r in selected)/1e6}
    return {'experiment':EXPERIMENT, 'mode':'PAIRED_PAPER_RESEARCH', 'pairs':len(pairs),
            'completed_valid_pairs':len(valid),
            'invalid_pairs':sum(any(r['invalid_reasons'] for r in p.values()) for p in pairs.values()),
            'pending_pairs':sum(any(r['status']=='OPEN' for r in p.values()) for p in pairs.values()),
            'results':results, 'rows':rows[-1000:], 'rows_truncated':len(rows)>1000,
            'limitations':['Conditional on accepted mid-window-v1 entries and its risk limits.',
                'Polling snapshots; not actual venue fills. Minimum 250ms, actual latency recorded.',
                '50% displayed depth; full fill or no fill, no partial execution.',
                'Missing intervals invalidate ranking; no historical backfill or live eligibility.']}
