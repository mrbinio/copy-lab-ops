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
QUALIFIER_OFF = ROOT / 'data' / 'QUALIFIER_OFF'
MITCH_OFF = ROOT / 'data' / 'MITCH_OFF'
MITCH_MANUAL = ROOT / 'data' / 'mitch_manual_pauses.json'
LIVE_STOP = ROOT / 'data' / 'LIVE_STOP'
WEEKLY_DAY = 6  # Sunday
WEEKLY_HOUR = 20
COMMANDS = [
    ('status', 'Czy wszystko działa'),
    ('mitch', 'Portfele Mitcha: wynik i pauzy'),
    ('kopie', 'Ostatnie decyzje kopiowania Mitcha z czasem'),
    ('portfele', 'Twoje portfele (kwalifikator): wynik, najlepsze i najgorsze'),
    ('pauzy', 'Kto jest na pauzie i dlaczego'),
    ('odkrywanie', 'Wyniki szukania portfeli metodą Mitcha (90 dni)'),
    ('rezerwa', 'Rezerwa zysku'),
    ('rynek', 'Cena BTC, ruch 24 h, najbliższe wydarzenia'),
    ('wydarzenia', 'Kalendarz makro'),
    ('system', 'Usługi na Macu, dysk, rejestrator'),
    ('audyt', 'Ostatni audyt dzienny i gotowość do LIVE'),
    ('proby', 'Próbna księga nowych portfeli (jak u Mitcha, 5 USD)'),
    ('kwalifikator_stop', 'Wstrzymaj kupno w Twoich portfelach'),
    ('kwalifikator_start', 'Włącz kupno w Twoich portfelach'),
    ('przeglad', 'Tygodniowy przegląd portfeli Mitcha'),
    ('mitch_pauza', 'Wstrzymaj jeden portfel Mitcha, np. /mitch_pauza dc27'),
    ('mitch_wznow', 'Wznów jeden portfel Mitcha, np. /mitch_wznow dc27'),
    ('mitch_stop', 'Wstrzymaj kupno Mitcha'),
    ('mitch_start', 'Włącz kupno Mitcha'),
    ('live', 'Prawdziwe pieniądze: saldo, w grze, ostatnie zlecenia'),
    ('live_stop', 'Wstrzymaj prawdziwe kupna od razu (papier działa)'),
    ('live_start', 'Wznów prawdziwe kupna'),
    ('stop', 'STOP: wszystkie nowe kupna'),
    ('wznow', 'Usuń STOP'),
    ('pomoc', 'Lista komend'),
]
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
WARN_BEFORE = (60,)  # 17 Oct 2026: one warning an hour ahead is enough
LABELS = {
    '0x16217458b59b3458149918058754cd234096b159': '096b159',
    '0xeda9247a2b3c99a9e0bf46cdac6e1974365cf589': '0x9f672c31',
    '0x943cea746e701823b6902a6f4eaeed58207e77c2': '0xdc27',
    '0x454c48b436e5dda7a186cc7e0ebeee2a1d1865cf': 'checkr3',
    '0xa82365c8e854728c472812fba6202ca125386215': 'mihaXd',
    '0x94f471f68396ff4a3cab8cb5c47c86274b8b77a2': 'izzyaussie',
    '0xbadb9af986ee66437bd39e6cd3d3036cbbdc31a7': '0xBadB9af',
    '0x2a989ed9be66328c6d80a60758eadff6f279ff22': '1Speed',
}
HELP = (
    'BTC Lab (PAPER). Komendy są też w menu „/” obok pola wiadomości.\n'
    '/status – worker, zegar, szybka ścieżka\n'
    '/mitch – 5 portfeli Mitcha, pauzy, wynik\n'
    '/portfele – kwalifikator dziś i łącznie\n'
    '/rezerwa – rezerwa zysku 40%\n'
    '/stop – STOP wszystkich nowych kupna (sprzedaż i rozliczenia działają)\n'
    '/wznow – usuń STOP\n'
    '/rynek – cena BTC, ruch 24 h i najbliższe wydarzenia makro\n'
    '/kopie – ostatnie decyzje kopiowania Mitcha\n'
    '/pauzy – kto stoi i dlaczego\n'
    '/odkrywanie – portfele metodą Mitcha (90 dni)\n'
    '/wydarzenia – kalendarz makro\n'
    '/system – usługi, dysk, rejestrator\n'
    '/audyt – ostatni audyt dzienny (codziennie 07:30) i gotowość do LIVE\n'
    '/proby – nowe portfele na próbie (5 USD na okno, osobna księga)\n'
    '/kwalifikator_stop, /kwalifikator_start – Twoje portfele\n'
    '/mitch_stop, /mitch_start – wszystkie portfele Mitcha\n'
    '/przeglad – tydzień każdego portfela Mitcha i co sprawdzić\n'
    '/mitch_pauza dc27 [powód], /mitch_wznow dc27 – jeden portfel (jak u Mitcha: decyzja człowieka)\n'
    '\nPrawdziwe pieniądze (tylko Mitch):\n'
    '/live – saldo portfela, w grze, strata dnia, ostatnie zlecenia\n'
    '/live_stop – natychmiast wstrzymaj prawdziwe kupna (papier i sprzedaże działają)\n'
    '/live_start – wznów prawdziwe kupna\n'
    '/stop zatrzymuje też prawdziwe kupna, /mitch_stop też.'
)


