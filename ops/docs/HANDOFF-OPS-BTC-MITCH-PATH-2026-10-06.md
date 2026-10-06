# BTC Lab — Mitch path, speed, recovery — 6 Oct 2026

PAPER only. `clob_live` stayed false. Port stayed 8769. The live database, the copy start `1790703742.889763`, and the Mitch start `1791308151.5852091` were not reset.

This file is the evidence. A sentence that the service is up is not a result.

## What was wrong, and what the running code does now

The Mitch book had no official settlement. `anchor_source()` was never called, so a sell with an unknown source book stayed `SOURCE_PROPORTION_UNKNOWN` and the source book did not move. Buys were planned with fee `0` without a confirmed fee schedule. A sell assumed the whole position filled at the best bid. The book was not checked for token or age. A fast chain row wrote `SOURCE_PRICE_UNCONFIRMED` into `mitch_events`, and `pending()` then skipped that row forever. Activity rows with the same size were added together even when they were different fills.

The code on the paper process now:

- settles a Mitch position only from the official CLOB market: `closed` is true, the condition matches, the token is in the set, and there is exactly one winner. The ledger id `settle:<position>` is inserted once. A second call does not pay again. A local BTC price or the clock does not decide the winner.
- stores each source trade once and rebuilds the source book from a data-api baseline. A sell that cannot be filled still records the source trade. Missing shares stay unknown.
- accepts fee 0 only when the market says `feesEnabled` is false. Otherwise the fee rate has to be present. A sell uses the book depth (half the shown size, both fees). If the book cannot fill the size, the row is `NO_LIQUIDITY`, not a made-up full fill.
- re-reads the activity row inside the database transaction after the book and the fee request return. A closed market is `MARKET_CLOSED`. A book older than 3 seconds or for the wrong token is rejected. A buy whose book wait exceeds 3 seconds is `BOOK_WAIT_TOO_LONG` and is not filled.
- keeps `AWAITING_SOURCE_PRICE` eligible. A later API row wakes the copier. A book ask is not stored as the price the wallet paid. A `last_trade_price` print is used only when the transaction and the token size match the wallet transfer.
- splits identical fills by fill id. The same id replaces. A new id adds. An anonymous row is not added to a different fill.
- records the source transaction, token, market, and reason on the decision, including `SOURCE_PROPORTION_UNKNOWN`.
- holds Mitch buys for one wallet when cash, the ledger, the remaining cost, and the closed net disagree. The other wallets are not held. The check is not turned off.
- keeps a qualifier sell that is older than 90 seconds and younger than 24 hours as `LATE_SELL_NOT_FILLED`. The source book is updated. The paper position is not sold at an old price.
- gives each finished qualifier period an id and keeps the old positions on their open time. The return after a positive observation opened after the pause is unchanged. The sample stays `uncertain` when the new observation is small, and `sample_size` is `small`.
- restarts a stopped copier task inside the process, up to five times. The watchdog restarts the service for a stale heartbeat, a copier step that has stopped, or a publish this process let go stale. A timestamp older than the process is ignored. HTTP 503 with a fresh heartbeat is recorded and does not kick the service. A ledger mismatch does not restart the service.

These are still assumptions, not statements Mitch confirmed: a sell does not restore the window buy budget; the cap includes the buy cost and the entry fee; a partial sell uses source shares sold divided by the source shares just before that sell; paper capital is $500 per wallet.

## Revisions

| Piece | Revision | How it was checked |
| --- | --- | --- |
| Paper process (supervisor, BTC worker, ETH worker, server) | `08c81e3e6742bfeaa1a41068b28f9ec9f3a2c8b3` | `LAB_REVISION` on the running processes after the restart |
| Watchdog script, read from disk each minute | `e30aaa1a0f3a42f3ddd9c454354866836bb57ab0` | Installed at `~/Library/Application Support/BTC Lab/service_watchdog.py` |

The process was not restarted again for the two later watchdog commits. Those commits only change the watchdog file. The wrapper had been up for 1 hour 16 minutes at 00:06 on 7 Oct, which covers the stable part of the watch below.

Backup before that restart: `~/Library/Application Support/BTC Lab/backups/lab-20261006-222513-before-08c81e3.sqlite`, 5.7 GB, `PRAGMA integrity_check` returned `ok`.

## Tests before the restart

On an isolated database, not the live book:

