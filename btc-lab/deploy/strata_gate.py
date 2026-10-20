"""Mr.Binio gate (20 Oct 2026): btc.damianbiniarz.com now shows the Strata desk.

The Cloudflare tunnel points at 127.0.0.1:<port from config.json> (8769, the old
BTC Lab dashboard). This gate keeps the same login (username and SHA-256 of the
password from config.json, Basic auth then a signed cookie) and passes every
request through to the Strata desk on 127.0.0.1:8900. The desk itself stays
bound to localhost, so its BUY/STOP buttons are never reachable without login.
"""
import base64
import hashlib
import hmac
import http.client
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path.home() / 'Library' / 'Application Support' / 'BTC Lab'
DESK = ('127.0.0.1', 8900)
PASS_HEADERS = ('Content-Type', 'Cache-Control', 'Content-Disposition')


def load():
    cfg = json.loads((ROOT / 'config.json').read_text())
    return int(cfg['port']), cfg['username'], cfg['password_sha256']


def make_handler(username, digest):
    class Gate(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, fmt, *args):
            pass

        def _session(self):
            for part in self.headers.get('Cookie', '').split(';'):
                item = part.strip()
                if not item.startswith('binio_sess='):
                    continue
                try:
                    user, exp, sig = item.split('=', 1)[1].split('|', 2)
                except ValueError:
                    return False
                want = hmac.new(digest.encode(), (user + '|' + exp).encode(), hashlib.sha256).hexdigest()
                return hmac.compare_digest(sig, want) and hmac.compare_digest(user, username) and int(exp) > time.time()
            return False

        def _basic(self):
            try:
                scheme, encoded = self.headers.get('Authorization', '').split(' ', 1)
                if scheme != 'Basic':
                    return False
                user, password = base64.b64decode(encoded, validate=True).decode().split(':', 1)
            except (ValueError, UnicodeError):
                return False
            return hmac.compare_digest(user, username) and \
                hmac.compare_digest(hashlib.sha256(password.encode()).hexdigest(), digest)

        def _cookie(self):
            exp = str(int(time.time()) + 7 * 24 * 3600)
            sig = hmac.new(digest.encode(), (username + '|' + exp).encode(), hashlib.sha256).hexdigest()
            return 'binio_sess=%s|%s|%s; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=604800' % (username, exp, sig)

        def _handle(self):
            fresh = False
            if not self._session():
                if not self._basic():
                    body = b'Login required'
                    self.send_response(401)
                    self.send_header('WWW-Authenticate', 'Basic realm="Mr.Binio", charset="UTF-8"')
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                fresh = True
            length = int(self.headers.get('Content-Length') or 0)
            data = self.rfile.read(length) if length else None
            conn = http.client.HTTPConnection(*DESK, timeout=20)
            try:
                headers = {'Content-Type': self.headers.get('Content-Type', 'application/json')} if data else {}
                conn.request(self.command, self.path, body=data, headers=headers)
                resp = conn.getresponse()
                body = resp.read()
                status = resp.status
                passed = [(k, v) for k, v in resp.getheaders() if k in PASS_HEADERS]
            except OSError:
                body, status, passed = b'Mr.Binio desk is not running', 502, [('Content-Type', 'text/plain')]
            finally:
                conn.close()
            self.send_response(status)
            for k, v in passed:
                self.send_header(k, v)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('X-Frame-Options', 'DENY')
            self.send_header('Referrer-Policy', 'no-referrer')
            if fresh:
                self.send_header('Set-Cookie', self._cookie())
            self.end_headers()
            self.wfile.write(body)

        do_GET = do_POST = _handle

    return Gate


def main():
    port, username, digest = load()
    if len(digest) != 64:
        sys.exit('config.json has no password hash; the gate fails closed.')
    ThreadingHTTPServer(('127.0.0.1', port), make_handler(username, digest)).serve_forever()


if __name__ == '__main__':
    main()
