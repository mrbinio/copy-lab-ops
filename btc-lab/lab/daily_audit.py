"""Daily audit of the PAPER lab, sent to Telegram. It never trades.

Damian, 11 Oct 2026: he wants real money from 18 Oct, so the technical
faults found by hand on 10-11 Oct must be caught every day without him.
Each check is OK, PROBLEM or UWAGA (worth a look, does not block). A day
with no PROBLEM counts toward readiness: LIVE needs READY_DAYS in a row.

Checks, over the last 24 hours:
  mitch_on_time    share of Mitch's BTC 15m buys judged inside 1 s
  fast_lane        match -> fill read from the pending tx, p90
  db_lock          wait for the SQLite write lock, p90 of a short sample
  restarts         watchdog restarts of the worker
  ledger           desk result equals the closed copies since the desk start
  heartbeat        worker, qualifier process, recorder, Telegram alive
  live_gate        real orders still disabled in code and config (PAPER)
  disk             free disk
  qualifier_speed  qualifier decisions for copying wallets (UWAGA only)

Runs as launchd com.btc-lab.audit every morning at 07:30.
"""
import json
import os
import shutil
import sqlite3
import statistics
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

DAY = 86400
READY_DAYS = 3
ON_TIME_MIN = 0.90
ON_TIME_MIN_BUYS = 20
FAST_P90_MAX_S = 0.8
LOCK_P90_MAX_MS = 500
DISK_MIN_BYTES = 15 * 1024 ** 3
QUALIFIER_DECIDE_MAX_S = 5
HANDLED = ('MITCH_BUY', 'MITCH_ADD', 'WINDOW_LIMIT', 'NO_LIQUIDITY', 'PRICE_WORSE_THAN_10C',
           'DESK_CASH', 'MITCH_PAUSED', 'GLOBAL_STOP', 'PAPER_CASH')
LATE = ('LATE_BUY_NOT_COPIED',)


def check(name, status, detail, value=None):
    return {'name': name, 'status': status, 'detail': detail, 'value': value}


def p90(values):
    values = sorted(values)
    return values[int(len(values) * 0.9)] if values else None


def mitch_on_time(db, since):
    """Mitch's fast-lane BTC 15m buys: judged inside 1 s, or late."""
    from .mitch_copy import WALLETS
    marks = ','.join('?' * len(WALLETS))
    rows = db.execute(
        f"""SELECT e.reason FROM mitch_events e JOIN wallet_activity a
            ON a.wallet=e.wallet AND a.event_key=e.event_key
            WHERE e.at>=? AND e.wallet IN ({marks})
              AND json_extract(a.body,'$._source')='clob_match'
              AND json_extract(a.body,'$.side')='BUY'""",
        (since, *WALLETS)).fetchall()
    handled = sum(1 for (r,) in rows if r in HANDLED)
    late = sum(1 for (r,) in rows if r in LATE)
    total = handled + late
    if total < ON_TIME_MIN_BUYS:
        return check('mitch_on_time', 'UWAGA', 'za mało kupna Mitcha do oceny (%d)' % total, None)
    share = handled / total
    return check('mitch_on_time', 'OK' if share >= ON_TIME_MIN else 'PROBLEM',
                 '%.0f%% jego kupna ocenionych w 1 s (%d z %d, próg %.0f%%)' % (
                     share * 100, handled, total, ON_TIME_MIN * 100), round(share, 3))


def fast_lane(db, since):
    from .mitch_copy import WALLETS
    marks = ','.join('?' * len(WALLETS))
    ages = []
    for print_at, resolve_ms, ts in db.execute(
            f"""SELECT json_extract(body,'$._print_at'), json_extract(body,'$._resolve_ms'),
                       json_extract(body,'$.timestamp')
                FROM wallet_activity WHERE first_seen>=? AND wallet IN ({marks})
                  AND json_extract(body,'$._source')='clob_match'""", (since, *WALLETS)):
        if print_at and resolve_ms is not None and ts:
            ages.append(float(print_at) + float(resolve_ms) / 1000 - float(ts))
    if not ages:
        return check('fast_lane', 'UWAGA', 'brak transakcji Mitcha z szybkiej ścieżki', None)
    worst = p90(ages)
    return check('fast_lane', 'OK' if worst <= FAST_P90_MAX_S else 'PROBLEM',
                 'transakcja odczytana po %.2f s (p90, mediana %.2f s, %d szt.)' % (
                     worst, statistics.median(ages), len(ages)), round(worst, 3))


def db_lock(path, samples=20, pause=0.2):
    """Empty write transactions: how long the shared lock makes a writer wait."""
    db = sqlite3.connect(path, timeout=30, isolation_level=None)
    waits = []
    try:
        for _ in range(samples):
            started = time.perf_counter()
            db.execute('BEGIN IMMEDIATE')
            db.execute('COMMIT')
            waits.append((time.perf_counter() - started) * 1000)
            time.sleep(pause)
    finally:
        db.close()
    worst = p90(waits)
    return check('db_lock', 'OK' if worst <= LOCK_P90_MAX_MS else 'PROBLEM',
                 'czekanie na zapis do bazy %.0f ms (p90), max %.0f ms' % (worst, max(waits)), round(worst, 1))


