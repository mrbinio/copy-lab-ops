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


ALLOWED_HOSTS = ('clob.polymarket.com', 'data-api.polymarket.com', 'gamma-api.polymarket.com', 'bridge.polymarket.com',
                 'relayer-v2.polymarket.com', 'ws-live-data.polymarket.com', 'ws-subscriptions-clob.polymarket.com',
                 'polygon-bor-rpc.publicnode.com', 'polygon-bor.publicnode.com', 'polygon.drpc.org',
                 'rpc-mainnet.matic.quiknode.pro', 'api.binance.com', 'data.binance.vision', 'data-api.binance.vision', 'api.binance.us', 'api.telegram.org',
                 'www.coindesk.com', 'news.google.com', 'decrypt.co', 'cointelegraph.com')
# Cloudflare fronts Polymarket, publicnode and drpc; their addresses rotate inside these ranges.
CLOUDFLARE = ('104.16.', '104.17.', '104.18.', '104.19.', '104.20.', '104.21.', '104.22.', '104.23.', '104.24.',
              '104.25.', '104.26.', '104.27.', '172.64.', '172.65.', '172.66.', '172.67.', '172.68.', '172.69.',
              '172.70.', '172.71.', '162.158.', '162.159.', '108.162.', '141.101.', '188.114.', '190.93.', '197.234.', '198.41.')
CODE_GLOB = ('*.py', 'dashboard/*.html', 'wallet_targets*.json')


def strange_connections():
    """Remote addresses the desk talks to that are not on the known list."""
    import socket
    import subprocess
    pid = subprocess.run(['pgrep', '-f', 'Strata-live/run.py'], capture_output=True, text=True).stdout.split()
    if not pid:
        return []
    out = subprocess.run(['lsof', '-nP', '-a', '-p', pid[0], '-i'], capture_output=True, text=True).stdout
    known = set()
    for host in ALLOWED_HOSTS:
        try:
            known.update(a[4][0] for a in socket.getaddrinfo(host, 443))
        except OSError:
            pass
    odd = set()
    for line in out.splitlines()[1:]:
        if 'ESTABLISHED' not in line and 'CLOSE_WAIT' not in line and 'SYN_SENT' not in line:
            continue
        if '->' not in line:
            continue
        ip = line.split('->')[1].split()[0].rsplit(':', 1)[0].strip('[]')
        if ip.startswith(('127.', '::1')) or ip in known or ip.startswith(CLOUDFLARE):
            continue
        odd.add(ip)
    odd = {ip for ip in odd if not proves_allowed(ip)}
    named = []
    for ip in sorted(odd):
        try:
            named.append('%s (%s)' % (ip, socket.gethostbyaddr(ip)[0]))
        except OSError:
            named.append(ip)
    return named


def proves_allowed(ip):
    """Binance and others sit behind CloudFront and rotate addresses. An address
    is fine when it presents a valid TLS certificate for one of the allowed hosts."""
    import socket
    import ssl
    ctx = ssl.create_default_context()
    for host in ALLOWED_HOSTS:
        try:
            with socket.create_connection((ip, 443), timeout=4) as raw:
                with ctx.wrap_socket(raw, server_hostname=host):
                    return True
        except (OSError, ssl.SSLError):
            continue
    return False


def code_print():
    import hashlib
    files = {}
    for pattern in CODE_GLOB:
        for f in DESK.glob('**/' + pattern if pattern.startswith('*') else pattern):
            if '.venv' in f.parts or 'data' in f.parts:
                continue
            files[str(f.relative_to(DESK))] = hashlib.sha256(f.read_bytes()).hexdigest()
    return files


def code_changes(st):
    now = code_print()
    base = st.get('code')
    if not base:
        st['code'] = now
        return []
    return sorted(k for k in set(now) | set(base) if now.get(k) != base.get(k))


def check():
    st = load_state()
    now = time.time()
    found = problems()
    odd = strange_connections()
    if odd:
        found.append('NIEZNANE połączenie programu: ' + ', '.join(odd))
    changed = code_changes(st)
    if changed and st.get('code_alerted') != changed:
        tell('⚠️ Mr.Binio: zmienił się kod programu: ' + ', '.join(changed[:8]) + '. Jeśli to nie aktualizacja zrobiona przez Claude, napisz od razu.')
        st['code_alerted'] = changed
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