LIVE_STATUS_PL = {'DRY_SIGNED': 'test: podpisane', 'FILLED': 'wykonane', 'NOT_FILLED': 'niewykonane',
                  'SKIPPED_STOP': 'pominięte: STOP', 'SKIPPED_LIVE_STOP': 'pominięte: /live_stop',
                  'SKIPPED_EXPOSURE_CAP': 'pominięte: limit w grze', 'SKIPPED_DAY_LOSS_STOP': 'pominięte: limit dnia',
                  'SKIPPED_DESK_STOP': 'pominięte: stop biurka', 'SKIPPED_MIN_ABOVE_CAP': 'pominięte: minimum > limit', 'SKIPPED_MIN_TOO_BIG': 'pominięte: minimum > 2× papier/5',
                  'HELD_BELOW_MIN': 'trzymane do rozliczenia', 'SKIPPED_NOTHING_HELD': 'nic do sprzedania', 'ERROR': 'błąd'}


def live_text(state):
    live = state.get('mitch_live') or {}
    if not live.get('mode'):
        return 'Prawdziwe pieniądze: brak danych.'
    wallet = live.get('wallet') or {}
    limits = live.get('limits') or {}
    mode = {'live': 'LIVE (prawdziwe zlecenia)', 'dry': 'TEST (podpisuje, nic nie wysyła)', 'off': 'wyłączone'}.get(live['mode'], live['mode'])
    lines = ['Mitch · prawdziwe pieniądze: %s%s' % (mode, ' · WSTRZYMANE (/live_stop)' if LIVE_STOP.exists() else ''),
             'Portfel: %s pUSD · POL %s' % (wallet.get('pusd', '—'), wallet.get('pol', '—')),
             'W grze: %s z limitu %s USD · strata dnia %s z limitu %s USD' % (
                 live.get('exposure_usd', '0'), limits.get('max_exposure_usd', '—'),
                 live.get('day_loss_usd', '0'), limits.get('day_loss_stop_usd', '—'))]
    counts = live.get('counts') or {}
    if counts:
        lines.append('Zlecenia: ' + ', '.join('%s %d' % (LIVE_STATUS_PL.get(k, k), v) for k, v in counts.items()))
    recent = live.get('recent') or []
    if recent:
        lines.append('Ostatnie:')
        for r in recent[:5]:
            at = time.strftime('%H:%M', time.localtime(float(r.get('finished_at') or 0)))
            size = ('%s USD' % r['amount_usd']) if r.get('amount_usd') else ('%s udz.' % r.get('shares', '—'))
            took = r.get('from_source_ms')
            lines.append('%s %s %s · cena Mitcha %s · %s%s' % (
                at, 'kupno' if r.get('side') == 'BUY' else 'sprzedaż', size, r.get('source_price', '—'),
                LIVE_STATUS_PL.get(r.get('status'), r.get('status')),
                ' · %.2f s od Mitcha' % (took / 1000) if took is not None else ''))
    return '\n'.join(lines)


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
    if desk_line(mitch):
        lines.append(desk_line(mitch))
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
    desk = desk_line(state.get('mitch_copy') or {})
    if desk:
        return 'Rezerwa zysku (PAPER)\nRazem: %s USD\nMitch: %s (wszystko ponad 500 biurka + 40%% sprzed biurka)\nKwalifikator: %s (40%% z nowych szczytów)\n%s' % (
            usd(bank.get('reserved_micro')).lstrip('+'), usd(bank.get('mitch_reserved_micro')).lstrip('+'),
            usd(bank.get('copy_reserved_micro')).lstrip('+'), desk)
    return 'Rezerwa zysku (40%% z nowych zamkniętych plusów, PAPER)\nRazem: %s USD\nMitch: %s · kwalifikator: %s' % (
        usd(bank.get('reserved_micro')).lstrip('+'), usd(bank.get('mitch_reserved_micro')).lstrip('+'),
        usd(bank.get('copy_reserved_micro')).lstrip('+'))


