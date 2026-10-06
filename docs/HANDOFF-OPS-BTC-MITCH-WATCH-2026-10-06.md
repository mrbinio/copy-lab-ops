# Handoff — Mitch copy wallets, pause speed, watchdog, dashboard

Date: 2026-10-06. PAPER only. `clob_live` stays false. Port 8769. The existing database, password and history were not reset.

## Executive summary

A second PAPER book, `mitch-copy-wallets-v1`, now runs beside the qualifier. It copies five Bitcoin 15-minute wallets with Mitch’s size rule, a $20 / $5 window cap and a one-sided 10 cent price limit. It does not use the qualifier’s profit gate, loss pause or 20–70¢ band, and it does not write that ledger.

The qualifier now pauses a wallet as soon as the current copying period is negative. It no longer waits for the 30-second roster pass, and a still-positive lifetime book no longer keeps a negative period buying. Sells and settlement stay on. Two extra pause ideas were measured and not turned on.

The 05:00–18:00 gap on the screen was a frozen dashboard publish, not a dead process and not a Mac sleep. A separate watchdog now restarts the service when the heartbeat or the publish goes stale. The main screen leads with status, project tabs and wallet tiles. The long journal is on Historia.

## What changed and why

- Mitch’s five wallets are watched with the shared collector. New events after this project’s start can be copied. Older buys are not replayed.
- Buy size is `min(D, 15) + 5% of (D − 15)`, then cut to the remaining window budget. D is price times shares on one stored activity row. The collector key is transaction, type, token and side, so several fills of one transaction collapse before the formula runs. A repeated row is not a second buy.
- A copy is skipped when the book we can actually buy is more than 10 cents worse than his price. A better price is kept. The fill is the book after the signal, not his price.
- Sells use source shares sold divided by source shares just before the sell, and only that fraction of our shares for that wallet. If the source book is unknown, the sell is not guessed.
- The qualifier pauses inside the same database transaction as the close, and again inside the transaction that would reserve the next buy.
- `com.btc-lab.watchdog` checks heartbeat and publish age every minute, reconnects by restarting only after that check fails, and stops after 3 restarts in 30 minutes.
- The Mac clock is read from `time.apple.com` on a timer. Local durations use a monotonic clock. Europe/Stockholm is display only.

## Numbers from the recorded book

These are the qualifier’s own closes, not a forecast.

- `218d69a9` current period since 04:36 was −25.60 USD by 19:25. Lifetime book was still +49.11 USD, so the old whole-book rule did not pause it. The period first went negative at 05:29:36. The next copied buy was 05:30:53, 78 seconds later. 155 copied buys were recorded after 05:29. Two positions were still open, cost about 4.62 USD.
- `4096b159` current period was −1.67 USD from 02:33 and was still marked copying. No copied buy was recorded after that time. The new rule pauses it because the period is negative.
- Not deployed, measured on `218d69a9` only: stopping after the first losing close would have left out later losses of about −194 USD and later gains of about +163 USD. Stopping after a 5 USD drop from the period high (the existing one-position cap, used here only as a yardstick) would have left out later losses of about −190 USD and later gains of about +163 USD. That is history, not a promise.
- Open positions stay after a pause. The existing caps remain 5 USD per position including fees, 25 USD per wallet, and 5 open positions. No new cap was added.
- Activity rows kept arriving every hour from 00:00 through 19:00 (hour 05: 10 542, hour 18: 19 905). The process start before the afternoon restart was 2026-10-05 23:24. The next start was 2026-10-06 18:34. The publish error `copy ledger mismatch` began at 05:20:01 and the on-screen journal stopped moving. The accounts checked at 19:28 matched cash, ledger and open cost. Clock guard readings at 19:26 were about −37 ms, marked ok.

## Assumptions that need Mitch

These are not his confirmed rules:

1. A sell does not give back used buy budget in the same window.
2. The $20 and $5 caps include buy cost and entry fee. Exit fees sit only in the net.
3. Partial sells use the share proportion above.
4. Paper capital is 500 USD per wallet because he did not set it. The window caps bind first.

Under 1 second from his trade to our paper fill is not confirmed. The public activity stamp is one second, and the fast chain row carries a local detection time plus a book quote, not the price he paid. Totals from those stamps stay unconfirmed. A local unit test is not that measurement and is not a profit result.

## Changelog

- `btc-lab/lab/mitch_copy.py` — separate book, sizing, caps, price rule, sells, latency fields.
- `btc-lab/lab/wallet_roster.py`, `wallet_copy.py` — immediate period pause, atomic with the buy.
- `btc-lab/lab/clock_status.py`, `worker.py` — NTP reading and wake check.
- `btc-lab/deploy/service_watchdog.py` — independent stall detection.
- `lab/index.html`, `lab/app.js`, `lab/style.css` — status bar, Mitch tab, Historia, tiles first.

## Limits the program cannot remove

The Mac must be powered on and logged in. A closed lid can still sleep. After a reboot the session must be unlocked before user agents run. The screen lock was not turned off. `caffeinate -i` already runs with the paper process so idle sleep is held off while that process is up; System Settings still show `sleep 1`. There is no approved remote alarm channel in this repo. A dashboard banner is not a phone alert. A destination Damian approves, and a credential kept out of git, are what’s missing.

## Next decision

Confirm with Mitch the three assumptions and the 500 USD paper capital. Decide whether the measured single-loss pause or the 5 USD drawdown pause should become a qualifier rule. Neither is on.
