"""Independent hourly private reporting. No trading writes, no external dependencies."""
import base64
import datetime
import fcntl
import getpass
import json
import os
from pathlib import Path
import plistlib
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request

REPO='mrbinio/btc-lab-reports'
LABEL='com.btc-lab.reports'
ROOT=Path.home()/'Library/Application Support/BTC Lab'

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise RuntimeError('GitHub redirect refused')

def api(token,path,body=None):
    req=urllib.request.Request('https://api.github.com/repos/'+REPO+path,
        data=json.dumps(body).encode() if body is not None else None,
        method='PUT' if body is not None else 'GET',headers={
        'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json',
        'User-Agent':'BTC-Lab-Private-Reports','Content-Type':'application/json',
        'X-GitHub-Api-Version':'2022-11-28'})
    with urllib.request.build_opener(NoRedirect()).open(req,timeout=30) as response:
        return json.load(response)

def selected(value,keys):
    return {k:value[k] for k in keys.split() if k in value}

def snapshot(root):
    path=root/'data/lab.sqlite'
    db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=10)
    db.row_factory=sqlite3.Row
    try:
        db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
        def state(key):
            row=db.execute('SELECT body FROM state WHERE key=?',(key,)).fetchone()
            return json.loads(row[0]) if row else {}
        now=time.time()
        worker=selected(state('worker'),'status heartbeat reference_status version execution')
        model=selected(state('model'),'status samples required trained_at feature_schema model_id frozen_at validation_brier book_brier freeze_provenance')
        exit_fee='exit_fee' if any(r[1]=='exit_fee' for r in db.execute('PRAGMA table_info(positions)')) else '0'
        accounts=[]
        for a in db.execute('SELECT strategy,initial,cash FROM accounts'):
            p=db.execute(f'SELECT COUNT(*) n, SUM(payout IS NOT NULL) settled, SUM(payout-cost-fee-{exit_fee}>0) wins, COALESCE(SUM(CASE WHEN payout IS NOT NULL THEN payout-cost-fee-{exit_fee} ELSE 0 END),0) pnl, COALESCE(SUM(fee+{exit_fee}),0) fees, COALESCE(SUM(CASE WHEN status="OPEN" THEN cost+fee ELSE 0 END),0) open_cost, COALESCE(SUM(CASE WHEN status="RESOLVED" THEN payout ELSE 0 END),0) pending FROM positions WHERE strategy=?',(a['strategy'],)).fetchone()
            accounts.append({'id':a['strategy'],'cash':a['cash']/1e6,'initial':a['initial']/1e6,
                **{k:p[k]/1e6 for k in ('pnl','fees','open_cost','pending')},
                'trades':p['n'],'settled':p['settled'] or 0,'wins':p['wins'] or 0})
        trades=[dict(r) for r in db.execute(f'SELECT id,strategy,market,side,shares,cost,fee,{exit_fee} AS exit_fee,opened,status,payout,resolved FROM positions ORDER BY id DESC LIMIT 1000')]
        decisions=[dict(r) for r in db.execute('SELECT strategy,reason,COUNT(*) recorded_events FROM decisions WHERE ts>=? GROUP BY strategy,reason',(now-86400,))]
        counts={k:db.execute('SELECT COUNT(*) FROM '+v).fetchone()[0] for k,v in [('observations','observations'),('labels','labels'),('examples','examples'),('total_trades','positions')]}
        policies={}
        for row in db.execute('SELECT body FROM examples'):
            policy=json.loads(row[0]).get('sampling_policy','legacy')
            policies[policy]=policies.get(policy,0)+1
        market=selected(state('market'),'slug start end rule_kind rule_supported feature_schema opening')
        reference=selected(state('reference'),'source_ts received_at topic price')
        return {'schema':'btc-private-report-v1','source':'MAC_SQLITE_READ_ONLY','mode':'PAPER',
            'exported_at':datetime.datetime.fromtimestamp(now,datetime.timezone.utc).isoformat(),
            'generated_at':now,'worker':worker,'heartbeat_age_seconds':now-worker['heartbeat'] if worker.get('heartbeat') else None,
            'model':model,'accounts':accounts,'trades':trades,'trades_truncated':counts['total_trades']>len(trades),
            'exit_comparison':state('exit_comparison'),
            'exit_comparison_error':state('exit_comparison_error'),
            'trade_integer_scale':1000000,'counts':counts,'sampling_policies':policies,
            'recorded_decision_events_24h':decisions,'market':market,'reference':reference,
            'limitations':['Decision counts are throttled recorded events, not every evaluation.',
                'Export timestamp is not proof of a fresh worker. Inspect heartbeat age.',
                'No raw orderbook history; not sufficient for exit/latency replay.']}
    finally:db.close()

