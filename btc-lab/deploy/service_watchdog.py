#!/usr/bin/python3
"""Independent check that the paper service is doing work, not merely alive.

A running process and HTTP 200 are not enough. This reads the heartbeat,
the copy publish time and the Mitch publish time. A quiet market is not
a failure. A frozen publish or a dead heartbeat is.
"""
import json
import os
import subprocess
import time
from pathlib import Path

ROOT = Path(os.environ.get(
    'BTC_LAB_ROOT',
    str(Path.home() / 'Library/Application Support/BTC Lab'),
))
LABEL = os.environ.get('BTC_LAB_LABEL', 'gui/%s/com.btc-lab.paper' % os.getuid())
PORT = int(os.environ.get('BTC_LAB_PORT', '8769'))
ATTEMPTS = ROOT / 'watchdog-attempts.json'
STATUS = ROOT / 'logs/watchdog-status.json'
MAX_RESTARTS = 3
WINDOW = 1800
HEARTBEAT_LIMIT = 90
PUBLISH_LIMIT = 180


def load(path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def save_status(body):
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(json.dumps(body))


def recent_attempts(now):
    rows = [x for x in load(ATTEMPTS, []) if now - x < WINDOW]
    return rows


def restart(now, reason):
    rows = recent_attempts(now)
    if len(rows) >= MAX_RESTARTS:
        return 'restart_limited'
    ATTEMPTS.write_text(json.dumps(rows + [now]))
    subprocess.run(['/bin/launchctl', 'kickstart', '-k', LABEL], check=False, timeout=30)
    return 'restarted'


def read_state(db_path):
    import sqlite3
    uri = 'file:%s?mode=ro' % db_path
    db = sqlite3.connect(uri, uri=True, timeout=5)
    try:
        out = {}
        keys = (
            'worker', 'wallet_copy_execution', 'mitch_copy', 'clock_status',
            'wallet_copy_health', 'wallet_copy_progress', 'mitch_progress',
            'task_health', 'mitch_health',
        )
        for key in keys:
            row = db.execute('SELECT body FROM state WHERE key=?', (key,)).fetchone()
            out[key] = json.loads(row[0]) if row else {}
        return out
    finally:
        db.close()


def _age(now, stamp):
    return None if not stamp else round(now - float(stamp), 1)


def assess(now, state, http_ok, launch_wait=None, process_age=None, http_failures=0):
    """A live heartbeat does not hide a stopped copier or a publish that never moved.

    A ledger mismatch holds buys and is not restarted. A launch-limit wait is
    not kicked again. HTTP is noted, then restarted only after repeated failures.
    """
    worker = state.get('worker') or {}
    copy = state.get('wallet_copy_execution') or {}
    mitch = state.get('mitch_copy') or {}
    health = state.get('wallet_copy_health') or {}
    mitch_health = state.get('mitch_health') or {}
    copy_progress = state.get('wallet_copy_progress') or {}
    mitch_progress = state.get('mitch_progress') or {}
    heartbeat = float(worker.get('heartbeat') or 0)
    copy_at = float(copy.get('updated_at') or 0)
    mitch_at = float(mitch.get('updated_at') or 0)
    copy_step = float(copy_progress.get('at') or 0)
    mitch_step = float(mitch_progress.get('at') or 0)
    restart_problems = []
    noted = []
    old = process_age is not None and process_age >= 180
    waiting = bool(launch_wait and float(launch_wait.get('retry_at') or 0) > now)
    if waiting:
        noted.append('launch_wait')
    elif not heartbeat or now - heartbeat > HEARTBEAT_LIMIT:
        if heartbeat or old or process_age is None:
            restart_problems.append('heartbeat')
    if copy_at and now - copy_at > PUBLISH_LIMIT:
        restart_problems.append('copy_publish')
    elif old and not copy_at:
        restart_problems.append('copy_publish_never')
    if mitch_at and now - mitch_at > PUBLISH_LIMIT:
        restart_problems.append('mitch_publish')
    elif old and not mitch_at:
        restart_problems.append('mitch_publish_never')
    if copy_step and now - copy_step > PUBLISH_LIMIT:
        restart_problems.append('copy_stalled')
    elif old and not copy_step:
        restart_problems.append('copy_never_progressed')
    if mitch_step and now - mitch_step > PUBLISH_LIMIT:
        restart_problems.append('mitch_stalled')
    elif old and not mitch_step:
        restart_problems.append('mitch_never_progressed')
    if not http_ok:
        noted.append('connection')
        if http_failures >= 3 and not waiting:
            restart_problems.append('connection')
    if health.get('status') == 'ledger_mismatch' or mitch_health.get('status') == 'mismatch':
        noted.append('ledger_mismatch')
    if waiting:
        restart_problems = []
    return restart_problems, noted, {
        'heartbeat_age_s': _age(now, heartbeat),
        'copy_publish_age_s': _age(now, copy_at),
        'mitch_publish_age_s': _age(now, mitch_at),
        'copy_step_age_s': _age(now, copy_step),
        'mitch_step_age_s': _age(now, mitch_step),
        'copy_queue': copy_progress.get('queue'),
        'mitch_queue': mitch_progress.get('queue'),
    }


def notify(body):
    """One optional webhook. The address is environment-only and is never stored."""
    url = os.environ.get('BTC_LAB_ALERT_URL', '').strip()
    if not url:
        return 'unconfigured'
    if body.get('status') == 'ok':
        return 'quiet'
    try:
        import urllib.request
        data = json.dumps({
            'status': body.get('status'),
            'problems': body.get('problems'),
            'action': body.get('action'),
        }).encode()
        req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=5):
            return 'sent'
    except Exception:
        return 'failed'