REASONS_PL = {
    'MITCH_BUY': 'kupiono', 'MITCH_ADD': 'dokupiono', 'MITCH_SELL': 'sprzedano',
    'LATE_BUY_NOT_COPIED': 'za późno (>1 s)', 'PRICE_WORSE_THAN_10C': 'cena gorsza o >10¢',
    'MITCH_PAUSED': 'portfel na pauzie', 'GLOBAL_STOP': 'STOP', 'TECH_BRAKE': 'hamulec techniczny', 'WINDOW_LIMIT': 'limit okna',
    'NO_LIQUIDITY': 'brak płynności', 'NO_ASK': 'brak ofert', 'BOOK_WAIT_TOO_LONG': 'arkusz za wolno',
    'MITCH_NEED_CHAIN': 'brak jego ceny', 'SOURCE_TIME_UNKNOWN': 'nieznany czas', 'LATE_SELL_RECONCILED': 'spóźniona sprzedaż',
}


def copies_text(state):
    m = state.get('mitch_copy') or {}
    events = m.get('period_events') or []
    if not events:
        return 'Mitch: brak decyzji w okresie testu.'
    labels = {w.get('wallet'): w.get('label') for w in m.get('wallets') or []}
    reasons = m.get('period_reasons') or {}
    bought = reasons.get('MITCH_BUY', 0) + reasons.get('MITCH_ADD', 0)
    lines = ['Mitch, okres testu: %d kopii · za późno %d · pauza %d' % (
        bought, reasons.get('LATE_BUY_NOT_COPIED', 0), reasons.get('MITCH_PAUSED', 0)), 'Ostatnie:']
    for e in events[:10]:
        when = datetime.fromtimestamp(float(e['at']), STOCKHOLM).strftime('%d.%m %H:%M') if STOCKHOLM else ''
        ms = '' if e.get('total_ms') is None else ' · %d ms' % e['total_ms']
        lines.append('  %s %s %s: %s%s' % (when, labels.get(e.get('wallet')) or str(e.get('wallet'))[-6:],
                                          'kupno' if e.get('side') == 'BUY' else 'sprzedaż' if e.get('side') == 'SELL' else '',
                                          REASONS_PL.get(e.get('reason'), e.get('reason')), ms))
    return '\n'.join(lines)


def pauses_text(state):
    m = state.get('mitch_copy') or {}
    lines = ['Pauzy']
    if MITCH_OFF.exists():
        lines.append('Mitch: kupno wyłączone komendą (/mitch_start włącza).')
    for w in m.get('wallets') or []:
        if w.get('paused'):
            lines.append('  %s: %s' % (w.get('label'), w.get('pause_reason') or 'pauza'))
    if len(lines) == 1 or (len(lines) == 2 and MITCH_OFF.exists()):
        lines.append('  Mitch: żaden portfel nie stoi.')
    roster = ((state.get('wallet_roster') or {}).get('wallets') or {})
    counts = {}
    for row in roster.values():
        counts[row.get('state')] = counts.get(row.get('state'), 0) + 1
    lines.append('Twoje portfele: kupno %s · test %d · aktywne %d · pauza %d · obserwowane %d' % (
        'wyłączone' if QUALIFIER_OFF.exists() else 'włączone', counts.get('paper_test', 0),
        counts.get('paper_active', 0), counts.get('paused', 0), counts.get('observed', 0)))
    if PAUSE.exists():
        lines.append('STOP globalny jest aktywny (/wznow).')
    return '\n'.join(lines)


