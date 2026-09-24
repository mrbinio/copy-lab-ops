"""User-owned launch agent installer; passwords are entered on the Mac only."""
import getpass
import hashlib
import json
import os
import plistlib
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from macos_launch import stop_service, start_service, wait_started, failure_report

LABEL='com.btc-lab.paper'

def choose_port(preferred):
    """Probe only; never stop another program. Prefer a stable nearby port."""
    for port in [p for p in range(preferred,preferred+21) if 1024<=p<=65535]+[0]:
        with socket.socket() as sock:
            try:
                sock.bind(('127.0.0.1',port))
            except OSError:
                continue
            return sock.getsockname()[1]
    raise SystemExit('Nie znaleziono wolnego portu lokalnego.')

def agent_definition(root, release):
    return {'Label':LABEL,'ProgramArguments':[str(release/'venv/bin/python'),str(release/'btc-lab/deploy/macos_service.py'),str(root)],
            'WorkingDirectory':str(release/'btc-lab'),'RunAtLoad':True,
            'KeepAlive':{'SuccessfulExit':False},'ThrottleInterval':60,
            'StandardOutPath':str(root/'logs/launch.stdout.log'),
            'StandardErrorPath':str(root/'logs/launch.stderr.log'),
            'EnvironmentVariables':{'PYTHONUNBUFFERED':'1','PYTHONDONTWRITEBYTECODE':'1'}}

