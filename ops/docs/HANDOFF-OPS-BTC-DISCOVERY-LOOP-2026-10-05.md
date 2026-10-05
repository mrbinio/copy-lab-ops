# HANDOFF — Wallet discovery loop, 2026-10-05

## Executive summary

Automatic discovery existed only as an hourly CRYPTO month shortlist. `promote()` did nothing, and the roster was given no copy result, so a new wallet could not enter PAPER. That path is now `discovery-v1`: leads come from the live BTC/ETH 5m/15m trades tape and from the month board. The board is not a score.

One scan after the deploy watched **264** wallets on the tape (**759** prints) and probed **12**. **One** new wallet was admitted to `observed`, with copy buys paused. It is not `paper_test`. Live orders stayed off.

## What changed and why

The old scan listed the top 50 CRYPTO month names, probed 8, and stopped. Six of those names already traded our markets and were still not watched.

The new scan still reads that board, then adds the busiest wallets from `data-api.polymarket.com/trades` whose slug is `btc`/`eth` `updown` `5m`/`15m`. A wallet is admitted to `observed` only when the activity screen passes. `paper_test` still uses the unchanged `paper-roster-v1` rules on **our** hypothetical copies. Reported month PnL is not an input.

Observed names sit behind wallets we already copy in the 20-row queue, so a noisy candidate cannot take the active wallet's slot.

## This scan

Tape wallets 264, prints 759, probed 12. `copy_enabled` false. Worker `RECORDING`, book `FRESH`, healthz 200.

Admitted to `observed` (buys paused):

- `0x7121364063e70c2929ed22bd8c51ca9e4723b28d` from the trades tape, not the month board. 1,248 of our-market trades in the 30-day pull, span 47.2 hours, 41.5% inside the 20–70c band with 90 seconds left in the window, largest trade 0.6% of notional. Copy net, win rate, drawdown, and fees are empty until hypothetical tickets settle.

Rejected:

- `89647072`, `05b04524`: no BTC/ETH 5m/15m trades (`wrong_markets`, `too_little_history`)
- `9b9fa354`, `8a2e7537`, `f11764d4`, `13cf8ec3`, `218d69a9`, `2608ad88`, `3c67fb39`: our-market trades, but the returned history is shorter than one day
- `112b4746`: history under one day, and under 25% of trades are copyable in time (`cannot_copy_in_time`)
- `af5d1c50`: history under one day, and under 25% of trades are inside the 20–70c band (`poor_liquidity_or_price_band`)

Ten other month-board names were not probed. The cap is 8 board names plus tape names, 12 probes in total.

`3e6eba30` and honey-spot were already on the roster. Their state was not changed.

Roster after the scan: paper_active 1 (`4096b159`), paper_test 1 (honey-spot `dcfcf46e`), paused 4 (Atomforge `69de3680`, `365cf589`, `207e77c2`, `3e6eba30`), observed 1 (the new wallet). No ledger rows were deleted.

## Rules (not refit)

Promotion `observed` → `paper_test`: at least 20 settled hypothetical copies, 5 windows, 7 days, copy net at least $0.01, best day at most 70% of gains. A first sighting stays `observed` even if those numbers are already filled in. `paper_test` → `paper_active`: at least 30 copy trades, 14 days, net at least $0.01, same 70% day cap.

Pause from `paper_test` or `paper_active`: 7-day net at or below −$15, or 8 losses in a row. The old losses stay.

Restore: paused at least 14 days, and the hypothetical book after the pause is at least +$8 over 7 days with at least 10 hypothetical trades.

Replacement: at most 3 `paper_test` wallets. A new one that clears the promotion rule takes the slot of the weakest `paper_test` when its copy net is higher. The weaker wallet goes back to `observed`. Its positions stay. `paper_active` is not replaced this way. This did not fire on this scan.

## Changelog

- `btc-lab/lab/wallet_discovery.py` — tape plus board, activity screen, audit, observe only
- `btc-lab/lab/wallet_roster.py` — observe → paper_test, three test slots, audit actions
- `btc-lab/lab/wallet_observer.py` — `observed` is watched
- `btc-lab/lab/strategy_control.py` — a new `copy-0x…` id can be paused
- `btc-lab/lab/wallet_copy.py` — observed trades fill only leftover queue slots
- `lab/app.js`, `lab/index.html` — source, decision, reject reason, roster reason

## Activity API limit

Checked on 2026-10-05 against `0x3048d65321be3497164cdfc2996f94f98a2e7537`. The first 1,500 activity rows cover about an hour. Offset 5,000 still returns a full page. Offset 5,500 returns HTTP 400. The oldest readable trade in that pull was about 5.7 hours old, and that page was still full, so the wallet's real age is not in the response. A full page is not "too young". Only a complete pull shorter than one day is rejected for age. Passing the 20–70¢ and 90s gates is recorded separately from a result after fees. The after-fees number stays empty until a hypothetical fill includes a fee.

## Next decision

Leave the new wallet in `observed` until its own hypothetical book meets the promotion rule. That takes days of settled tickets, not another threshold change. Live trading stays a separate decision.

The Mac is running these files copied into release `b009e2b8b429-1790926011187411000`. The config revision string was not changed. `clob_live` remains false.