def restarts(logs, since):
    count = 0
    path = Path(logs) / 'watchdog.out'
    try:
        lines = path.read_text().splitlines()[-5000:]
    except OSError:
        lines = []
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get('action') == 'restart_requested' and float(row.get('at') or 0) >= since:
            count += 1
    return check('restarts', 'OK' if count == 0 else 'PROBLEM',
                 'restarty workera przez watchdog: %d' % count, count)


def ledger(db):
    row = db.execute("SELECT body FROM state WHERE key='mitch_desk'").fetchone()
    if not row:
        return check('ledger', 'UWAGA', 'biurko Mitcha jeszcze nie wystartowało', None)
    desk = json.loads(row[0])
    total = 0
    for (body,) in db.execute('SELECT body FROM mitch_positions'):
        trade = json.loads(body)
        if float(trade.get('opened') or 0) >= float(desk['start_at']) and \
                trade.get('status') in ('CLOSED', 'SETTLED') and trade.get('pnl_micro') is not None:
            total += int(trade['pnl_micro'])
    gap = int(desk['realized_micro']) - total
    money = int(desk['line_micro']) + int(desk['realized_micro']) - int(desk['swept_micro'])
    ok = abs(gap) <= 10
    return check('ledger', 'OK' if ok else 'PROBLEM',
                 'biurko %.2f USD, rezerwa z biurka %.2f, wynik %+.2f%s' % (
                     money / 1e6, int(desk['swept_micro']) / 1e6, int(desk['realized_micro']) / 1e6,
                     '' if ok else ' · różnica z pozycjami %.2f USD' % (gap / 1e6)), gap)


def heartbeat(state, db, now):
    problems = []
    worker = state.get('worker') or {}
    if now - float(worker.get('heartbeat') or 0) > 60:
        problems.append('worker stoi')
    row = db.execute("SELECT body FROM state WHERE key='qualifier_process'").fetchone()
    q = json.loads(row[0]) if row else {}
    if now - float(q.get('at') or 0) > 120:
        problems.append('proces kwalifikatora stoi')
    if not (state.get('recorder_status') or {}).get('ok'):
        problems.append('rejestrator')
    tg = state.get('telegram_status') or {}
    if tg and tg.get('ok') is False:
        problems.append('Telegram')
    return check('heartbeat', 'PROBLEM' if problems else 'OK',
                 'wszystko żyje' if not problems else 'nie działa: ' + ', '.join(problems), problems)


def live_gate(state, root):
    from .live_gate import LIVE_ORDERS_ALLOWED
    try:
        config = json.loads((Path(root) / 'config.json').read_text())
    except (OSError, ValueError):
        config = {}
    on = bool(LIVE_ORDERS_ALLOWED) or config.get('clob_live') is True or bool(state.get('live_enabled'))
    return check('live_gate', 'PROBLEM' if on else 'OK',
                 'prawdziwe zlecenia WŁĄCZONE — to nie jest PAPER' if on else 'PAPER: prawdziwe zlecenia wyłączone w kodzie',
                 on)


def disk(root):
    free = shutil.disk_usage(str(root)).free
    return check('disk', 'OK' if free >= DISK_MIN_BYTES else 'PROBLEM', 'wolne %.0f GB' % (free / 1024 ** 3), free)


def qualifier_speed(db, since):
    row = db.execute("SELECT body FROM state WHERE key='wallet_roster'").fetchone()
    roster = (json.loads(row[0]) if row else {}).get('wallets') or {}
    copying = [w for w, r in roster.items() if (r or {}).get('state') in ('paper_test', 'paper_active')]
    if not copying:
        return check('qualifier_speed', 'UWAGA', 'brak portfeli w kopiowaniu', None)
    marks = ','.join('?' * len(copying))
    waits = [r[0] for r in db.execute(
        f"""SELECT e.ts-a.first_seen FROM wallet_copy_events e JOIN wallet_activity a
            ON a.wallet=e.wallet AND a.event_key=e.event_key
            WHERE e.ts>=? AND e.wallet IN ({marks}) AND e.reason!='PROCESSING'""", (since, *copying))]
    if not waits:
        return check('qualifier_speed', 'UWAGA', 'brak decyzji kwalifikatora', None)
    median = statistics.median(waits)
    return check('qualifier_speed', 'OK' if median <= QUALIFIER_DECIDE_MAX_S else 'UWAGA',
                 'decyzja po %.0f s (mediana, %d decyzji)' % (median, len(waits)), round(median, 1))


