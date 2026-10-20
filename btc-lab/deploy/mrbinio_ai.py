"""Mr.Binio AI: plain-text questions to the Telegram bot (Damian, 20 Oct 2026).

The desk's own bot answers fixed pings (status, today, emergency halt ...). Any
other message from Damian's chat comes here. Claude reads the desk's data and
answers in Polish. It may only READ and press STOP: it cannot buy, sell, change
rules or caps, move money, or resume after a stop.

Key: BTC Lab/secrets/anthropic.key (owner-only file). No key, no answer.
"""
import json
import sqlite3
import time
import urllib.request
from pathlib import Path

LAB = Path.home() / 'Library' / 'Application Support' / 'BTC Lab'
DESK = Path.home() / 'Projects' / 'Strata-Oktober-20'
API = 'http://127.0.0.1:8900'
MODEL = 'claude-sonnet-5-5'
LINE_USD = 250
KRAKEN = '0xcFf015f1C22bfFE66529d5F8967ADbeDf5E95396'

SYSTEM = """Jesteś Mr.Binio, asystentem Damiana na Telegramie. Pilnujesz jego programu, który kopiuje
zakłady portfeli Mitcha na rynku Polymarket „Bitcoin w górę czy w dół, 15 minut” za prawdziwe pieniądze.
Odpowiadaj po polsku, krótko i prosto, bez żargonu. Liczby bierz tylko z narzędzi; niczego nie zgaduj.
Zasady pieniędzy: wygrane zostają w portfelu do 250 USD, nadwyżka ponad 250 idzie automatycznie na Kraken
Damiana w porcjach od 5 USD. Do Mitcha nic nie idzie automatycznie (10% zysku Damian płaci sam).
Możesz TYLKO czytać dane i zatrzymać zakupy (halt_desk), i to tylko gdy Damian wyraźnie prosi o STOP lub pauzę.
Nie możesz kupować, sprzedawać, zmieniać limitów ani zasad, przelewać pieniędzy ani wznawiać po STOP:
wtedy powiedz, że to zrobi Claude w sesji na Macu."""

TOOLS = [
    {'name': 'desk_state', 'description': 'Stan programu teraz: tryb, saldo, wynik od startu, zakład w grze, '
     'połączenia, kopiowane portfele z limitami, ostatnie wpisy z czatu programu.',
     'input_schema': {'type': 'object', 'properties': {}}},
    {'name': 'windows', 'description': 'Okna 15-minutowe z ostatnich N godzin: czy był zakład, po której stronie, '
     'ile włożone i wynik.', 'input_schema': {'type': 'object', 'properties': {
         'hours': {'type': 'number', 'description': 'ile godzin wstecz, domyślnie 24'}}}},
    {'name': 'halt_desk', 'description': 'STOP: żadnych nowych zakupów, otwarte zakłady rozliczą się same. '
     'Tylko na wyraźną prośbę Damiana.', 'input_schema': {'type': 'object', 'properties': {}}},
]


def _get(path, timeout=8):
    return json.load(urllib.request.urlopen(API + path, timeout=timeout))


def desk_state(_args):
    s = _get('/api/state')
    cash = float(s.get('cash') or 0)
    return {
        'tryb': s.get('mode'), 'zatrzymany': s.get('halted'), 'saldo_usd': round(cash, 2),
        'wynik_od_startu_usd': round(float(s.get('pnl') or 0), 2),
        'brakuje_do_250_usd': round(max(0.0, LINE_USD - cash), 2),
        'zaklad_w_grze': s.get('open_position'), 'ostatnie_wykonanie': s.get('last_fill'),
        'gielda': {k: (s.get('clob') or {}).get(k) for k in ('ok', 'live', 'balance', 'rtt_ms')},
        'szybki_podglad_blockchaina': s.get('copy_chain'),
        'okna_od_startu': s.get('windows'),
        'czat': [c.get('text') for c in (s.get('chat') or [])[-12:]],
    }


def windows(args):
    hours = float((args or {}).get('hours') or 24)
    db = sqlite3.connect('file:%s?mode=ro' % (DESK / 'data' / 'live' / 'windows.sqlite'), uri=True, timeout=8)
    rows = db.execute('SELECT window_id, open_ts, edge_traded_side, filled_cost, pnl_paper, miss_code '
                      'FROM windows WHERE open_ts >= ? ORDER BY open_ts', (time.time() - hours * 3600,)).fetchall()
    out = []
    for wid, ts, side, cost, pnl, miss in rows:
        out.append({'okno': time.strftime('%d.%m %H:%M', time.localtime(float(ts or 0))),
                    'zaklad': bool(cost), 'strona': side, 'wlozone_usd': round(float(cost or 0), 2),
                    'wynik_usd': round(float(pnl or 0), 2) if cost else None, 'pominiete': miss})
    return {'okna': out, 'z_zakladem': sum(1 for o in out if o['zaklad']),
            'wynik_razem_usd': round(sum(o['wynik_usd'] or 0 for o in out), 2)}


def halt_desk(_args):
    req = urllib.request.Request(API + '/api/halt', data=b'', method='POST')
    return json.load(urllib.request.urlopen(req, timeout=8))


RUN = {'desk_state': desk_state, 'windows': windows, 'halt_desk': halt_desk}


def _claude(messages, key):
    body = json.dumps({'model': MODEL, 'max_tokens': 700, 'system': SYSTEM, 'tools': TOOLS,
                       'messages': messages}).encode()
    req = urllib.request.Request('https://api.anthropic.com/v1/messages', data=body, headers={
        'x-api-key': key, 'anthropic-version': '2023-06-01', 'content-type': 'application/json'})
    return json.load(urllib.request.urlopen(req, timeout=60))


def answer(text, call=_claude):
    """Polish reply to one plain-text message, or None without a key."""
    path = LAB / 'secrets' / 'anthropic.key'
    if not path.exists():
        return None
    key = path.read_text().strip()
    messages = [{'role': 'user', 'content': str(text)[:2000]}]
    for _ in range(4):
        reply = call(messages, key)
        content = reply.get('content') or []
        uses = [c for c in content if c.get('type') == 'tool_use']
        if not uses:
            return '\n'.join(c.get('text', '') for c in content if c.get('type') == 'text').strip() or None
        messages.append({'role': 'assistant', 'content': content})
        results = []
        for use in uses:
            try:
                out = RUN[use['name']](use.get('input') or {})
            except Exception as error:
                out = {'blad': str(error)[:200]}
            results.append({'type': 'tool_result', 'tool_use_id': use['id'],
                            'content': json.dumps(out, ensure_ascii=False, default=str)[:6000]})
        messages.append({'role': 'user', 'content': results})
    return 'Nie dałem rady odpowiedzieć, spróbuj prościej.'