def process_age(now):
    """Seconds since the paper wrapper started. A slow open is not a hang yet."""
    try:
        proc = subprocess.run(
            ['/bin/ps', '-axo', 'etime,command'],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    for line in proc.stdout.splitlines():
        if 'macos_service.py' not in line:
            continue
        etime = line.split(None, 1)[0]
        parts = [int(p) for p in etime.replace('-', ':').split(':')]
        seconds = 0
        for part in parts:
            seconds = seconds * 60 + part
        return seconds
    return None


def main():
    now = time.time()
    http_ok = False
    try:
        import urllib.request
        with urllib.request.urlopen('http://127.0.0.1:%s/healthz' % PORT, timeout=3) as response:
            http_ok = response.status == 200
    except Exception:
        http_ok = False
    db = ROOT / 'data' / 'lab.sqlite'
    try:
        state = read_state(db)
    except Exception as error:
        state = {}
        read_error = str(error)[:200]
    else:
        read_error = None
    launch_wait = load(ROOT / 'logs' / 'service-stopped.json', None)
    previous = load(STATUS, {})
    http_failures = int(previous.get('http_failures') or 0)
    http_failures = 0 if http_ok else http_failures + 1
    age = process_age(now)
    restart_problems, noted, ages = assess(
        now, state, http_ok, launch_wait, process_age=age, http_failures=http_failures,
    )
    action = 'ok'
    proof = load(ROOT / 'logs' / 'watchdog-restart.json', None)
    if proof and not proof.get('verified') and age is not None and age >= 180 and not restart_problems:
        proof['verified'] = True
        proof['verified_at'] = now
        (ROOT / 'logs' / 'watchdog-restart.json').write_text(json.dumps(proof))
    if restart_problems and age is not None and age < 180:
        action = 'starting'
    elif restart_problems:
        action = restart(now, ','.join(restart_problems))
        if action == 'restarted':
            (ROOT / 'logs').mkdir(parents=True, exist_ok=True)
            (ROOT / 'logs' / 'watchdog-restart.json').write_text(json.dumps({
                'at': now, 'problems': restart_problems, 'verified': False,
            }))
            action = 'restart_requested'
    elif noted:
        action = 'degraded'
    ages['process_age_s'] = age
    if action == 'ok':
        status = 'ok'
    elif action == 'restarted':
        status = 'recovering'
    elif action in ('degraded', 'starting'):
        status = 'degraded'
    else:
        status = 'failed'
    body = {
        'at': now,
        'status': status,
        'problems': restart_problems,
        'noted': noted,
        'action': action,
        'ages': ages,
        'http_ok': http_ok,
        'read_error': read_error,
        'restarts_in_window': len(recent_attempts(now)),
        'launch_wait': launch_wait if launch_wait else None,
        'http_failures': http_failures,
        'restart_proof': proof,
        'note': 'A stale heartbeat, a stalled copier, or a publish that is late or missing restarts the service after the startup grace. A ledger mismatch holds buys and is not restarted. launchctl is recorded as requested until the next check sees progress.',
    }
    body['alert'] = notify(body)
    save_status(body)
    # The dashboard reads this from the database when the worker is up.
    # A dead worker cannot write it, so the page also watches response age.
    print(json.dumps(body))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