def publish(root,token):
    meta=api(token,'')
    if meta.get('private') is not True or meta.get('full_name')!=REPO:
        raise RuntimeError('Destination must be the expected PRIVATE repository')
    report=snapshot(root)
    raw=json.dumps(report,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
    if len(raw)>700000:raise RuntimeError('Report too large; nothing uploaded')
    body={'message':'Hourly BTC paper report','content':base64.b64encode(raw).decode(),'branch':meta['default_branch']}
    try:body['sha']=api(token,'/contents/latest.json?ref='+meta['default_branch'])['sha']
    except urllib.error.HTTPError as e:
        if e.code!=404:raise
    api(token,'/contents/latest.json',body)
    return report['exported_at']

def secure_write(path,text):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as f:f.write(text)
    path.chmod(0o600)

def install():
    if sys.platform!='darwin' or os.getuid()==0:raise RuntimeError('Uruchom na prywatnym Macu, bez sudo')
    config=json.loads((ROOT/'config.json').read_text())
    python=Path(config['release'])/'venv/bin/python'
    if not python.is_file():raise RuntimeError('Brak srodowiska BTC Lab')
    folder=ROOT/'reporting';folder.mkdir(mode=0o700,exist_ok=True);folder.chmod(0o700)
    token=getpass.getpass('Wklej token GitHub (niewidoczny) i nacisnij Enter: ').strip()
    if not token:raise RuntimeError('Pusty token')
    # Test actual read+write before registering any scheduled job.
    stamp=publish(ROOT,token)
    script=folder/'publish_report_macos.py'
    if Path(__file__).resolve()!=script.resolve():shutil.copyfile(__file__,script)
    script.chmod(0o600);secure_write(folder/'token',token)
    agent=Path.home()/'Library/LaunchAgents'/f'{LABEL}.plist';agent.parent.mkdir(parents=True,exist_ok=True)
    target=f'gui/{os.getuid()}/{LABEL}'
    subprocess.run(['launchctl','bootout',target],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    data={'Label':LABEL,'ProgramArguments':[str(python),str(script),'--send'],
          'StartInterval':3600,'RunAtLoad':True,'ProcessType':'Background'}
    agent.write_bytes(plistlib.dumps(data));agent.chmod(0o600)
    subprocess.run(['launchctl','enable',target],check=True)
    subprocess.run(['launchctl','bootstrap',f'gui/{os.getuid()}',str(agent)],check=True)
    print('RAPORT WYSLANY: '+stamp+'; AUTOMAT CO GODZINE WLACZONY',flush=True)
    print('Nie zmieniono uslugi BTC Lab, portu, hasla ani bazy danych.')

def main():
    os.umask(0o077)
    args=[a.replace('—','--').replace('–','--') for a in sys.argv[1:]]
    if args==['--install']:return install()
    if args!=['--send']:raise ValueError('Use --install or --send')
    folder=ROOT/'reporting'
    with (folder/'lock').open('w') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return
        try:
            stamp=publish(ROOT,(folder/'token').read_text().strip())
            status={'ok':True,'exported_at':stamp}
        except Exception as e:
            # Do not persist request headers, token, arbitrary responses or tracebacks.
            status={'ok':False,'attempted_at':time.time(),'error_type':type(e).__name__,
                    'http_status':e.code if isinstance(e,urllib.error.HTTPError) else None}
        secure_write(folder/'status.json',json.dumps(status))
        if not status['ok']:raise RuntimeError('Wysylka nieudana; sprawdz reporting/status.json')

if __name__=='__main__':
    try:main()
    except Exception as e:
        print('BLAD: '+type(e).__name__+((' HTTP '+str(e.code)) if isinstance(e,urllib.error.HTTPError) else '')+'. Instalacja lub wysylka niepotwierdzona.',file=sys.stderr)
        sys.exit(1)