def wallets_detail_text(state):
    text = wallets_text(state)
    accounts = [a for a in state.get('accounts') or [] if str(a.get('id', '')).startswith('copy-') and a.get('trades')]
    if not accounts:
        return text
    accounts.sort(key=lambda a: float(a.get('pnl') or 0))
    fmt = lambda a: '  %s: %+.2f USD (%d transakcji)' % (str(a['id'])[-8:], float(a.get('pnl') or 0), int(a.get('trades') or 0))
    best = [fmt(a) for a in reversed(accounts[-5:])]
    worst = [fmt(a) for a in accounts[:5]]
    plus = sum(1 for a in accounts if float(a.get('pnl') or 0) > 0)
    return '\n'.join([text, 'Kupno: %s' % ('wyłączone' if QUALIFIER_OFF.exists() else 'włączone'),
                      'Na plusie %d z %d portfeli z transakcjami.' % (plus, len(accounts)),
                      'Najlepsze:'] + best + ['Najgorsze:'] + worst)


def events_text(now):
    upcoming = sorted((e for e in calendar_events() if float(e['at']) >= now - 3600), key=lambda e: e['at'])
    if not upcoming:
        return 'Kalendarz makro jest pusty.'
    lines = ['Kalendarz makro (czas sztokholmski)']
    for e in upcoming[:10]:
        lines.append('  %s  %s' % (datetime.fromtimestamp(float(e['at']), STOCKHOLM).strftime('%a %d.%m %H:%M'), e['name']))
    return '\n'.join(lines)


def system_text(state, code):
    import shutil
    rec = state.get('recorder_status') or {}
    free = shutil.disk_usage(str(ROOT)).free / 1e9
    tun = state.get('tunnel_status') or {}
    ch = state.get('chain_status') or {}
    return '\n'.join([
        status_text(state, code),
        'Łańcuch Polygon: %s' % ('połączony' if ch.get('connected') else 'brak'),
        'Tunel zdalny: %s' % ('połączony' if tun.get('edge_connected') else 'brak'),
        'Rejestrator: %s · %.2f GB' % ('zapisuje' if rec.get('ok') else 'problem: %s' % (rec.get('stale') or rec.get('paused')),
                                       (rec.get('bytes') or 0) / 1e9),
        'Wolne miejsce na dysku: %.0f GB' % free,
        'Kupno: Mitch %s · Twoje portfele %s%s' % (
            'wył.' if MITCH_OFF.exists() else 'wł.', 'wył.' if QUALIFIER_OFF.exists() else 'wł.',
            ' · STOP AKTYWNY' if PAUSE.exists() else ''),
    ])


def find_wallet(name):
    name = (name or '').lower().strip()
    if not name:
        return None
    hits = [w for w, short in LABELS.items()
            if name == short.lower() or name in short.lower() or w.startswith(name) or w.endswith(name)]
    return hits[0] if len(hits) == 1 else None


def manual_pause(name, why, chat, on):
    wallet = find_wallet(name)
    if wallet is None:
        return 'Nie znam portfela „%s”. Użyj: %s' % (name, ', '.join(LABELS.values()))
    body = load(MITCH_MANUAL, {'wallets': {}})
    wallets = body.setdefault('wallets', {})
    if on:
        wallets[wallet] = {'since': time.time(), 'reason': why or None, 'by': 'telegram %s' % chat}
        text = '%s: kupno wstrzymane ręcznie%s. Sprzedaż i rozliczenia działają. /mitch_wznow %s wznawia.' % (
            LABELS[wallet], ' (%s)' % why if why else '', LABELS[wallet])
    else:
        if wallets.pop(wallet, None) is None:
            return '%s nie był wstrzymany ręcznie.' % LABELS[wallet]
        text = '%s: kupno wraca (pauza ręczna zdjęta).' % LABELS[wallet]
    save(MITCH_MANUAL, body)
    return text


