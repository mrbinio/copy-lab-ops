#!/usr/bin/python3
"""Connect the BTC Lab Telegram bot in one step.

Run:  python3 "$HOME/Library/Application Support/BTC Lab/setup_telegram.py"
Paste the token from @BotFather, then send /start to your bot.
The token is not shown on screen and is stored with owner-only access.
"""
import getpass
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(os.environ.get('BTC_LAB_ROOT', str(Path.home() / 'Library/Application Support/BTC Lab')))
CONFIG = ROOT / 'telegram.json'
WAIT = 300


def call(token, method, **params):
    data = urllib.parse.urlencode(params).encode()
    url = 'https://api.telegram.org/bot%s/%s' % (token, method)
    with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=40) as reply:
        body = json.loads(reply.read().decode())
    if not body.get('ok'):
        raise RuntimeError(body.get('description') or 'Telegram error')
    return body['result']


def main():
    print('BTC Lab · połączenie z Telegramem\n')
    token = getpass.getpass('Wklej token od @BotFather (nie będzie widoczny) i naciśnij Enter: ').strip()
    try:
        me = call(token, 'getMe')
    except Exception as error:
        print('\nTen token nie działa: %s\nSprawdź, czy skopiowałeś go w całości.' % error)
        return 1
    name = me.get('username')
    print('\nToken OK. Twój bot: @%s' % name)
    print('Teraz w Telegramie otwórz https://t.me/%s i naciśnij START (albo napisz /start).' % name)
    print('Czekam do %d minut...' % (WAIT // 60))
    offset = 0
    chat = None
    deadline = time.time() + WAIT
    while time.time() < deadline and chat is None:
        try:
            updates = call(token, 'getUpdates', offset=offset, timeout=25)
        except Exception as error:
            print('Telegram: %s, próbuję dalej' % error)
            time.sleep(3)
            continue
        for update in updates:
            offset = update['update_id'] + 1
            message = update.get('message') or {}
            if (message.get('text') or '').strip().lower().startswith('/start'):
                chat = int(message['chat']['id'])
                who = (message.get('from') or {}).get('first_name') or ''
    if chat is None:
        print('\nNie przyszło /start w ciągu %d minut. Uruchom kreator jeszcze raz.' % (WAIT // 60))
        return 1
    call(token, 'getUpdates', offset=offset, timeout=0)
    existing = {}
    try:
        existing = json.loads(CONFIG.read_text())
    except (OSError, ValueError):
        pass
    chats = sorted({int(c) for c in existing.get('chat_ids') or []} | {chat})
    CONFIG.write_text(json.dumps({'token': token, 'chat_ids': chats}, indent=1))
    os.chmod(CONFIG, 0o600)
    subprocess.run(['launchctl', 'kickstart', '-k', 'gui/%d/com.btc-lab.telegram' % os.getuid()],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    call(token, 'sendMessage', chat_id=chat,
         text='BTC Lab połączony%s. Napisz /pomoc, żeby zobaczyć komendy.' % (', ' + who if who else ''))
    print('\nGotowe. Czat %s zapisany. Bot wysłał Ci wiadomość powitalną.' % chat)
    return 0


if __name__ == '__main__':
    sys.exit(main())