def main():
    if sys.platform!='darwin' or os.getuid()==0:
        raise SystemExit('Use your normal macOS user account, without sudo.')
    source=Path(sys.argv[1]).resolve();revision=sys.argv[2]
    root=Path.home()/'Library/Application Support/BTC Lab'
    for part in ('','releases','data','logs'):
        (root/part).mkdir(parents=True,exist_ok=True,mode=0o700)
    config_path=root/'config.json'
    existing_install=config_path.exists()
    if existing_install:
        config=json.loads(config_path.read_text())
        print('Zachowuje dotychczasowe haslo i baze danych.')
    else:
        print('Ustaw NOWE haslo tylko do dashboardu (minimum 16 znakow).')
        print('To nie jest haslo do konta Mac, Apple ani Kraken.')
        while True:
            password=getpass.getpass('Haslo do dashboardu: ')
            repeated=getpass.getpass('Powtorz haslo: ')
            if len(password)>=16 and password==repeated:break
            print('Hasla musza byc takie same i miec minimum 16 znakow.')
        config={'username':'damian','password_sha256':hashlib.sha256(password.encode()).hexdigest(),'port':8765}
        del password,repeated
    port=int(config['port'])
    target=f'gui/{os.getuid()}/{LABEL}'
    loaded=subprocess.run(['launchctl','print',target],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
    if not loaded and not existing_install:
        selected=choose_port(port)
        if selected!=port:
            print(f'Port {port} jest zajety. BTC Lab uzyje wolnego portu {selected}.')
        port=selected
        config['port']=port
    # A fresh release per installation prevents an update overwriting a running venv.
    release=root/'releases'/f'{revision[:12]}-{time.time_ns()}'
    release.mkdir(mode=0o700)
    shutil.copytree(source/'btc-lab',release/'btc-lab',ignore=shutil.ignore_patterns('__pycache__','runtime','.env','.venv'))
    shutil.copytree(source/'lab',release/'lab')
    print('Tworze oddzielne srodowisko Pythona...')
    subprocess.run([sys.executable,'-m','venv',str(release/'venv')],check=True)
    python=str(release/'venv/bin/python')
    subprocess.run([python,'-m','pip','install','--disable-pip-version-check','-r',str(release/'btc-lab/requirements.txt')],check=True)
    subprocess.run([python,'-m','unittest','discover','-s','tests','-v'],cwd=release/'btc-lab',check=True)
    # Dependency installation and tests must succeed before stopping an old release.
    plist=Path.home()/'Library/LaunchAgents'/f'{LABEL}.plist'
    plist.parent.mkdir(parents=True,exist_ok=True)
    old_plist=plist.read_bytes() if plist.exists() else None
    old_config=config_path.read_bytes() if config_path.exists() else None
    try:
        stop_service(target,root)
    except Exception as error:
        failure_report(root,target)
        raise SystemExit(f'Nie zmieniono konfiguracji: {error}')
    # Preserve Cloudflare origin port on updates; never silently choose another.
    if existing_install:
        try:
            with socket.socket() as probe:
                probe.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
                probe.bind(('127.0.0.1',port))
        except OSError:
            if old_config and old_plist:
                start_service(target,plist)
            raise SystemExit(f'Port {port} nadal zajety. Zachowano stara konfiguracje; nie zmieniono portu tunelu.')
    else:
        port=choose_port(port)
    # Consistent backup before the new release performs additive migrations.
    import sqlite3
    db_path=root/'data/lab.sqlite'
    if db_path.exists():
        backup_dir=root/'backups';backup_dir.mkdir(mode=0o700,exist_ok=True)
        try:
            with sqlite3.connect(db_path) as src, sqlite3.connect(backup_dir/f'pre-{revision[:12]}-{time.time_ns()}.sqlite') as dst:
                src.backup(dst)
        except Exception:
            if old_config and old_plist:start_service(target,plist)
            raise
    config['port']=port
    config.update(release=str(release),revision=revision)
    config_path.write_text(json.dumps(config,indent=2));config_path.chmod(0o600)
    plist.write_bytes(plistlib.dumps(agent_definition(root,release)));plist.chmod(0o600)
    try:
        start_service(target,plist)
        print(wait_started(target,port),flush=True)
    except Exception as error:
        print(f'Nowa usluga nie wystartowala: {error}',flush=True)
        failure_report(root,target)
        try:
            stop_service(target,root)
            # Older releases do not know the new account name. Never run them
            # over an experiment ledger they cannot interpret.
            with sqlite3.connect(root/'data/lab.sqlite') as db:
                count=db.execute("SELECT COUNT(*) FROM positions WHERE strategy='mid-window-v1'").fetchone()[0]
                if count: raise RuntimeError('Zachowano nowa baze i konfiguracje: stara wersja nie obsluguje transakcji mid-window-v1. Wymagana naprawa nowej wersji, bez cofania danych.')
                db.execute("DELETE FROM accounts WHERE strategy='mid-window-v1' AND NOT EXISTS (SELECT 1 FROM ledger WHERE strategy='mid-window-v1')")
            if old_config:config_path.write_bytes(old_config)
            if old_plist:plist.write_bytes(old_plist)
            if old_config and old_plist:
                start_service(target,plist)
                print('Poprzednia wersja:',wait_started(target,int(json.loads(old_config)['port'])))
        except Exception as rollback_error:
            print(f'PRZYWROCENIE USLUGI NIEPOTWIERDZONE: {rollback_error}')
        raise SystemExit('Instalacja nieudana. Zachowano baze danych; szczegoly w raporcie powyzej.')
    # Refresh the already-installed hourly publisher without changing its token or schedule.
    reporter=root/'reporting/publish_report_macos.py'
    if reporter.exists():
        staged=reporter.with_suffix('.new')
        shutil.copyfile(release/'btc-lab/deploy/publish_report_macos.py',staged)
        staged.chmod(0o600);os.replace(staged,reporter)
    print('\nSkonfigurowano automatyczny start PO ZALOGOWANIU na to konto.')
    print(f'Dashboard na tym Macu: http://127.0.0.1:{port}')
    print('Login dashboardu: damian. Haslo: ustawione przez Ciebie przed chwila lub zachowane.')
    print('Nie jest to jeszcze potwierdzenie dzialania danych rynkowych. Sprawdz stan w dashboardzie.')
    print('Mac musi pozostac zalogowany i podlaczony do zasilania; ekran moze byc zablokowany.')
    print('Zdalny dostep spoza tego Maca wymaga osobnej konfiguracji prywatnego polaczenia.')
    print('Logi:',root/'logs/service.log')
    subprocess.run(['open',f'http://127.0.0.1:{port}'],check=False)
    print('\nSprawdzam dane rynku, oba orderbooki, RTDS i stan uslugi (do 90 sekund)...',flush=True)
    try:
        subprocess.run([python,str(release/'btc-lab/deploy/diagnose_macos.py')],timeout=90,check=False)
    except subprocess.TimeoutExpired:
        print('Diagnostyka przekroczyla 90 sekund; usluga pozostaje uruchomiona.')

if __name__=='__main__':main()

