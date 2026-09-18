"""Read-only authenticated dashboard API. Run behind HTTPS reverse proxy."""
import base64
import hashlib
import hmac
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from .core import Store
from .research import report

def handler(store, web, password_hash, username='damian', local_dev=False):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            # Do not log request headers or query strings.
            pass

        def send(self, code, body, content_type, extra=None):
            self.send_response(code)
            self.send_header('Content-Type',content_type)
            self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('X-Frame-Options','DENY')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            for k,v in (extra or {}).items(): self.send_header(k,v)
            self.end_headers()
            self.wfile.write(body)

        def authorized(self):
            if local_dev: return True
            try:
                scheme,encoded=self.headers.get('Authorization','').split(' ',1)
                if scheme!='Basic': return False
                user,password=base64.b64decode(encoded,validate=True).decode().split(':',1)
                return hmac.compare_digest(user,username) and hmac.compare_digest(hashlib.sha256(password.encode()).hexdigest(),password_hash)
            except (ValueError,UnicodeError): return False

        def do_GET(self):
            path=self.path.split('?',1)[0]
            if path=='/healthz':
                worker=store.get('worker',{})
                ok=time.time()-worker.get('heartbeat',0)<30 and worker.get('status') in ('RECORDING','PAUSED')
                self.send(200 if ok else 503,b'{"ok":true}' if ok else b'{"ok":false}','application/json')
                return
            if not self.authorized():
                self.send(401,b'Authentication required','text/plain',{'WWW-Authenticate':'Basic realm="BTC Lab", charset="UTF-8"'})
                return
            if path in ('/api/state','/api/report'):
                value=store.snapshot() if path=='/api/state' else report(store)
                self.send(200,json.dumps(value,allow_nan=False).encode(),'application/json')
                return
            allowed={'/':'index.html','/index.html':'index.html','/style.css':'style.css','/app.js':'app.js'}
            if path not in allowed:
                self.send(404,b'Not found','text/plain'); return
            target=web/allowed[path]
            kind={'html':'text/html; charset=utf-8','css':'text/css; charset=utf-8','js':'text/javascript; charset=utf-8'}[target.suffix[1:]]
            self.send(200,target.read_bytes(),kind)
    return Handler

def main():
    local=os.environ.get('LAB_LOCAL_DEV')=='1'
    digest=os.environ.get('LAB_PASSWORD_SHA256','')
    if not local and (len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest)):
        raise SystemExit('Set LAB_PASSWORD_SHA256. Production fails closed without authentication.')
    data=Path(os.environ.get('LAB_DATA','./runtime'))
    web=Path(os.environ.get('LAB_WEB',str(Path(__file__).resolve().parents[2]/'lab')))
    host='127.0.0.1' if local else os.environ.get('LAB_BIND','0.0.0.0')
    server=ThreadingHTTPServer((host,int(os.environ.get('LAB_PORT','8080'))),handler(Store(data/'lab.sqlite'),web,digest,os.environ.get('LAB_USERNAME','damian'),local))
    server.serve_forever()

if __name__=='__main__': main()