def review_text(state):
    m = state.get('mitch_copy') or {}
    lines = ['Przegląd tygodnia: Mitch (PAPER)',
             'Zasada Mitcha: brak automatycznej pauzy. Portfel odpada po przeglądzie, '
             'gdy przez tydzień traci na naszych kopiach, milczy od dni albo nowy skan pokazuje słaby wynik.']
    for w in m.get('wallets') or []:
        last = w.get('last_copy_at')
        when = datetime.fromtimestamp(float(last), STOCKHOLM).strftime('%d.%m %H:%M') if last and STOCKHOLM else 'brak'
        flags = w.get('review') or []
        lines.append('%s: tydzień %s na %s zamkn. · okres %s · ostatnia kopia %s%s%s' % (
            w.get('label') or label(w.get('wallet')),
            usd(int(round(float(w.get('week_net_usd') or 0) * 1e6))), w.get('week_closed') or 0,
            usd(w.get('period_net_micro')), when,
            ' · PAUZA' if w.get('paused') else '',
            ' · do sprawdzenia: ' + ', '.join(flags) if flags else ''))
    found = state.get('mitch_discovery') or {}
    weak = [r.get('label') or label(r.get('wallet')) for r in (found.get('rows') or [])
            if r.get('in_mitch_book') and r.get('market') == 'BTC 15m' and r.get('verdict') is False]
    if weak:
        lines.append('Skan 90 dni: słabe: ' + ', '.join(weak))
    if m.get('desk_cash_usd') is not None:
        lines.append('Gotówka biurka: %.2f USD (stop przy 50).' % float(m['desk_cash_usd']))
    lines.append('Decyzja należy do Ciebie: /mitch_pauza <nazwa> [powód] albo nic.')
    return '\n'.join(lines)


def trials_text(state):
    t = state.get('mitch_trials') or {}
    rows = t.get('wallets') or []
    if not rows:
        return 'Próby nowych portfeli: jeszcze brak (lista przychodzi z odkrywania o 12:15).'
    lines = ['Próby nowych portfeli (PAPER, 5 USD na okno, kopia w 1 s, osobna księga)']
    for r in rows:
        lines.append('%s%s: %s USD na %d rozliczonych (%d okien), 7 dni %s, w grze %.2f' % (
            r.get('label'), '' if r.get('active') else ' (poza listą)', '%+.2f' % r.get('pnl', 0),
            r.get('settled', 0), r.get('windows', 0), '%+.2f' % r.get('pnl_7d', 0), r.get('in_play', 0)))
    lines.append('Dodanie do Mitcha tylko Twoją decyzją.')
    return '\n'.join(lines)


def switch(path, on, chat, what):
    if on:
        if path.exists():
            path.unlink()
        return '%s: kupno WŁĄCZONE. Pauzy portfeli zostają, sprzedaż i rozliczenia działają zawsze.' % what
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('telegram %s %s\n' % (chat, now_local().isoformat()))
    return '%s: kupno WYŁĄCZONE. Otwarte pozycje dalej się sprzedają i rozliczają.' % what


def trade_text(event):
    detail = event.get('detail') or {}
    timing = detail.get('timing') or {}
    side = {'MITCH_BUY': 'KUPNO', 'MITCH_ADD': 'DOKUPIENIE', 'MITCH_SELL': 'SPRZEDAŻ'}.get(event.get('reason'), event.get('reason'))
    total = timing.get('total_ms')
    return 'Mitch %s (PAPER) · %s\n%s\nopóźnienie od jego transakcji: %s' % (
        side, label(event.get('wallet')), detail.get('market') or '',
        '%.0f ms' % total if total is not None else 'nieznane')


def window_text(w):
    """One finished window, in the shape of Mitch's own message."""
    try:
        start = int(str(w.get('market')).rsplit('-', 1)[-1])
        when = datetime.fromtimestamp(start, STOCKHOLM).strftime('%H:%M') if STOCKHOLM else str(start)
    except ValueError:
        when = '?'
    lines = ['15m okno %s, %s kupna (PAPER) · %s' % (when, w.get('fills'), ', '.join(w.get('wallets') or []))]
    sides = w.get('sides') or {}
    for side, r in sides.items():
        lines.append('%s: %s USD w, %.0f akcji, śr. %.0f¢' % (
            side, usd(r.get('in_micro')).lstrip('+'), (r.get('shares_micro') or 0) / 1e6, (r.get('avg') or 0) * 100))
    for side, r in sides.items():
        lines.append('Jeśli wygra %s: %s USD z powrotem (%s)' % (
            side, usd(r.get('if_wins_micro')).lstrip('+'), usd(r.get('if_wins_net_micro'))))
    if w.get('pnl_micro') is not None:
        lines.append('Wynik: %s %s USD' % ('WYGRANA' if w['pnl_micro'] > 0 else 'STRATA' if w['pnl_micro'] < 0 else 'zero',
                                           usd(w['pnl_micro'])))
    return '\n'.join(lines)


