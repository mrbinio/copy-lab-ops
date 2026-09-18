"""Bounded launchd lifecycle and standalone recovery for the existing installation."""
import fcntl
import json
import os
from pathlib import Path
import plistlib
import re
import subprocess
import sys
import time
import urllib.request
import urllib.error

LABEL='com.btc-lab.paper'

def command(*args):
    return subprocess.run(list(args),capture_output=True,text=True,timeout=10)

def registered(target):
    return command('/bin/launchctl','print',target).returncode==0

def stop_service(target,root):
    if registered(target):
        result=command('/bin/launchctl','bootout',target)
        if result.returncode:
            raise RuntimeError('bootout: '+result.stderr.strip())
    deadline=time.monotonic()+30
    while registered(target):
        if time.monotonic()>deadline:raise RuntimeError('Poprzednia usluga nie zostala usunieta przez launchd w ciagu 30 s.')
        time.sleep(.5)
    # launchd registration can disappear before the old worker releases its lock.
    with (root/'data/worker.lock').open('a') as lock:
        while True:
            try:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic()>deadline:raise RuntimeError('Stary kolektor nadal dziala; nie uruchamiam drugiego.')
                time.sleep(.5)

def start_service(target,plist):
    lint=command('/usr/bin/plutil','-lint',str(plist))
    if lint.returncode:raise RuntimeError('Niepoprawny plist: '+lint.stdout+lint.stderr)
    enable=command('/bin/launchctl','enable',target)
    if enable.returncode:raise RuntimeError('enable: '+enable.stderr.strip())
    result=None
    for attempt in range(3):
        result=command('/bin/launchctl','bootstrap',target.rsplit('/',1)[0],str(plist))
        if result.returncode==0:return
        if registered(target):return
        if attempt<2:time.sleep(2)
    raise RuntimeError('bootstrap: '+result.stderr.strip())

def wait_started(target,port):
    deadline=time.monotonic()+20
    while time.monotonic()<deadline:
        status=command('/bin/launchctl','print',target)
        pid=re.search(r'^\s*pid = (\d+)',status.stdout,re.M)
        if pid:
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/healthz',timeout=1) as response:
                    if response.status==200:return 'DASHBOARD OK; /healthz=200'
            except urllib.error.HTTPError as error:
                if error.code==503:return 'DASHBOARD OK; /healthz=503 — dane wymagaja diagnostyki'
            except OSError:pass
        time.sleep(.5)
    raise RuntimeError('Brak potwierdzenia startu procesu i HTTP w ciagu 20 s.')

def failure_report(root,target):
    print('BEGIN STARTUP REPORT',flush=True)
    for args in [('/bin/launchctl','print',target),('/usr/bin/log','show','--last','2m','--style','compact','--predicate',f'process == "launchd" AND eventMessage CONTAINS "{LABEL}"')]:
        try:
            r=command(*args)
            if args[1]=='print':
                # Never print environment/configuration values.
                lines=[s for s in r.stdout.splitlines() if re.match(r'\s*(state|pid|last exit code|program|path) =',s)]
                print('\n'.join(lines) or r.stderr.strip())
            else:print((r.stdout+r.stderr)[-6000:])
        except Exception as error:print(type(error).__name__,str(error))
    for name in ('launch.stderr.log','service.log'):
        path=root/'logs'/name
        if path.exists():
            with path.open('rb') as file:
                file.seek(max(0,path.stat().st_size-6000))
                print(name+':\n'+'\n'.join(file.read().decode(errors='replace').splitlines()[-15:]))
    print('END STARTUP REPORT',flush=True)

def main():
    if sys.platform!='darwin' or os.getuid()==0:raise SystemExit('Uruchom na Macu, bez sudo.')
    root=Path.home()/'Library/Application Support/BTC Lab'
    config=json.loads((root/'config.json').read_text())
    release=Path(config['release'])
    # Reuse the existing release; no package install and no data/password changes.
    sys.path.insert(0,str(release/'btc-lab/deploy'))
    from setup_macos import agent_definition
    plist=Path.home()/'Library/LaunchAgents'/f'{LABEL}.plist'
    target=f'gui/{os.getuid()}/{LABEL}'
    print('Naprawiam uruchamianie istniejacej instalacji BTC Lab...',flush=True)
    try:
        if command('/bin/launchctl','print',f'gui/{os.getuid()}').returncode:
            raise RuntimeError('Brak sesji graficznej tego uzytkownika. Uruchom Terminal z pulpitu Maca.')
        if not (release/'venv/bin/python').exists():raise RuntimeError('Brakuje Pythona zapisanej wersji.')
        if plist.exists():
            backup=plist.with_name(plist.name+'.backup-'+str(time.time_ns()))
            backup.write_bytes(plist.read_bytes());backup.chmod(0o600)
        stop_service(target,root)
        plist.write_bytes(plistlib.dumps(agent_definition(root,release)));plist.chmod(0o600)
        start_service(target,plist)
        print(wait_started(target,int(config['port'])),flush=True)
        print(f"Dashboard: http://127.0.0.1:{config['port']} — login: {config['username']}",flush=True)
        subprocess.run(['/usr/bin/open',f"http://127.0.0.1:{config['port']}"],check=False)
        doctor=release/'btc-lab/deploy/diagnose_macos.py'
        if doctor.exists():
            subprocess.run([str(release/'venv/bin/python'),str(doctor)],timeout=90,check=False)
        else:failure_report(root,target)
    except Exception as error:
        print('START NIEPOTWIERDZONY:',str(error),flush=True)
        failure_report(root,target)
        return 1
    return 0

if __name__=='__main__':sys.exit(main())