def results(db, since):
    row = db.execute("SELECT body FROM state WHERE key='mitch_desk'").fetchone()
    start = float(json.loads(row[0])['start_at']) if row else 0
    windows = {}
    for (body,) in db.execute('SELECT body FROM mitch_positions'):
        trade = json.loads(body)
        if float(trade.get('opened') or 0) < start or trade.get('pnl_micro') is None:
            continue
        if float(trade.get('closed_at') or 0) < since:
            continue
        windows[trade.get('market')] = windows.get(trade.get('market'), 0) + int(trade['pnl_micro'])
    return {'windows': len(windows), 'won': sum(1 for v in windows.values() if v > 0),
            'lost': sum(1 for v in windows.values() if v < 0), 'net_micro': sum(windows.values())}


def fetch_state(url='http://127.0.0.1:8769/api/state?asset=BTC'):
    try:
        with urllib.request.urlopen(url, timeout=20) as reply:
            return json.loads(reply.read())
    except Exception:
        return {}


def run_checks(root, now=None, state=None, lock_samples=20):
    root = Path(root)
    now = now or time.time()
    since = now - DAY
    path = root / 'data' / 'lab.sqlite'
    state = fetch_state() if state is None else state
    ro = sqlite3.connect('file:%s?mode=ro' % path, uri=True, timeout=30)
    try:
        checks = [
            mitch_on_time(ro, since),
            fast_lane(ro, since),
            db_lock(str(path), samples=lock_samples) if lock_samples else check('db_lock', 'UWAGA', 'pominięto', None),
            restarts(root / 'logs', since),
            ledger(ro),
            heartbeat(state, ro, now),
            live_gate(state, root),
            disk(root),
            qualifier_speed(ro, since),
        ]
        day = results(ro, since)
    finally:
        ro.close()
    return {'at': now, 'checks': checks, 'results': day,
            'ok': not any(c['status'] == 'PROBLEM' for c in checks)}


def update_history(report, path):
    try:
        history = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        history = []
    day = time.strftime('%Y-%m-%d', time.localtime(report['at']))
    history = [h for h in history if h.get('day') != day][-30:]
    history.append({'day': day, 'ok': report['ok'],
                    'problems': [c['name'] for c in report['checks'] if c['status'] == 'PROBLEM']})
    streak = 0
    for h in reversed(history):
        if not h['ok']:
            break
        streak += 1
    report['streak'] = streak
    report['ready'] = streak >= READY_DAYS
    tmp = Path(str(path) + '.tmp')
    tmp.write_text(json.dumps(history))
    os.replace(tmp, path)
    return report


NAMES = {
    'mitch_on_time': 'Mitch w 1 s', 'fast_lane': 'Szybka ścieżka', 'db_lock': 'Baza danych',
    'restarts': 'Restarty', 'ledger': 'Księga biurka', 'heartbeat': 'Usługi',
    'live_gate': 'Tryb PAPER', 'disk': 'Dysk', 'qualifier_speed': 'Twoje portfele',
}
MARK = {'OK': '✅', 'PROBLEM': '❌', 'UWAGA': '⚠️'}


def text(report):
    lines = ['Audyt dzienny BTC Lab (PAPER) · ostatnie 24 h',
             'Wynik: %s' % ('wszystko OK' if report['ok'] else 'są PROBLEMY — sprawdzam')]
    for c in report['checks']:
        lines.append('%s %s: %s' % (MARK.get(c['status'], ''), NAMES.get(c['name'], c['name']), c['detail']))
    r = report.get('results') or {}
    lines.append('Mitch 24 h: %d okien, %d wygranych, %d przegranych, netto %+.2f USD' % (
        r.get('windows', 0), r.get('won', 0), r.get('lost', 0), (r.get('net_micro') or 0) / 1e6))
    if 'streak' in report:
        lines.append('Gotowość do LIVE: %d/%d dni z rzędu bez problemu%s' % (
            min(report['streak'], READY_DAYS), READY_DAYS,
            ' — technicznie gotowe' if report.get('ready') else ''))
    return '\n'.join(lines)


def send_telegram(root, message):
    try:
        config = json.loads((Path(root) / 'telegram.json').read_text())
    except (OSError, ValueError):
        return 0
    sent = 0
    for chat in config.get('chat_ids') or []:
        data = urllib.parse.urlencode({'chat_id': chat, 'text': message}).encode()
        try:
            urllib.request.urlopen('https://api.telegram.org/bot%s/sendMessage' % config['token'], data, timeout=20).read()
            sent += 1
        except Exception as error:
            print('telegram: %s' % str(error)[:120], file=sys.stderr)
    return sent


def main(root):
    root = Path(root)
    report = update_history(run_checks(root), root / 'logs' / 'daily-audit-history.json')
    report['text'] = text(report)
    out = root / 'logs' / 'daily-audit.json'
    tmp = out.with_suffix('.tmp')
    tmp.write_text(json.dumps(report, default=str))
    os.replace(tmp, out)
    print(report['text'])
    send_telegram(root, report['text'])


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else str(Path.home() / 'Library/Application Support/BTC Lab'))