- Mitch buy, add-on, partial sell, then one official payout for the remainder. A second settlement did not pay again. An open market and a mismatched token did not pay.
- Fee not confirmed and a book too thin both return no fill.
- Two fills with different ids and the same size stay separate. A refetch of the same id does not add. An anonymous refetch does not add. A changed anonymous total replaces that one fill.
- A chain quote is replaced by the confirmed API price.
- A qualifier sell 120 seconds old is `LATE_SELL_NOT_FILLED` and the paper position stays open.
- A negative close and a waiting buy on the same transaction: the buy is `COPY_PAUSED`.
- Watchdog: a fresh heartbeat and a publish this process let go stale is a restart. A ledger mismatch is not. A process still in `STARTING` for under 10 minutes is not. After the restart the proof file stays `verified: false` until a later check sees the problems gone.

Replay of one stored live sell (`SOURCE_PROPORTION_UNKNOWN`, wallet ending `25386215`) into `/tmp/mitch-replay-not-live-*`: the new decision stored the transaction, the token, and the market. That database was not the live book. The two historical live rows were not rewritten. They still contain only `delayed` and `timing`.

## Observation after the restart

Samples every 60 seconds from 22:45:13 to 00:03:17 Stockholm, 78 rows, in `docs/evidence-btc-mitch-path-2026-10-06.jsonl`. The sampler has stopped. The paper service and the launchd watchdog have not.

Four windows sit entirely inside the samples: 23:00–23:15, 23:15–23:30, 23:30–23:45, 23:45–00:00. The 22:45 window is missing its first 13 seconds. The 00:00 window is only the first few minutes.

From 22:50 onward (65 samples, 64 minutes) the worker did not return to `STARTING`. Heartbeat age median 24 s, max 74 s. Copy step age median 12.5 s, max 40 s. Mitch step age median 25 s, max 80 s. Copy ledger health `ok` on every sample. Mitch health `ok` once the first Mitch publish of this process existed. Clock `synced` on every sample. Last offset 60.9 ms, uncertainty 2.3 ms.

`/healthz` was 503 for most samples because the worker status is `DEGRADED`: the reference websocket timed out during the opening handshake (`MISSING_OR_STALE`). The book status at the end of the watch was `FRESH`. That 503 is why the screen must not say the whole system is fine. The copiers were still stepping.

## Speed

Goal: under 1000 ms from the source transaction to the committed PAPER row. That goal is not met.

Mitch, this process, five decisions that carried a timing block. The total is not the sum of the stages. Total is confirmed only when the source stamp is finer than one second. These five are one-second API stamps, so total confirmed is 0.

| Stage | n | median | p95 | max | under 1 s |
| --- | --- | --- | --- | --- | --- |
| Detect, one-second API stamp | 5 | 6099 ms | 16850 ms | 17554 ms | 0% |
| Book fetch (`book_ms`) | 5 | 21064 ms | 27271 ms | 28752 ms | 0% |
| Total, sub-second source and a synced clock | 0 | — | — | — | — |

Examples that were not filled, with the source transaction:

- `207e77c2` `df8b31827ec53998d2` at 23:28:25, tx `0xfd30c6385d75`, book 28752 ms, `BOOK_WAIT_TOO_LONG`
- `207e77c2` `37cc7f84d309fa9c99` at 23:28:47, tx `0x0e881bff3b62`, book 21064 ms, `BOOK_WAIT_TOO_LONG`
- `25386215` `9f199e58f5b0f44218` at 23:58:09, tx `0x8f0568c8f8f4`, book 11127 ms, `BOOK_WAIT_TOO_LONG`

The qualifier book had no `COPIED_BUY` in this window, so there is no trade-to-commit sample for that project either. The copy step staying under 40 s is the loop waking up. It is not a fill time.

The public market websocket is connected for the current and next BTC 15-minute tokens. A print becomes the paid price only when the transaction and the size match the wallet transfer. No decision in this hour had `source_precision=source_subsecond`. The missing piece for the one-second goal is that join actually occurring, plus a book fetch that finishes inside the remaining time. One-second activity timestamps cannot prove it.

## Mitch wallets

No Mitch position was opened on the live book. `mitch_positions` is still 0. That is not a hidden fill.

| Wallet ending | Copies | Open | Window spend | Buy hold | What this hour showed |
| --- | --- | --- | --- | --- | --- |
| 4096b159 | 0 | 0 | 0 | no | No qualifying BTC 15m buy inside the time limit |
| 365cf589 | 0 | 0 | 0 | no | Late buys, class `queue`, for example `aee6e98e4a5edead2c` tx `0x9f0bbebf76` at 23:31:33 |
| 207e77c2 | 0 | 0 | 0 | no | Late buys and the slow-book rows above |
| 1d1865cf | 0 | 0 | 0 | no | No qualifying buy |
| 25386215 (mihaXd, $5) | 0 | 0 | 0 | no | Late buy `603ecce5a78365a9bc` tx `0xfd0df36918` at 23:31:33. The two older `SOURCE_PROPORTION_UNKNOWN` rows are unchanged |

