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
        for key in ('worker', 'wallet_copy_execution', 'mitch_copy', 'clock_status', 'wallet_copy_health'):
            row = db.execute('SELECT body FROM state WHERE key=?', (key,)).fetchone()
            out[key] = json.loads(row[0]) if row else {}
        return out
    finally:
        db.close()


def assess(now, state, http_ok, launch_wait=None):
    """Split a dead process from a publish, a connection, and a bad book.

    Only a stale heartbeat restarts the service. A late journal, a refused
    HTTP check, or a ledger hold stays on the status line. Restarting would
    not repair those, and a launch-limit wait must not be kicked again.
    """
    worker = state.get('worker') or {}
    copy = state.get('wallet_copy_execution') or {}
    mitch = state.get('mitch_copy') or {}
    health = state.get('wallet_copy_health') or {}
    heartbeat = float(worker.get('heartbeat') or 0)
    copy_at = float(copy.get('updated_at') or 0)
    mitch_at = float(mitch.get('updated_at') or 0)
    restart_problems = []
    noted = []
    waiting = bool(launch_wait and float(launch_wait.get('retry_at') or 0) > now)
    if waiting:
        noted.append('launch_wait')
    elif now - heartbeat > HEARTBEAT_LIMIT:
        restart_problems.append('heartbeat')
    if copy_at and now - copy_at > PUBLISH_LIMIT:
        noted.append('copy_publish')
    if mitch_at and now - mitch_at > PUBLISH_LIMIT:
        noted.append('mitch_publish')
    if not http_ok:
        noted.append('connection')
    if health.get('status') == 'ledger_mismatch':
        noted.append('ledger_mismatch')
    return restart_problems, noted, {
        'heartbeat_age_s': None if not heartbeat else round(now - heartbeat, 1),
        'copy_publish_age_s': None if not copy_at else round(now - copy_at, 1),
        'mitch_publish_age_s': None if not mitch_at else round(now - mitch_at, 1),
    }


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
    restart_problems, noted, ages = assess(now, state, http_ok, launch_wait)
    age = process_age(now)
    action = 'ok'
    if restart_problems and age is not None and age < 180:
        action = 'starting'
    elif restart_problems:
        action = restart(now, ','.join(restart_problems))
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
        'note': 'Restart only when the heartbeat is stale. A late publish, a connection error, or a ledger hold is reported and left running. After five launches the wrapper waits out the ten-minute window and starts again.',
    }
    save_status(body)
    # The dashboard reads this from the database when the worker is up.
    # A dead worker cannot write it, so the page also watches response age.
    print(json.dumps(body))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
