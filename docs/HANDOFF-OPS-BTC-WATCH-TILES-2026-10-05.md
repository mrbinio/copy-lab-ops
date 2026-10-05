# HANDOFF — Observed wallet tiles, 2026-10-05

## Executive summary

New observed wallets were on the dashboard as PAPER accounts with $0 and 0 trades. Those numbers are the real paper book. Copy buys stay paused while a wallet is observed, so that book is a confirmed zero and says nothing about analysis.

The analysis is in skip reviews. On the live database, 14 of 15 observed wallets already have hypothetical fills waiting for settlement (`COPY_PAUSED` / `FILLED_PENDING_SETTLEMENT`). None of those observation tickets are settled yet, so their net after costs is still missing, not zero. A separate set of older skips (too late, position already open, price moved) does have a settled net. That net is not the PAPER account and does not count toward `paper_test`.

`b77c706` was already the running release. This change does not restart discovery rules, risk limits, or live orders.

## What changed and why

The card was reading `wallet_copy_positions`. Observed wallets never get those rows. The tile now reads a cached watch summary: roster state, last check, last source trade, last buy, open and settled observation copies, observation net after fees, the PAPER account beside it, the last skip reason, and progress against the existing `paper-roster-v1` bars (20 settled, 5 windows, 7 evidence days, net ≥ 0.01, best day ≤ 70%). Missing measurements stay “brak danych”. A failed poll is not shown as “no trades”.

The summary runs on a worker thread every upkeep cycle. `publish()` only attaches the last cache. It does not scan the 60k skip rows on the copier loop.

Settlement was stuck behind that backlog: about 6,763 ended fills were waiting, and the review took 5 arbitrary rows every 30 seconds. Ended hypothetical fills are now first (8), then up to 5 other due skips. That does not open a paper buy and does not replay a signal older than 90 seconds.

## Numbers at the check, before this deploy

Observed 15. Observation fills open on 14. Observation fills settled: 0. One observed wallet, `d1662625`, had activity and a fresh poll, and no copy decision in the fresh window. Paper positions stayed 551. `clob_live` stayed false.

## Changelog

- `btc-lab/lab/wallet_watch.py` — read-only per-wallet summary.
- `btc-lab/lab/wallet_copy.py` — cache on the account payload; fill-first skip review off the event loop.
- `lab/app.js`, `lab/index.html`, `lab/style.css` — tile labels OBSERWOWANY / TEST PAPER / AKTYWNY PAPER / WSTRZYMANY.
- `btc-lab/tests/test_wallet_watch.py` — net after fee, missing versus zero, feed failure, and no paper buy from the review order.

## Settlement queue

The fill review always took the eight oldest ended markets and ignored when they were last tried. Unresolved markets in those eight seats blocked every later record. A due row now waits 60 seconds after an attempt, and the next due fills are selected. Observation tickets (`COPY_PAUSED` / `PAUSED`) also have their own eight seats, so older skip reasons cannot keep that result unknown. This does not create a paper buy and does not replay a signal.

Test: eight markets just tried and still unresolved, the ninth resolved. The ninth is settled. Its net is payout minus cost minus fee. The eight stay pending. The paper position count does not change.

## Next decision

Leave the wallets observed. Do not unpause them to manufacture trades. Live orders stay off. The useful check is the first settled `COPY_PAUSED` tickets and whether the ended-fill backlog shrinks without a new `COPIED_BUY`.