def desk_line(mitch):
    d = mitch.get('desk') or {}
    if not d:
        return None
    return 'Biurko: %s USD (linia 500) · w grze %s · stop przy 50: zapas %s · do rezerwy od startu biurka %s' % (
        usd(d.get('money_micro')).lstrip('+'), usd(d.get('in_play_micro')).lstrip('+'),
        usd(d.get('room_micro')).lstrip('+'), usd(d.get('swept_micro')).lstrip('+'))


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


BRAKE_ALERT_AFTER_S = 300
LIVE_ALARMS = {'ERROR': 'BŁĄD prawdziwego zlecenia', 'SKIPPED_DAY_LOSS_STOP': 'LIMIT STRATY DNIA osiągnięty: prawdziwe kupna stoją do jutra',
               'SKIPPED_DESK_STOP': 'STOP BIURKA: w portfelu za mało pieniędzy, prawdziwe kupna stoją'}


def alerts(state, memory, now=None):
    """Only what needs Damian now. Damian, 17 Oct 2026: too many messages; single
    PAPER trades, window reports, pause flips and discovery results are no
    longer sent (they are in the evening summary, the dashboard and the commands).
    Updates memory in place."""
    now = now or time.time()
    out = []
    found = state.get('mitch_discovery') or {}
    if found.get('finished_at'):
        memory['discovery_at'] = found.get('finished_at')
    mitch = state.get('mitch_copy') or {}
    seen = set(memory.get('seen') or [])
    first = not memory.get('primed')
    for event in mitch.get('recent') or []:
        if event.get('reason') not in TRADE_REASONS:
            continue
        seen.add('%s|%s|%s' % (event.get('at'), event.get('wallet'), event.get('reason')))
    paused = memory.get('paused') or {}
    for row in mitch.get('wallets') or []:
        paused[row.get('wallet')] = bool(row.get('paused'))
    # The brake is news only when it lasts: every restart has a 2-minute warm-up.
    brake = mitch.get('brake') or {}
    if brake.get('on'):
        since = memory.setdefault('brake_since', now)
        if now - since >= BRAKE_ALERT_AFTER_S and not memory.get('brake_alerted') and not first:
            out.append('HAMULEC TECHNICZNY od %d min: nowe kupna Mitcha wstrzymane — %s. Wracają same, gdy złapiemy '
                       'co najmniej 75%% jego kupna w 1 s.' % ((now - since) // 60, brake.get('reason') or '?'))
            memory['brake_alerted'] = True
    else:
        if memory.get('brake_alerted'):
            out.append('Hamulec techniczny zdjęty: kopiowanie Mitcha znowu działa.')
        memory.pop('brake_since', None)
        memory['brake_alerted'] = False
    live = state.get('mitch_live') or {}
    live_seen = set(memory.get('live_seen') or [])
    for row in live.get('recent') or []:
        key = str(row.get('id')) + '|' + str(row.get('status'))
        if row.get('status') in LIVE_ALARMS and key not in live_seen:
            live_seen.add(key)
            if not first:
                out.append('%s.%s' % (LIVE_ALARMS[row['status']], (' ' + str(row.get('error'))[:150]) if row.get('error') else ''))
    memory['live_seen'] = sorted(live_seen)[-300:]
    if state.get('live_enabled'):
        out.append('UWAGA: pulpit zgłasza live_enabled=true. Sprawdź natychmiast.')
    memory['paused'] = paused
    memory['seen'] = sorted(seen)[-800:]
    memory['primed'] = True
    return out


def handle(command, chat, tg, allowed, opener=urllib.request.urlopen):
    words = command.split() if command else []
    command = words[0].split('@')[0].lower() if words else ''
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
    if command == '/kwalifikator_stop':
        tg.send(chat, switch(QUALIFIER_OFF, False, chat, 'Twoje portfele'))
        return
    if command == '/kwalifikator_start':
        tg.send(chat, switch(QUALIFIER_OFF, True, chat, 'Twoje portfele'))
        return
    if command == '/live_stop':
        LIVE_STOP.parent.mkdir(parents=True, exist_ok=True)
        LIVE_STOP.write_text('telegram %s %s\n' % (chat, now_local().isoformat()))
        tg.send(chat, 'Prawdziwe pieniądze: kupno WSTRZYMANE od teraz. Papier działa dalej, otwarte pozycje dalej się '
                      'sprzedają i rozliczają. /live_start wznawia.')
        return
    if command == '/live_start':
        if LIVE_STOP.exists():
            LIVE_STOP.unlink()
        tg.send(chat, 'Prawdziwe pieniądze: kupno wraca (dalej obowiązują limity: w grze, strata dnia, stop biurka, /stop).')
        return
    if command == '/mitch_stop':
        tg.send(chat, switch(MITCH_OFF, False, chat, 'Mitch'))
        return
    if command == '/mitch_start':
        tg.send(chat, switch(MITCH_OFF, True, chat, 'Mitch'))
        return
    if command in ('/mitch_pauza', '/mitch_wznow', '/mitch_wznów'):
        if len(words) < 2:
            tg.send(chat, 'Podaj portfel, np. %s dc27. Portfele: %s' % (command, ', '.join(LABELS.values())))
        else:
            tg.send(chat, manual_pause(words[1], ' '.join(words[2:]), chat, command == '/mitch_pauza'))
        return
    if command == '/audyt':
        report = load(ROOT / 'logs' / 'daily-audit.json', {})
        tg.send(chat, report.get('text') or 'Audytu jeszcze nie było. Pierwszy jutro o 07:30.')
        return
    if command == '/wydarzenia':
        tg.send(chat, events_text(time.time()))
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
    elif command == '/live':
        tg.send(chat, live_text(state))
    elif command == '/portfele':
        tg.send(chat, wallets_detail_text(state))
    elif command == '/kopie':
        tg.send(chat, copies_text(state))
    elif command in ('/proby', '/próby'):
        tg.send(chat, trials_text(state))
    elif command in ('/przeglad', '/przegląd'):
        tg.send(chat, review_text(state))
    elif command == '/pauzy':
        tg.send(chat, pauses_text(state))
    elif command == '/odkrywanie':
        found = state.get('mitch_discovery') or {}
        tg.send(chat, discovery_text(found) if found.get('finished_at') else 'Odkrywanie metodą Mitcha jeszcze się liczy.')
    elif command == '/system':
        tg.send(chat, system_text(state, health(opener)))
    elif command == '/raport':
        try:
            day = get_json(BINANCE_DAY, opener)
        except Exception:
            day = None
        tg.send(chat, morning_text(state, day, time.time()))
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
            try:
                tg.call('setMyCommands', {'commands': json.dumps(
                    [{'command': c, 'description': d} for c, d in COMMANDS], ensure_ascii=False)}, timeout=15)
            except Exception as error:
                print('setMyCommands:', str(error)[:120], file=sys.stderr, flush=True)
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
                # 17 Oct 2026: BTC move alerts are no longer sent (/rynek shows them).
                today = now_local().date().isoformat()
                now_ts = time.time()
                messages.extend(calendar_alerts(memory, now_ts))
                if now_local().hour >= MORNING_HOUR and memory.get('morning') != today:
                    memory['morning'] = today
                    try:
                        day = get_json(BINANCE_DAY)
                    except Exception:
                        day = None
                    messages.append(morning_text(state, day, now_ts))
                week = '%d-%02d' % now_local().isocalendar()[:2]
                if (now_local().weekday() == WEEKLY_DAY and now_local().hour >= WEEKLY_HOUR
                        and memory.get('weekly') != week):
                    memory['weekly'] = week
                    messages.append(review_text(state))
                if now_local().hour >= DAILY_HOUR and memory.get('daily') != today:
                    memory['daily'] = today
                    messages.append('Podsumowanie dnia\n\n' + mitch_text(state) + '\n\n' + live_text(state) + '\n\n'
                                    + wallets_text(state) + '\n\n' + bank_text(state))
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
