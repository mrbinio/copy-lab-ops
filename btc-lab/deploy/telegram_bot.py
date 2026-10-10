#!/usr/bin/python3
"""Telegram for BTC Lab: alerts out, a few commands in. PAPER only.

It reads the dashboard state on loopback, like the browser does, so it keeps
working when the worker is stuck and can say so. The only thing it changes
is the PAUSE file: /stop stops every new buy (Mitch, wallets, strategies),
sells and settlement go on. /wznow removes it. It cannot place an order.

Setup: create a bot with @BotFather, put the token in
  ~/Library/Application Support/BTC Lab/telegram.json
  {"token": "123:ABC", "chat_ids": []}
then send /start to the bot. It answers with your chat id and nothing else.
Add that id to chat_ids. Only listed chats get data or commands.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
    STOCKHOLM = ZoneInfo('Europe/Stockholm')
except Exception:  # pragma: no cover
    STOCKHOLM = None

ROOT = Path(os.environ.get('BTC_LAB_ROOT', str(Path.home() / 'Library/Application Support/BTC Lab')))
CONFIG = ROOT / 'telegram.json'
STATE = ROOT / 'logs' / 'telegram-state.json'
PAUSE = ROOT / 'data' / 'PAUSE'
DASH = os.environ.get('BTC_LAB_DASH', 'http://127.0.0.1:8769')
CHECK_EVERY = 15
DOWN_AFTER = 120
DAILY_HOUR = 21
TRADE_REASONS = ('MITCH_BUY', 'MITCH_ADD', 'MITCH_SELL')
CALENDAR = ROOT / 'market_calendar.json'
MARKET_LOG = ROOT / 'logs' / 'market-events.jsonl'
BINANCE_PRICE = 'https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT'
BINANCE_DAY = 'https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT'
MOVE_5M = 1.0
MOVE_15M = 2.0
MOVE_COOLDOWN = 1800
MORNING_HOUR = 8
WARN_BEFORE = (60, 10)
LABELS = {
    '0x16217458b59b3458149918058754cd234096b159': '096b159',
    '0xeda9247a2b3c99a9e0bf46cdac6e1974365cf589': '0x9f672c31',
    '0x943cea746e701823b6902a6f4eaeed58207e77c2': '0xdc27',
    '0x454c48b436e5dda7a186cc7e0ebeee2a1d1865cf': 'checkr3',
    '0xa82365c8e854728c472812fba6202ca125386215': 'mihaXd',
}
HELP = (
    'BTC Lab (PAPER)\n'
    '/status – worker, zegar, szybka ścieżka\n'
    '/mitch – 5 portfeli Mitcha, pauzy, wynik\n'
    '/portfele – kwalifikator dziś i łącznie\n'
    '/rezerwa – rezerwa zysku 40%\n'
    '/stop – STOP wszystkich nowych kupna (sprzedaż i rozliczenia działają)\n'
    '/wznow – usuń STOP\n'
    '/rynek – cena BTC, ruch 24 h i najbliższe wydarzenia makro\n'
    'LIVE jest wyłączone w kodzie. Bot nie składa zleceń.'
)


def load(path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def save(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(body))
    os.replace(tmp, path)


def usd(micro):
    if micro is None:
        return '—'
    value = micro / 1e6
    return ('+' if value > 0 else '') + '%.2f' % value


def label(wallet):
    wallet = str(wallet or '').lower()
    return LABELS.get(wallet, wallet[-8:])


def now_local():
    return datetime.now(STOCKHOLM) if STOCKHOLM else datetime.now()


class Telegram:
    def __init__(self, token, opener=urllib.request.urlopen):
        self.base = 'https://api.telegram.org/bot%s/' % token
        self.opener = opener

    def call(self, method, params, timeout=35):
        data = urllib.parse.urlencode(params).encode()
        with self.opener(urllib.request.Request(self.base + method, data=data), timeout=timeout) as reply:
            body = json.loads(reply.read().decode())
        if not body.get('ok'):
            raise RuntimeError('telegram %s: %s' % (method, str(body)[:200]))
        return body.get('result')

    def send(self, chat, text):
        return self.call('sendMessage', {'chat_id': chat, 'text': text[:4000],
                                         'disable_web_page_preview': 'true'}, timeout=15)


def fetch_state(opener=urllib.request.urlopen):
    with opener(DASH + '/api/state?asset=BTC', timeout=10) as reply:
        return json.loads(reply.read().decode())


def health(opener=urllib.request.urlopen):
    try:
        with opener(DASH + '/healthz', timeout=5) as reply:
            return reply.status
    except urllib.error.HTTPError as error:
        return error.code
    except Exception:
        return None


def status_text(state, code):
    worker = state.get('worker') or {}
    clock = state.get('clock_status') or {}
    age = time.time() - float(worker.get('heartbeat') or 0)
    fast = (state.get('mitch_copy') or {}).get('fast') or {}
    lines = [
        'BTC Lab · %s' % ('STOP aktywny' if PAUSE.exists() else 'kupno włączone'),
        'Tryb: PAPER · LIVE: %s' % ('TAK' if state.get('live_enabled') else 'nie'),
        'Worker %s %s · heartbeat %.0f s · healthz %s' % (
            worker.get('version', '?'), worker.get('status', '?'), age, code),
        'Book %s · referencja %s' % (worker.get('book_status', '?'), worker.get('reference_status', '?')),
        'Zegar %s %s ms' % (clock.get('status', '?'), clock.get('offset_ms', '?')),
    ]
    if fast:
        lines.append('Szybka ścieżka: %s printów, %s odczytanych, %s chybionych, mediana %s ms, Mitch %s' % (
            fast.get('prints'), fast.get('resolved'), fast.get('missed'),
            fast.get('resolve_median_ms'), fast.get('watched')))
    return '\n'.join(lines)


def mitch_text(state):
    mitch = state.get('mitch_copy') or {}
    pauses = {}
    lines = ['Mitch (PAPER, tylko BTC 15m)',
             'Od startu: %s · dziś: %s · otwarte: %s' % (
                 usd(mitch.get('closed_all_micro')), usd(mitch.get('closed_today_micro')),
                 mitch.get('open_count'))]
    stint = mitch.get('stint') or {}
    if stint.get('at'):
        lines.append('Okres testu %s od %s' % (
            stint.get('id'), datetime.fromtimestamp(float(stint['at']), STOCKHOLM).strftime('%d.%m %H:%M')))
    for row in mitch.get('wallets') or []:
        pauses[row.get('wallet')] = row
        lines.append('%s: %s · kopii %s%s' % (
            row.get('label') or label(row.get('wallet')),
            'PAUZA' if row.get('paused') else 'aktywny',
            row.get('copies', 0),
            '' if row.get('net_micro') is None else ' · wynik ' + usd(row.get('net_micro'))))
    return '\n'.join(lines)


def wallets_text(state):
    board = ((state.get('wallet_copy_execution') or {}).get('board') or {}).get('periods') or {}
    lines = ['Portfele (kwalifikator, PAPER)']
    for name, title in (('today', 'Dziś'), ('week', 'Tydzień'), ('all', 'Łącznie')):
        period = board.get(name) or {}
        if period:
            lines.append('%s: %s na %s zamkniętych' % (title, usd(period.get('net_micro')), period.get('closed')))
    return '\n'.join(lines)


def bank_text(state):
    bank = state.get('profit_bank') or {}
    return 'Rezerwa zysku (40%% z nowych zamkniętych plusów, PAPER)\nRazem: %s USD\nMitch: %s · kwalifikator: %s' % (
        usd(bank.get('reserved_micro')).lstrip('+'), usd(bank.get('mitch_reserved_micro')).lstrip('+'),
        usd(bank.get('copy_reserved_micro')).lstrip('+'))


def trade_text(event):
    detail = event.get('detail') or {}
    timing = detail.get('timing') or {}
    side = {'MITCH_BUY': 'KUPNO', 'MITCH_ADD': 'DOKUPIENIE', 'MITCH_SELL': 'SPRZEDAŻ'}.get(event.get('reason'), event.get('reason'))
    total = timing.get('total_ms')
    return 'Mitch %s (PAPER) · %s\n%s\nopóźnienie od jego transakcji: %s' % (
        side, label(event.get('wallet')), detail.get('market') or '',
        '%.0f ms' % total if total is not None else 'nieznane')


def close_text(row):
    return 'Mitch zamknięcie (PAPER) · %s · %s\nwynik %s USD' % (
        label(row.get('wallet')), row.get('slug') or '', usd(row.get('pnl_micro')))


def log_market(kind, body):
    try:
        MARKET_LOG.parent.mkdir(parents=True, exist_ok=True)
        with MARKET_LOG.open('a') as handle:
            handle.write(json.dumps(dict(body, kind=kind, at=time.time())) + '\n')
    except OSError:
        pass


def get_json(url, opener=urllib.request.urlopen):
    with opener(urllib.request.Request(url, headers={'User-Agent': 'BTC-Lab-Bot/1.0'}), timeout=8) as reply:
        return json.loads(reply.read().decode())


def market_moves(memory, price, now):
    """Alert on a sharp BTC move. Keeps 20 minutes of prices in memory."""
    history = [p for p in memory.get('prices') or [] if now - p[0] <= 1200]
    history.append([now, price])
    memory['prices'] = history
    out = []
    for minutes, limit in ((5, MOVE_5M), (15, MOVE_15M)):
        past = [p for p in history if now - p[0] >= minutes * 60 - 30]
        if not past:
            continue
        ref = past[-1][1]
        change = (price - ref) / ref * 100
        key = 'move_%dm_at' % minutes
        if abs(change) >= limit and now - float(memory.get(key) or 0) >= MOVE_COOLDOWN:
            memory[key] = now
            direction = 'w górę' if change > 0 else 'w dół'
            out.append('RYNEK: BTC %+.2f%% w %d min (%s), teraz %.0f USD.\n'
                       'Krótkie rynki 5m/15m mogą się teraz gwałtownie przestawiać. '
                       'Jeśli chcesz wstrzymać nowe kupna: /stop' % (change, minutes, direction, price))
            log_market('move', {'minutes': minutes, 'change_pct': round(change, 3), 'price': price})
    return out


def calendar_events():
    data = load(CALENDAR, {})
    return [e for e in data.get('events') or [] if isinstance(e, dict) and e.get('at') and e.get('name')]


def calendar_alerts(memory, now):
    out = []
    sent = set(memory.get('calendar_sent') or [])
    for event in calendar_events():
        at = float(event['at'])
        for minutes in WARN_BEFORE:
            key = '%s|%d' % (event['name'], minutes)
            if key in sent:
                continue
            if 0 <= at - now <= minutes * 60:
                sent.add(key)
                when = datetime.fromtimestamp(at, STOCKHOLM).strftime('%H:%M') if STOCKHOLM else ''
                out.append('KALENDARZ: za %d min (%s) %s.\n%s' % (
                    max(1, int((at - now) // 60)), when, event['name'], event.get('note') or ''))
                if minutes == min(WARN_BEFORE):
                    log_market('macro', {'name': event['name'], 'event_at': at})
    memory['calendar_sent'] = sorted(sent)[-200:]
    return out


def morning_text(state, day, now):
    lines = ['Dzień dobry. Raport BTC Lab (PAPER)']
    if day:
        lines.append('BTC %.0f USD · 24 h %+.2f%% · zakres %.0f–%.0f' % (
            float(day['lastPrice']), float(day['priceChangePercent']), float(day['lowPrice']), float(day['highPrice'])))
    upcoming = [e for e in calendar_events() if 0 <= float(e['at']) - now <= 36 * 3600]
    if upcoming:
        lines.append('Najbliższe wydarzenia:')
        for e in sorted(upcoming, key=lambda e: e['at']):
            lines.append('  %s  %s' % (datetime.fromtimestamp(float(e['at']), STOCKHOLM).strftime('%a %H:%M'), e['name']))
    else:
        lines.append('Brak ważnych publikacji makro w ciągu 36 h.')
    lines.append('')
    lines.append(mitch_text(state))
    return '\n'.join(lines)


def discovery_text(d):
    lines = ['Odkrywanie metodą Mitcha (90 dni, kopia o 2 centy gorzej)']
    book = [r for r in d.get('rows') or [] if r.get('in_mitch_book')]
    if book:
        lines.append('Portfele Mitcha:')
        for r in book:
            lines.append('  %s %s: 90 dni %+.0f · 30 dni %+.0f · %s' % (
                r.get('label') or r['wallet'][-6:], r['market'], r.get('copy_90d') or 0, r.get('copy_30d') or 0,
                'KOPIOWAĆ' if r.get('verdict') else 'nie'))
    new = [p for p in d.get('passed') or [] if not p.get('in_mitch_book')]
    if new:
        lines.append('Nowi kandydaci (decyzja Twoja albo Mitcha):')
        for p in new[:8]:
            lines.append('  %s… %s: 90 dni %+.0f · 30 dni %+.0f · %d okien' % (
                p['wallet'][:8], p['market'], p['copy_90d'], p['copy_30d'], p['windows']))
    else:
        lines.append('Nowych kandydatów, którzy przeszli test, brak.')
    return '\n'.join(lines)


def alerts(state, memory):
    """New things worth a message. Updates memory in place."""
    out = []
    found = state.get('mitch_discovery') or {}
    if found.get('finished_at') and found.get('finished_at') != memory.get('discovery_at'):
        if memory.get('primed'):
            out.append(discovery_text(found))
        memory['discovery_at'] = found.get('finished_at')
    mitch = state.get('mitch_copy') or {}
    seen = set(memory.get('seen') or [])
    first = not memory.get('primed')
    for event in mitch.get('recent') or []:
        if event.get('reason') not in TRADE_REASONS:
            continue
        key = '%s|%s|%s' % (event.get('at'), event.get('wallet'), event.get('reason'))
        if key not in seen:
            seen.add(key)
            if not first:
                out.append(trade_text(event))
    for row in mitch.get('journal') or []:
        key = 'close|%s|%s|%s' % (row.get('at'), row.get('wallet'), row.get('slug'))
        if key not in seen:
            seen.add(key)
            if not first:
                out.append(close_text(row))
    paused = memory.get('paused') or {}
    for row in mitch.get('wallets') or []:
        wallet = row.get('wallet')
        now = bool(row.get('paused'))
        if wallet in paused and paused[wallet] != now and not first:
            out.append('Mitch %s: %s' % (row.get('label') or label(wallet),
                                         ('PAUZA. ' + (row.get('pause_reason') or 'minus w okresie testu')) if now else 'pauza zdjęta, kupno wraca'))
        paused[wallet] = now
    if state.get('live_enabled'):
        out.append('UWAGA: pulpit zgłasza live_enabled=true. Sprawdź natychmiast.')
    memory['paused'] = paused
    memory['seen'] = sorted(seen)[-800:]
    memory['primed'] = True
    return out


def handle(command, chat, tg, allowed, opener=urllib.request.urlopen):
    command = command.split()[0].split('@')[0].lower() if command else ''
    if chat not in allowed:
        if command == '/start':
            tg.send(chat, 'Twój chat id: %s\nDodaj go do telegram.json → chat_ids.' % chat)
        return
    if command in ('/start', '/pomoc', '/help'):
        tg.send(chat, HELP)
        return
    if command == '/stop':
        PAUSE.parent.mkdir(parents=True, exist_ok=True)
        PAUSE.write_text('telegram %s %s\n' % (chat, now_local().isoformat()))
        tg.send(chat, 'STOP: nowe kupna wstrzymane (Mitch, portfele, strategie). Sprzedaż i rozliczenia działają.')
        return
    if command in ('/wznow', '/wznów', '/resume'):
        if PAUSE.exists():
            PAUSE.unlink()
        tg.send(chat, 'STOP usunięty. Kupno wraca zgodnie z regułami (pauzy portfeli zostają).')
        return
    try:
        state = fetch_state(opener)
    except Exception as error:
        tg.send(chat, 'Pulpit nie odpowiada: %s' % str(error)[:200])
        return
    if command == '/status':
        tg.send(chat, status_text(state, health(opener)))
    elif command == '/mitch':
        tg.send(chat, mitch_text(state))
    elif command == '/portfele':
        tg.send(chat, wallets_text(state))
    elif command == '/rezerwa':
        tg.send(chat, bank_text(state))
    elif command == '/rynek':
        try:
            day = get_json(BINANCE_DAY, opener)
        except Exception:
            day = None
        tg.send(chat, morning_text(state, day, time.time()).replace('Dzień dobry. Raport BTC Lab (PAPER)', 'Rynek teraz'))
    else:
        tg.send(chat, HELP)


def main():
    memory = load(STATE, {})
    tg = None
    token = None
    last_check = 0
    while True:
        config = load(CONFIG, {})
        if not config.get('token'):
            time.sleep(60)
            continue
        if config['token'] != token:
            token = config['token']
            tg = Telegram(token)
        allowed = {int(c) for c in config.get('chat_ids') or []}
        try:
            updates = tg.call('getUpdates', {'offset': memory.get('offset', 0), 'timeout': 10}, timeout=20)
        except Exception as error:
            print('getUpdates:', str(error)[:200], file=sys.stderr, flush=True)
            time.sleep(5)
            updates = []
        for update in updates or []:
            memory['offset'] = update['update_id'] + 1
            message = update.get('message') or {}
            chat = (message.get('chat') or {}).get('id')
            if chat is None:
                continue
            try:
                handle(message.get('text') or '', int(chat), tg, allowed)
            except Exception as error:
                print('command:', str(error)[:200], file=sys.stderr, flush=True)
        if time.time() - last_check >= CHECK_EVERY and allowed:
            last_check = time.time()
            messages = []
            try:
                state = fetch_state()
                memory['last_ok'] = time.time()
                if memory.get('down_alerted'):
                    messages.append('Pulpit znowu odpowiada.')
                    memory['down_alerted'] = False
                worker = state.get('worker') or {}
                age = time.time() - float(worker.get('heartbeat') or 0)
                stale = age > DOWN_AFTER
                if stale and not memory.get('stale_alerted'):
                    messages.append('Heartbeat workera stoi %.0f s (status %s). Watchdog powinien go wznowić.' % (age, worker.get('status')))
                memory['stale_alerted'] = stale
                messages.extend(alerts(state, memory))
                today = now_local().date().isoformat()
                now_ts = time.time()
                try:
                    price = float(get_json(BINANCE_PRICE)['price'])
                    messages.extend(market_moves(memory, price, now_ts))
                except Exception as error:
                    print('binance:', str(error)[:120], file=sys.stderr, flush=True)
                messages.extend(calendar_alerts(memory, now_ts))
                if now_local().hour >= MORNING_HOUR and memory.get('morning') != today:
                    memory['morning'] = today
                    try:
                        day = get_json(BINANCE_DAY)
                    except Exception:
                        day = None
                    messages.append(morning_text(state, day, now_ts))
                if now_local().hour >= DAILY_HOUR and memory.get('daily') != today:
                    memory['daily'] = today
                    messages.append('Podsumowanie dnia\n\n' + mitch_text(state) + '\n\n' + wallets_text(state) + '\n\n' + bank_text(state))
            except Exception as error:
                if time.time() - float(memory.get('last_ok') or time.time()) > DOWN_AFTER and not memory.get('down_alerted'):
                    messages.append('Pulpit nie odpowiada od ponad %d s: %s' % (DOWN_AFTER, str(error)[:150]))
                    memory['down_alerted'] = True
            for text in messages:
                for chat in allowed:
                    try:
                        tg.send(chat, text)
                    except Exception as error:
                        print('send:', str(error)[:200], file=sys.stderr, flush=True)
        save(STATE, memory)


if __name__ == '__main__':
    main()
