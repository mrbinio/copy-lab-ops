"""Mr.Binio watch and daily audit (Damian, 20 Oct 2026).

  check  (every 5 min): is the desk alive, not halted, live and on the chain feed?
         One Telegram alarm when something breaks, one note when it is back.
  audit  (07:30 daily): last 24 h in plain Polish: result, cash, source bets vs
         our copies, Kraken payouts, connection state.

Read-only: it reads the desk's local API and database and Polymarket's public
data. It never trades, stops or restarts anything.
"""
import json
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

LAB = Path.home() / 'Library' / 'Application Support' / 'BTC Lab'
DESK = Path.home() / 'Projects' / 'Strata-Oktober-20'
STATE = LAB / 'logs' / 'mrbinio-watch.json'
API = 'http://127.0.0.1:8900'
UA = {'User-Agent': 'MrBinio-watch/1.0'}
KRAKEN = '0xcFf015f1C22bfFE66529d5F8967ADbeDf5E95396'


def get(url, timeout=6):
    return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout))


def tell(text):
    cfg = json.loads((LAB / 'telegram.json').read_text())
    for chat in cfg.get('chat_ids') or []:
        data = urllib.parse.urlencode({'chat_id': chat, 'text': text}).encode()
        urllib.request.urlopen('https://api.telegram.org/bot%s/sendMessage' % cfg['token'], data=data, timeout=20)


def load_state():
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {}


def problems():
    """What is wrong right now, in Polish. Empty list = all good."""
    try:
        health = get(API + '/api/health')
        state = get(API + '/api/state', timeout=10)
    except Exception:
        return ['Mr.Binio nie odpowiada: program nie działa (zamknięte okno Terminala albo restart Maca?)']
    out = []
    if health.get('halted') or state.get('halted'):
        out.append('Mr.Binio jest ZATRZYMANY (STOP albo stop-loss): nowe zakupy stoją')
    if float(health.get('step_age_s') or 0) > 60:
        out.append('Mr.Binio się zawiesił: ostatni krok %.0f s temu' % float(health['step_age_s']))
    if state.get('mode') != 'live':
        out.append('Mr.Binio nie jest w trybie LIVE (tryb: %s)' % state.get('mode'))
    clob = state.get('clob') or {}
    if not clob.get('ok'):
        out.append('Mr.Binio nie jest zalogowany do giełdy: %s' % (clob.get('reason') or '?'))
    return out


def check():
    st = load_state()
    now = time.time()
    found = problems()
    # The chain feed may blink; alarm only when a problem lasts two checks in a row.
    if found:
        if st.get('seen') == found and not st.get('alerted'):
            tell('⚠️ Mr.Binio: ' + '; '.join(found))
            st['alerted'] = True
        st['seen'] = found
    else:
        if st.get('alerted'):
            tell('✅ Mr.Binio znowu działa normalnie.')
        st.update(seen=[], alerted=False)
    st['checked_at'] = now
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st))


def source_windows(since):
    """BTC 15m windows in which Mitch's wallets bought, from Polymarket's public data."""
    targets = json.loads((DESK / 'wallet_targets.json').read_text())['wallets']
    wins = {}
    for row in targets:
        try:
            trades = get('https://data-api.polymarket.com/activity?user=%s&limit=500&type=TRADE' % row['wallet'], timeout=20)
        except Exception:
            continue
        for t in trades:
            slug = str(t.get('slug') or '')
            if t.get('side') == 'BUY' and slug.startswith('btc-updown-15m-') and float(t['timestamp']) >= since:
                wins.setdefault(slug, set()).add(row['name'])
        time.sleep(1.5)
    return wins


def audit():
    since = time.time() - 86400
    lines = ['☀️ Mr.Binio — audyt dzienny (ostatnie 24 h)']
    found = problems()
    lines.append('Stan: ' + ('✅ wszystko działa' if not found else '❌ ' + '; '.join(found)))
    try:
        state = get(API + '/api/state', timeout=10)
        lines.append('Saldo: %.2f USD · wynik od startu %+.2f USD' % (float(state.get('cash') or 0), float(state.get('pnl') or 0)))
    except Exception:
        state = {}
    db = sqlite3.connect('file:%s?mode=ro' % (DESK / 'data' / 'live' / 'windows.sqlite'), uri=True, timeout=10)
    first = db.execute('SELECT MIN(open_ts) FROM windows').fetchone()[0]
    since = max(since, float(first or since))      # only the time the desk was running
    rows = db.execute('SELECT window_id, pnl_paper, filled_cost FROM windows WHERE open_ts >= ?', (since,)).fetchall()
    bets = [r for r in rows if r[2]]
    pnl = sum(float(r[1] or 0) for r in bets)
    won = sum(1 for r in bets if float(r[1] or 0) > 0)
    lines.append('Okna: %d · z zakładem %d · wygrane %d · wynik %+.2f USD' % (len(rows), len(bets), won, pnl))
    src = source_windows(since)
    ours = {r[0] for r in bets}
    missed = sorted(set(src) - ours)
    lines.append('Źródło grało w %d oknach, my mieliśmy zakład w %d' % (len(src), len(ours & set(src))))
    if missed:
        lines.append('Bez naszej kopii: ' + ', '.join(time.strftime('%H:%M', time.localtime(int(s.rsplit('-', 1)[1]))) for s in missed[:10]))
    floor = db.execute("SELECT v FROM meta WHERE k='exodus_floor'").fetchone()
    lines.append('Kraken: linia %s USD, nadwyżka idzie na %s…%s' % (floor[0] if floor else '?', KRAKEN[:6], KRAKEN[-4:]))
    lines.append('Szybki podgląd blockchaina: %s' % ('✅' if state.get('copy_chain') else '❌ (wolniejsza droga zapasowa)'))
    tell('\n'.join(lines))


if __name__ == '__main__':
    {'check': check, 'audit': audit}[sys.argv[1] if len(sys.argv) > 1 else 'check']()