def shadow(since):
    """What the desk would have done since `since` with Mitch's sizing and our
    local caps: per window stake and result, from Polymarket's public trades and
    official winners. An estimate: it skips Mitch's price/book checks."""
    from collections import defaultdict
    targets = json.loads((DESK / 'wallet_targets.json').read_text())['wallets']
    try:
        local = json.loads((DESK / 'wallet_targets.local.json').read_text())
    except (OSError, ValueError):
        local = {}
    top = float(local.get('max_cap') or 30)
    caps = {t['name']: min(float(t.get('cap') or 30), top) for t in targets}
    buys = defaultdict(list)
    for t in targets:
        try:
            rows = get('https://data-api.polymarket.com/activity?user=%s&limit=500&type=TRADE' % t['wallet'], timeout=20)
        except Exception:
            continue
        for r in rows:
            slug = str(r.get('slug') or '')
            if r.get('side') == 'BUY' and slug.startswith('btc-updown-15m-') and float(r['timestamp']) >= since:
                buys[slug].append((float(r['timestamp']), t['name'], r.get('outcome'), float(r['price']), float(r['usdcSize'])))
        time.sleep(1.5)
    out = []
    for slug in sorted(buys):
        try:
            m = get('https://gamma-api.polymarket.com/markets/slug/' + slug, timeout=15)
        except Exception:
            continue
        if not m.get('closed'):
            continue
        prices = json.loads(m.get('outcomePrices') or '[]')
        names = json.loads(m.get('outcomes') or '[]')
        if '1' not in prices:
            continue
        winner = names[prices.index('1')]
        spent, pnl = defaultdict(float), 0.0
        for ts, name, side, px, usd in sorted(buys[slug]):
            stake = usd if usd <= 22.5 else 22.5 + 0.05 * (usd - 22.5)
            stake = min(stake, 30.0, caps.get(name, top) - spent[name])
            if stake < 1 or px <= 0:
                continue
            spent[name] += stake
            pnl += (stake / px if side == winner else 0) - stake - stake * 0.07 * (1 - px)
        if spent:
            out.append({'window': int(slug.rsplit('-', 1)[1]), 'stake': sum(spent.values()), 'pnl': pnl})
    return out


def shadow_text(since, label):
    rows = shadow(since)
    if not rows:
        return '%s: portfele Mitcha nie grały na BTC 15m.' % label
    won = sum(1 for r in rows if r['pnl'] > 0)
    total = sum(r['pnl'] for r in rows)
    last = ', '.join('%s %+.2f' % (time.strftime('%H:%M', time.localtime(r['window'])), r['pnl']) for r in rows[-6:])
    return 'RAZEM %s: %s%.2f USD (szacunek)\n%d okien z zakładem, %d wygranych\nOstatnie: %s' % (
        label, '+' if total >= 0 else '−', abs(total), len(rows), won, last)


def halt_since():
    try:
        return float((DESK / 'data' / 'live' / 'halt').read_text().split()[0])
    except (OSError, ValueError, IndexError):
        return None


def shadow_report():
    """Every 2 h while the desk is stopped: how it would have done."""
    since = halt_since()
    if since is None:
        return
    tell('⏸ Mr.Binio stoi od %s.\nGdybyśmy grali:\n%s' % (
        time.strftime('%d.%m %H:%M', time.localtime(since)),
        shadow_text(since, 'od zatrzymania')))


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
    stopped = halt_since()
    if stopped is not None:
        lines.append('⏸ Program stoi od %s. Gdybyśmy grali — %s' % (
            time.strftime('%d.%m %H:%M', time.localtime(stopped)), shadow_text(stopped, 'od zatrzymania')))
    tell('\n'.join(lines))


if __name__ == '__main__':
    {'check': check, 'audit': audit, 'shadow': shadow_report}[sys.argv[1] if len(sys.argv) > 1 else 'check']()
