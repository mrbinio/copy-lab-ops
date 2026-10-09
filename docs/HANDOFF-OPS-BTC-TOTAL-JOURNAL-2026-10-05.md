# HANDOFF — Copy results in TOTAL and the journal, 2026-10-05

## Executive summary

TOTAL was only the research strategies, about −57 USD. The copy tiles sat outside that number, so a green observation result and a red paused paper book were both invisible in the total. The trade journal listed paper fills only. Settled hypothetical copies never became a row.

TOTAL now adds three separate books: strategies, copy PAPER accounts, and the observation net after costs. A missing observation net stays “brak danych” and is not added as zero. Other scored skips stay on the tile and are not in TOTAL. The journal adds the latest settled hypothetical copies for each wallet, marked HIPOTETYCZNA. That is not a paper buy and does not replay an old signal.

## What changed and why

The green observed tiles are the observation book. The losses the screen was hiding are the copy PAPER books, especially paused wallets. Both now enter the same total, with the strategy book, and the breakdown stays on the total line. Live orders stay off. Roster rules and risk limits are unchanged.

## Changelog

- `lab/app.js` — TOTAL is strategies + copy PAPER + known observation net. Journal rows include hypothetical settlements.
- `lab/index.html`, `lab/style.css` — cache key `20261005-total`.
- `btc-lab/lab/wallet_watch.py` — each watch summary carries the 12 newest settled observation rows.
- `btc-lab/tests/test_wallet_watch.py` — one settled observation row is journaled; an open fill and a non-observation skip are not.

## Next decision

Refresh the dashboard. The hypothetical rows appear after the paper service loads this watch summary. Do not unpause wallets to create journal rows. Live orders stay off.
