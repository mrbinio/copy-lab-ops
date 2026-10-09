#!/usr/bin/python3
"""Watch the existing Cloudflare tunnel, not the paper copier.

A live cloudflared process is not a connection. This asks the public
hostname and treats Error 1033 as a lost tunnel. It restarts only
com.cloudflare.cloudflared, and only when the Mac's network is up.
Sleep, a dead copier, and a missing password are not reasons to restart.
"""
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(os.environ.get(
    'BTC_LAB_ROOT',
    str(Path.home() / 'Library/Application Support/BTC Lab'),
))
TUNNEL_LABEL = 'system/com.cloudflare.cloudflared'
HOST = os.environ.get('BTC_LAB_TUNNEL_HOST', 'btc.damianbiniarz.com')
ATTEMPTS = ROOT / 'logs' / 'tunnel-watch-attempts.json'
STATUS = ROOT / 'logs' / 'tunnel-watch-status.json'
MAX_RESTARTS = 3
WINDOW = 1800
MIN_GAP = 600
STREAK_TO_RESTART = 2


def load(path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def network_up():
    """A default route. This is down while the interface itself is down."""
    try:
        proc = subprocess.run(
            ['/sbin/route', '-n', 'get', '1.1.1.1'],
            capture_output=True, text=True, timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if proc.returncode != 0:
        return False
    for line in proc.stdout.splitlines():
        if line.strip().startswith('interface:'):
            return bool(line.split(':', 1)[1].strip())
    return False


def probe_edge(host=HOST, timeout=8):
    """Return (http_status or None, body). Redirects are not followed.

    A 302 from Cloudflare Access means the tunnel carried the request.
    It does not mean the application behind the login answered.
    """
    class _Keep(urllib.request.HTTPErrorProcessor):
        def http_response(self, request, response):
            return response

        https_response = http_response

    url = 'https://%s/healthz' % host
    opener = urllib.request.build_opener(_Keep)
    request = urllib.request.Request(url, headers={'User-Agent': 'BTC-Lab-TunnelWatch/1'})
    try:
        with opener.open(request, timeout=timeout) as response:
            body = response.read(4000)
            return response.status, body
    except urllib.error.HTTPError as error:
        body = error.read(4000) if error.fp else b''
        return error.code, body
    except Exception:
        return None, b''


def edge_connected(status, body):
    text = body or b''
    if b'1033' in text or b'Cloudflare Tunnel error' in text:
        return False
    return status in (200, 301, 302, 303, 307, 308, 401, 403)


def decide(now, network, connected, streak, attempts):
    """What to do with the existing tunnel. Never a copier restart."""
    if not network:
        return 'none', 0, 'network_down'
    if connected:
        return 'none', 0, 'tunnel_connected'
    streak += 1
    recent = [float(item) for item in attempts if now - float(item) < WINDOW]
    if len(recent) >= MAX_RESTARTS or (recent and now - max(recent) < MIN_GAP):
        return 'restart_limited', streak, 'rate_limit'
    if streak < STREAK_TO_RESTART:
        return 'none', streak, 'failure_pending'
    return 'restart', 0, 'tunnel_down'


def restart_tunnel(now, attempts):
    recent = [float(item) for item in attempts if now - float(item) < WINDOW]
    ATTEMPTS.parent.mkdir(parents=True, exist_ok=True)
    ATTEMPTS.write_text(json.dumps(recent + [now]))
    proc = subprocess.run(
        ['/bin/launchctl', 'kickstart', '-k', TUNNEL_LABEL],
        capture_output=True, text=True, timeout=30,
    )
    detail = (proc.stderr or proc.stdout or '').strip()[:300]
    return proc.returncode, detail


def main():
    now = time.time()
    up = network_up()
    status, body = (None, b'')
    if up:
        status, body = probe_edge()
    connected = edge_connected(status, body) if up else False
    previous = load(STATUS, {})
    streak = int(previous.get('failure_streak') or 0)
    attempts = load(ATTEMPTS, [])
    action, streak, reason = decide(now, up, connected, streak, attempts)
    detail = ''
    if action == 'restart':
        code, detail = restart_tunnel(now, attempts)
        if code != 0:
            reason = 'restart_failed'
            action = 'restart_failed'
    report = {
        'at': now,
        'network_up': up,
        'http_status': status,
        'edge_connected': bool(connected) if up else False,
        'origin_confirmed': False,
        'failure_streak': streak,
        'action': action,
        'reason': reason,
        'detail': detail,
        'note': (
            'edge_connected means Cloudflare answered for this hostname, '
            'including an Access login redirect. It does not prove the '
            'application behind that login. This job does not restart the copier.'
        ),
    }
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(json.dumps(report))
    print(json.dumps(report))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
