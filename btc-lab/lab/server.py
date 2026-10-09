"""Read-only authenticated dashboard API. Run behind HTTPS reverse proxy."""
import base64
import hashlib
import hmac
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from .core import Store
from .daily_report import build_report
from .strategy_control import set_paused
from urllib.parse import parse_qs, urlsplit

_SNAP = {}
_SNAP_LOCK = threading.Lock()
_SNAP_TTL = 2.0
_SNAP_BUILDING = set()
_SNAP_READY = {}
_LOCAL_GET = ('/', '/index.html', '/app.js', '/style.css', '/api/state')


def request_path(raw):
    """Browsers behind a proxy send the absolute form, not '/'."""
    value = raw or '/'
    if value.startswith('http://') or value.startswith('https://'):
        value = urlsplit(value).path or '/'
    else:
        value = value.split('?', 1)[0] or '/'
    return value


def peer_host(client_address):
    host = (client_address or ['',])[0] or ''
    if host.startswith('::ffff:'):
        host = host[7:]
    return host


def is_loopback(client_address):
    host = peer_host(client_address)
    return host in ('127.0.0.1', '::1') or host.startswith('127.')

def _decorate(store, value):
    watch = Path(store.path).resolve().parent.parent / 'logs' / 'watchdog-status.json'
    try:
        value['service_watch'] = json.loads(watch.read_text()) if watch.exists() else value.get('service_watch') or {}
    except (OSError, ValueError):
        value['service_watch'] = {'status': 'unknown'}
    value['revision'] = os.environ.get('LAB_REVISION') or None
    value['view'] = 'live'
    value['dashboard_port'] = 8769
    return value

def dashboard_state(store):
    """Return a snapshot without making every poll rebuild it.

    The page asks every 2 seconds. A build that holds the lock, or a failure
    that raises, leaves the browser with no payload and the screen says
    there is no data. Waiters reuse the last finished snapshot.
    """
    key = store.asset
    with _SNAP_LOCK:
        now = time.time()
        hit = _SNAP.get(key)
        if hit and now - hit[0] < _SNAP_TTL:
            return hit[1]
        if key in _SNAP_BUILDING:
            ready = _SNAP_READY.get(key)
            cached = hit
        else:
            ready = threading.Event()
            _SNAP_READY[key] = ready
            _SNAP_BUILDING.add(key)
            cached = None
    if cached is not None or (ready is not None and key not in _SNAP_BUILDING):
        if ready is not None and not ready.is_set():
            ready.wait(8)
        with _SNAP_LOCK:
            hit = _SNAP.get(key)
        if hit:
            return hit[1]
        if cached is not None:
            return cached[1]
    try:
        value = _decorate(store, store.snapshot())
        cache = Path(store.path).resolve().parent.parent / 'logs' / ('dashboard-state-%s.json' % key)
        try:
            cache.write_text(json.dumps(value, allow_nan=False))
        except Exception:
            pass
    except Exception:
        with _SNAP_LOCK:
            hit = _SNAP.get(key)
            _SNAP_BUILDING.discard(key)
            ready = _SNAP_READY.pop(key, None)
        if ready is not None:
            ready.set()
        if hit:
            return hit[1]
        cache = Path(store.path).resolve().parent.parent / 'logs' / ('dashboard-state-%s.json' % key)
        try:
            return json.loads(cache.read_text())
        except Exception:
            raise
    with _SNAP_LOCK:
        _SNAP[key] = (time.time(), value)
        _SNAP_BUILDING.discard(key)
        ready = _SNAP_READY.pop(key, None)
    if ready is not None:
        ready.set()
    return value

def drop_dashboard_state(asset=None):
    with _SNAP_LOCK:
        if asset is None:
            _SNAP.clear()
        else:
            _SNAP.pop(asset, None)

