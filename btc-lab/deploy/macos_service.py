"""launchd wrapper with bounded crash retries, rotating logs and idle-sleep prevention."""
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

def main():
    root=Path(sys.argv[1])
    config=json.loads((root/'config.json').read_text())
    attempts_path=root/'launch-attempts.json'
    now=time.time()
    attempts=json.loads(attempts_path.read_text()) if attempts_path.exists() else []
    attempts=[x for x in attempts if now-x<600]
    log=logging.getLogger('btc-lab-service');log.setLevel(logging.INFO)
    handler=RotatingFileHandler(root/'logs/service.log',maxBytes=2_000_000,backupCount=4)
    handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'));log.addHandler(handler)
    if len(attempts)>=5:
        log.error('Stopped after five launches in ten minutes. Operator review required.')
        return 0 # SuccessfulExit=False prevents launchd restarting this stopped state.
    attempts_path.write_text(json.dumps(attempts+[now]))
    env=os.environ.copy()
    env.pop('LAB_LOCAL_DEV',None)
    env.update(LAB_BIND='127.0.0.1',LAB_PORT=str(config['port']),LAB_DATA=str(root/'data'),
               LAB_WEB=str(Path(config['release'])/'lab'),LAB_USERNAME=config['username'],
               LAB_PASSWORD_SHA256=config['password_sha256'])
    stopping=False
    proc=None
    def stop(*args):
        nonlocal stopping
        stopping=True
        if proc is not None and proc.poll() is None:proc.terminate()
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    proc=subprocess.Popen([sys.executable,'-m','lab.supervisor'],cwd=Path(config['release'])/'btc-lab',
                          env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    awake=subprocess.Popen(['/usr/bin/caffeinate','-i','-w',str(proc.pid)])
    log.info('Starting paper-only service, release %s',config['revision'])
    try:
        for line in proc.stdout:log.info('%s',line.rstrip())
        code=proc.wait()
    finally:
        if proc.poll() is None:proc.terminate();proc.wait(timeout=30)
        if awake.poll() is None:awake.terminate();awake.wait(timeout=5)
    log.info('Service stopped, code=%s requested=%s',code,stopping)
    return 0 if stopping else (code or 1)

if __name__=='__main__':sys.exit(main())
