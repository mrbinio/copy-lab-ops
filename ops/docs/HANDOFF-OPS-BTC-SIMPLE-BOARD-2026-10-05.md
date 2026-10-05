# HANDOFF — One PAPER copy number, 2026-10-05

## Executive summary

The main screen was mixing strategies, hypothetical tickets and several copy totals. It now shows one PAPER copy result, from the closed `wallet_copy_positions` book, with a switch for today, the last 7 days and lifetime. Wallets that were turned off later stay in the period that contains their closes. Open positions are a separate line. There is no fresh sale quote, so an open book says “brak aktualnej wyceny”; zero open positions is a confirmed zero.

## Numbers at the read

Read from the live database on 2026-10-05, about 15:16 Stockholm. Copy rules were not changed.

- Today: **−0.71 USD**, 3 closed trades. Table sum and journal sum match.
- Last 7 days: **−128.27 USD**, 551 closed trades. Same match.
- Since the start: **−128.27 USD**, 551 closed trades. Every close in this book is inside the last 7 days, so these two periods are the same figure.
- Open positions: **0**. Confirmed zero. No mark-to-market.
- Two wallets are copying now. The other losses stay in the table.

Hypothetical observation and old strategy results are on other tabs. They are not added to this number.

## What changed

- `paper_board` builds the three periods from the copy positions.
- The private page on port 8769 leads with that board. The journal is the same book and the same period.
- A github.io or other preview is labeled as an outdated preview.
- The running revision is the service revision, shown only when it is a real commit id.

## Next decision

Open http://127.0.0.1:8769/ and hard-refresh. The public name still stops at Cloudflare Access before this page. Live orders stay off.