Since 22:45 the new Mitch decisions were: `LATE_BUY_NOT_COPIED` 21, `NOT_BTC_15M` 20, `BOOK_WAIT_TOO_LONG` 10 by 23:58. The 505 historical late rows are still in the table and are counted apart from these 21. Awaiting price at the last sample: 0. The late rows in this hour are class `queue`: we had the row and did not decide inside 90 seconds. They are not the startup history load.

## Qualifier pause, the five named wallets

Buys after the current pause: 0 on each of these. Open paper cost after the pause: 0 on each. The positions from the earlier period are closed, so they stay in that period by their open time.

| Ending | Last pause | Period that ended | Net of that period | Buys in the period | After the pause |
| --- | --- | --- | --- | --- | --- |
| 218d69a9 | 6 Oct 20:58:16 | from the 20:32:40 retest | the audit at 19:31:32 recorded −25.60 USD on 118 trades; three buys after the 20:32 retest, then the new pause | 168 buys in the long period that ended 19:31 | 0 buys, 0 open cost |
| ee4ec347 | 6 Oct 21:05:26 | restored and paused again several times the same morning; last retest 20:32:40 | earlier pause net −2.90 USD | 0 in the empty stretch, 8 buys after an earlier pause that the retest allowed | 0 buys now, 0 open cost |
| d0df0b56 | 6 Oct 21:05:26 | 05:34–11:05 | −0.91 USD, 5 closes | 6 buys | 2 buys after that pause during the retest, 0 open now |
| 99e456ea | 6 Oct 20:55:31 | promoted 11:17, no separate audit pause row before the roster `since` | 0 closes in the current since | — | 0 buys, 0 open cost |
| 93f277a6 | 6 Oct 21:30:42 | promoted 16:36 | 28 older closes, 0 in the current since | — | 0 buys, 0 open cost |

During the watch the qualifier marked 3000 `COPY_PAUSED`, 1321 `SOURCE_TOO_OLD`, and 4 `LATE_SELL_NOT_FILLED`. Those four sells were not filled. Ids: `fbe49577a735286514` tx `0xa7b87d2a9e24` (eth 5m, 23:04), `3ce7d7809fca3a6d3e` tx `0xc57e7a1c17c0` (23:44), `25a8c9d3ead5947762` tx `0x4758f44f248e` (btc 5m, 23:45), `94f33ef430a15bd198` tx `0x97b33faf7996` (23:50).

## Recovery

The watchdog unit test restarts when the publish of this process is stale and the heartbeat is fresh, writes `watchdog-restart.json` with `verified: false`, and does not restart for a ledger mismatch. On the Mac, a degraded `/healthz` (503) with the copiers stepping was left running: the status file action was `degraded`, problems empty. The process etime of 1 hour 16 minutes is the check that launchctl was not called again during the stable hour.

One restart did happen at about 22:50, before the leftover-timestamp fix was installed. The watchdog treated the previous process's publish time as this process failing. After `d1cb977` and `e30aaa1` that did not repeat.

Alert delivery is not configured. The watchdog posts only if `BTC_LAB_ALERT_URL` is set in its environment. No address was invented and none is in git. Set that variable on the watchdog launchd job if a webhook is wanted. Until then the screen and `logs/watchdog-status.json` are the record.

## What is still limited

- No live Mitch fill happened, so official settlement has not run on the live book. The isolated test and the separate replay are the evidence for that path.
- End-to-end copy time is not under one second. The measured book fetches are 5–29 seconds. The source stamps in those decisions are one second.
- The worker is `DEGRADED` because the reference websocket handshake times out. `/healthz` stays 503 while that is true. The book was fresh at the last read.
- The logged-in dashboard was not opened. `http://127.0.0.1:8769/api/state` returns 401 without the password. `https://btc.damianbiniarz.com/healthz` returns 302 from Cloudflare Access. The static files on the release match the repo (`app.js` cache `20261006-path`), including the line `ostatnia publikacja wyników`. Confirming the pixels needs one login on that site.
- The copy queue sat at 20, which is the batch cap, while the step kept moving. That is a full batch, not proof the backlog is empty.
