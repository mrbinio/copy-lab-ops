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

LABEL='com.btc-lab.paper'

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
    if config_path.exists():
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
    if not loaded:
        with socket.socket() as sock:
            try:sock.bind(('127.0.0.1',port))
            except OSError:raise SystemExit(f'Port {port} jest zajety. Niczego nie zatrzymano. Przeslij komunikat bledu.')
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
    if loaded:
        subprocess.run(['launchctl','bootout',target],check=True)
    config.update(release=str(release),revision=revision)
    config_path.write_text(json.dumps(config,indent=2));config_path.chmod(0o600)
    plist.write_bytes(plistlib.dumps(agent_definition(root,release)));plist.chmod(0o600)
    try:
        subprocess.run(['launchctl','bootstrap',f'gui/{os.getuid()}',str(plist)],check=True)
    except subprocess.CalledProcessError:
        if old_config:config_path.write_bytes(old_config)
        if old_plist:
            plist.write_bytes(old_plist)
            if loaded:subprocess.run(['launchctl','bootstrap',f'gui/{os.getuid()}',str(plist)],check=False)
        raise SystemExit('Nie udalo sie wlaczyc uslugi. Poprzednia konfiguracja zostala przywrocona, jesli istniala.')
    print('\nSkonfigurowano automatyczny start PO ZALOGOWANIU na to konto.')
    print(f'Dashboard na tym Macu: http://127.0.0.1:{port}')
    print('Login dashboardu: damian. Haslo: ustawione przez Ciebie przed chwila lub zachowane.')
    print('Nie jest to jeszcze potwierdzenie dzialania danych rynkowych. Sprawdz stan w dashboardzie.')
    print('Mac musi pozostac zalogowany i podlaczony do zasilania; ekran moze byc zablokowany.')
    print('Zdalny dostep spoza tego Maca wymaga osobnej konfiguracji prywatnego polaczenia.')
    print('Logi:',root/'logs/service.log')
    subprocess.run(['open',f'http://127.0.0.1:{port}'],check=False)

if __name__=='__main__':main()