def handler(store, web, password_hash, username='damian', local_dev=False, eth_store=None):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            # Do not log request headers or query strings.
            pass

        def session_ok(self):
            raw=self.headers.get('Cookie','')
            for part in raw.split(';'):
                item=part.strip()
                if not item.startswith('lab_sess='):
                    continue
                value=item.split('=',1)[1]
                try:
                    user,exp,sig=value.split('|',2)
                    payload=user+'|'+exp
                    expect=hmac.new(password_hash.encode(),payload.encode(),hashlib.sha256).hexdigest()
                    if not hmac.compare_digest(sig,expect):
                        return False
                    if not hmac.compare_digest(user,username):
                        return False
                    if int(exp)<time.time():
                        return False
                    return True
                except (ValueError,TypeError):
                    return False
            return False

        def issue_cookie(self):
            exp=str(int(time.time())+7*24*3600)
            payload=username+'|'+exp
            sig=hmac.new(password_hash.encode(),payload.encode(),hashlib.sha256).hexdigest()
            return 'lab_sess=%s|%s; Path=/; HttpOnly; SameSite=Lax; Max-Age=604800'%(payload,sig)

        def authorized(self):
            if local_dev: return True
            path=request_path(self.path)
            if self.command=='GET' and is_loopback(self.client_address) and path in _LOCAL_GET:
                return True
            if self.session_ok():
                return True
            try:
                scheme,encoded=self.headers.get('Authorization','').split(' ',1)
                if scheme!='Basic': return False
                user,password=base64.b64decode(encoded,validate=True).decode().split(':',1)
                ok=hmac.compare_digest(user,username) and hmac.compare_digest(hashlib.sha256(password.encode()).hexdigest(),password_hash)
                if ok:
                    self._authed_basic=True
                return ok
            except (ValueError,UnicodeError): return False

        def send(self, code, body, content_type, extra=None):
            extra=dict(extra or {})
            if code==200 and (getattr(self,'_authed_basic',False) or request_path(self.path) in ('/','/index.html')):
                extra.setdefault('Set-Cookie',self.issue_cookie())
            self.send_response(code)
            self.send_header('Content-Type',content_type)
            self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('X-Frame-Options','DENY')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            for k,v in extra.items(): self.send_header(k,v)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path=request_path(self.path)
            if path=='/healthz':
                worker=store.get('worker',{})
                ok=time.time()-worker.get('heartbeat',0)<30 and worker.get('status') in ('RECORDING','PAUSED')
                self.send(200 if ok else 503,b'{"ok":true}' if ok else b'{"ok":false}','application/json')
                return
            if not self.authorized():
                self.send(401,b'Authentication required','text/plain',{'WWW-Authenticate':'Basic realm="BTC Lab", charset="UTF-8"'})
                return
            if path in ('/api/state','/api/report'):
                try:
                    query=parse_qs(urlsplit(self.path).query)
                    asset=query.get('asset',['BTC'])[0]
                    if asset not in ('BTC','ETH'):raise ValueError('unsupported asset')
                    selected=eth_store if asset=='ETH' else store
                    if selected is None:
                        self.send(503,b'ETH worker not installed','text/plain');return
                    value=dashboard_state(selected) if path=='/api/state' else build_report(selected,query.get('date',[None])[0])
                except ValueError:
                    self.send(400,b'Invalid completed report date','text/plain'); return
                self.send(200,json.dumps(value,allow_nan=False).encode(),'application/json')
                return
            allowed={'/':'index.html','/index.html':'index.html','/style.css':'style.css','/app.js':'app.js'}
            if path not in allowed:
                self.send(404,b'Not found','text/plain'); return
            target=web/allowed[path]
            kind={'html':'text/html; charset=utf-8','css':'text/css; charset=utf-8','js':'text/javascript; charset=utf-8'}[target.suffix[1:]]
            self.send(200,target.read_bytes(),kind)

        def do_POST(self):
            path=request_path(self.path)
            if not self.authorized():
                self.send(401,b'Authentication required','text/plain',{'WWW-Authenticate':'Basic realm="BTC Lab", charset="UTF-8"'})
                return
            if path=='/api/trade':
                self.send(501,b'Live orders are disabled','text/plain');return
            if path!='/api/strategy-pause':
                self.send(404,b'Not found','text/plain');return
            try:
                length=int(self.headers.get('Content-Length') or 0)
                if length<=0 or length>2000:raise ValueError('body')
                payload=json.loads(self.rfile.read(length))
                strategy=str(payload.get('id',''))
                paused=payload.get('paused')
                if paused not in (True,False):raise ValueError('paused')
                asset=str(payload.get('asset','BTC'))
                selected=eth_store if asset=='ETH' else store
                if selected is None:raise ValueError('asset')
                value=set_paused(selected,strategy,paused)
                drop_dashboard_state(selected.asset)
            except (TypeError,ValueError,json.JSONDecodeError):
                self.send(400,b'Invalid strategy pause','text/plain');return
            self.send(200,json.dumps({'ok':True,'strategy_pauses':value},allow_nan=False).encode(),'application/json')
    return Handler

def main():
    local=os.environ.get('LAB_LOCAL_DEV')=='1'
    digest=os.environ.get('LAB_PASSWORD_SHA256','')
    if not local and (len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest)):
        raise SystemExit('Set LAB_PASSWORD_SHA256. Production fails closed without authentication.')
    data=Path(os.environ.get('LAB_DATA','./runtime'))
    web=Path(os.environ.get('LAB_WEB',str(Path(__file__).resolve().parents[2]/'lab')))
    host='127.0.0.1' if local else os.environ.get('LAB_BIND','0.0.0.0')
    server=ThreadingHTTPServer((host,int(os.environ.get('LAB_PORT','8080'))),handler(Store(data/'lab.sqlite'),web,digest,os.environ.get('LAB_USERNAME','damian'),local,eth_store=Store(data/'eth/lab.sqlite',asset='ETH')))
    server.serve_forever()

if __name__=='__main__': main()


