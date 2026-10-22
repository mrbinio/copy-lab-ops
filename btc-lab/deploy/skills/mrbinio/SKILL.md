---
name: mrbinio
description: Run Damian's live Polymarket copy desk "Mr.Binio" (Mitch's Strata program) safely — status, resume after stop-loss, stop, safe restart, Mitch's updates, caps after a deposit, dashboard edits, watch/audit/shadow. Use for any request about Mr.Binio, Strata, the desk, stop-loss, "odblokuj", "zatrzymaj", "wynik", "aktualizacja od Mitcha", or btc.damianbiniarz.com.
---

# Mr.Binio — instrukcja obsługi

Damian (Polish, plain language, often from the phone via Remote Control) trades REAL money with
Mitch's copy desk. Answer in Polish, short, with proof (numbers, Polygonscan/Polymarket links).

## Where things are

- Desk (Mitch's repo, branded Mr.Binio): `~/Projects/Strata-Oktober-20`
  - runs as launchd `com.mrbinio.desk` (RunAtLoad, KeepAlive); logs `logs/desk.out|err`
  - local API: `http://127.0.0.1:8900/api/health`, `/api/state` (cash, pnl, mode, halted, open_position, chat, clob, copy_chain)
  - DB: `data/live/windows.sqlite` (tables `windows`, `meta`, `chat`); halt file `data/live/halt`
  - settings: `.env` (owner-only, holds the private key — NEVER print it), `wallet_targets.local.json` (our caps)
- Lab folder: `~/Library/Application Support/BTC Lab` (tools/, logs/, secrets/, telegram.json)
- Our tools (source in `~/Projects/copy-lab-ops/btc-lab/deploy/`, installed in `BTC Lab/tools/`):
  - `mrbinio_watch.py check` every 5 min (`com.mrbinio.watch`): alive/halted/live/clob, unknown
    network connections, code-fingerprint changes → Telegram
  - `mrbinio_watch.py audit` 07:30 (`com.mrbinio.audit`), `shadow` every 3 h (`com.mrbinio.shadow`)
  - `strata_gate.py` (`com.mrbinio.gate`): btc.damianbiniarz.com → login → desk on 8900
- Wallets: signer `0xEb1FA4A1AFA2138Bba3B106E4a56778236a3bF01`, deposit wallet (trading money)
  `0x2De437B983E864Dc8814bDca88493c87D3C1778c`, Kraken USDC (Polygon) `0xcFf015f1C22bfFE66529d5F8967ADbeDf5E95396`
- Telegram bot "Mr.Binio" (token in Strata .env and BTC Lab/telegram.json). Plain-text pings:
  status, ?, today, yesterday, week, help, emergency halt.

## Hard rules

1. **Exactly like Mitch.** Use his code and his defaults. Caps only from his README table
   (`max_cap`: $100→3, $250→8, $500→15, $1000→30; between: interpolate down). Stop-loss = his
   default 50. If any value is not Mitch's, say so explicitly before using it.
2. **Never restart while a ticket is open.** Always use the gated restart below.
3. **No automatic transfers** except the agreed Kraken sweep (line 250, chunks of 5, keep 0).
   Never send anything to Mitch. Profit share was removed by Mitch (no 10%).
4. **A bare "ok" is not consent** to change trading, code or money paths — confirm in one line.
5. **Never pull Mitch's updates blindly** — review first (procedure below).
6. Never print `.env`, keys, tokens. Don't send Damian's email anywhere.
7. Polymarket blocks orders from Poland — no VPN advice, ever.
8. After any edit to the desk's files, reset the watch's code baseline (else false alarm).
9. Mac noise: keep CPU light; kill any headless Chrome you start (`pkill -f "scratchpad/chrome"`).

## Procedures

### Status ("jak wynik", "co się dzieje")
```bash
curl -s -m 8 http://127.0.0.1:8900/api/state | python3 -c "
import sys,json,time;d=json.load(sys.stdin)
print('mode',d['mode'],'halted',d['halted'],'cash',round(d['cash'] or 0,2),'pnl',round(d['pnl'] or 0,2),'open',d.get('open_position') and d['open_position'].get('side'))
for c in (d.get('chat') or [])[-15:]:
  t=str(c.get('text'))
  if any(k in t for k in ('Copied','Official','Missed','Stop')): print(time.strftime('%H:%M',time.localtime(c['ts'])),t[:120])"
```
Real balance proof (deposit wallet pUSD from chain): eth_call balanceOf on
`0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB` via `https://polygon-bor-rpc.publicnode.com`.
Shadow while stopped: `cd ~/Projects/copy-lab-ops/btc-lab/deploy && python3 -I -c "import sys;sys.path.insert(0,'.');import mrbinio_watch as m;print(m.shadow_text(m.halt_since(),'od zatrzymania'))"`

### Gated restart (only when FLAT)
```bash
curl -s -m 8 http://127.0.0.1:8900/api/state | python3 -c "import sys,json;d=json.load(sys.stdin);p=d.get('open_position');print('open:',p and p.get('side'));sys.exit(1 if p else 0)" \
 && launchctl kickstart -k gui/$(id -u)/com.mrbinio.desk && sleep 15 && curl -s -m 5 http://127.0.0.1:8900/api/health
```
If it exits 1: wait for the window to settle (every :00/:15/:30/:45 + ~2 min) and retry.

### Stop now ("zatrzymaj")
`curl -s -X POST http://127.0.0.1:8900/api/halt` — no new buys, open bets settle. (Damian can also
send `emergency halt` to the bot.)

### Resume after stop-loss / halt ("odblokuj", "wznów")
Stop-loss baseline is `meta.live_start_cash` (first live wallet read; survives restarts). Deleting
only the halt file re-halts at once. So:
1. Show Damian the shadow result since the stop and confirm he wants to resume.
2. Set caps for the current balance (Mitch's table), then — only when FLAT — stop the service
   (the running desk locks the DB), reset baseline and halt, start again:
```bash
cd ~/Projects/Strata-Oktober-20 && U=$(id -u) && curl -s -m 8 http://127.0.0.1:8900/api/state | python3 -c "import sys,json;d=json.load(sys.stdin);sys.exit(1 if d.get('open_position') else 0)" \
 && launchctl bootout gui/$U/com.mrbinio.desk && sleep 4 \
 && sqlite3 -cmd ".timeout 10000" data/live/windows.sqlite "update meta set v='' where k='live_start_cash'" \
 && rm -f data/live/halt && launchctl bootstrap gui/$U ~/Library/LaunchAgents/com.mrbinio.desk.plist && sleep 25 \
 && curl -s -m 5 http://127.0.0.1:8900/api/health
```
   The next wallet read becomes the new start; stop-loss = start − 50. Make sure `com.mrbinio.watch`
   is loaded (alerts) and `com.mrbinio.shadow` is off while playing; reset the watch baseline.
3. Verify `halted False`, `mode live`, `clob ok`, cash; tell Damian new start and stop line.

### Mitch's update ("aktualizacja", "git pull")
```bash
cd ~/Projects/Strata-Oktober-20 && git fetch -q origin && git log --oneline HEAD..origin/HEAD && git diff --stat HEAD origin/HEAD
git diff HEAD origin/HEAD | grep '^+' | grep -oE 'https?://[a-zA-Z0-9.-]+|wss?://[a-zA-Z0-9.-]+|0x[0-9a-fA-F]{40}' | sort -u
```
Read changed code (engine/clob/live_wallet/telegram/server/run.py) for new hosts, addresses,
payments, telemetry. If clean: `git pull --ff-only` (our only local change is
`dashboard/index.html`; if it conflicts, take Mitch's file and re-apply our blocks — see below),
run tests WITHOUT our caps file (`mv wallet_targets.local.json /tmp/ && .venv/bin/python -m pytest tests -q; mv back`),
gated restart, reset watch baseline, add any new hosts to `ALLOWED_HOSTS` in mrbinio_watch.py.
Tell Damian what changed in plain words.

### Caps after a deposit or growth
Deposits go to the deposit wallet (from Kraken: USDC on Polygon to the signer; wrap/move as needed).
Then set `wallet_targets.local.json` `{"max_cap": N}` from Mitch's table for the new balance,
reset baseline if resuming, gated restart. Kraken line stays 250 unless Damian changes it.

### Reset the watch's code baseline (after our own edits)
```bash
python3 -I -c "import json,os;p=os.path.expanduser('~/Library/Application Support/BTC Lab/logs/mrbinio-watch.json');s=json.load(open(p));s.pop('code',None);s.pop('code_alerted',None);json.dump(s,open(p,'w'))"
```

### Our dashboard blocks in `dashboard/index.html` (re-apply after Mitch overwrites it)
Title/desk name "Mr.Binio"; `style#binio-font` (Ericsson Hilda from ~/Downloads/Font as base64,
old BTC Lab colors, softer red #ef8791, rounded panels); `div#binioGuide` + `script#binio-lang`
(PL/EN switch, guide with numbered screenshot, ?lang=, ?guide=1); `style#binio-phone-css`,
`div#binioPhone`, `script#binio-phone` (phone view: P&L, cash, to-250, mode, clock, in play,
STOP with confirm, latest list; ?desktop=1 full view). Verify with a headless Chrome screenshot
(min window width ~500 px), then kill Chrome.

### Telegram message to Damian
Read token and chat_ids from `BTC Lab/telegram.json` inside python; send via
`https://api.telegram.org/bot<token>/sendMessage`; never print the token.

## Known behaviour (don't "fix")
- "Loop error: '>=' not supported ... NoneType" at window change — harmless in Mitch's code.
- "Redeem not yet: No market found" — Polymarket auto-redeems deposit-wallet wins.
- Bad nights happen to the source wallets too (21.10 00:30 window: all bought Up, Down won;
  Mitch lost too). Check against the source before blaming the code.
