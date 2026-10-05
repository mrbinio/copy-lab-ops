# wallet-signal-copy-v1 — forward PAPER, 2026-09-29

Purpose: measure whether following NEW signals from the three user-provided wallets can earn net returns at prices available to a delayed follower. No real orders or claims of proven source-wallet profitability. This is not Mitch v8's Binance signal algorithm or an exact replica of source sizing/partial exits.

## Frozen first experiment
- BTC worker observes all three original addresses; discovery candidates are not automatically traded.
- Supported: recognized BTC/ETH Up/Down5m/15m markets with exact event start/end, condition and token mapping, verified supported resolution rule and fee schedule. Other markets/rules are visibly skipped.
- Three separate500USD PAPER accounts, maximum5USD all-in each entry and one open/unpaid resolved position per wallet. Daily gross losses plus next5USD <=15USD; weekly <=30USD. These are isolated benchmark scenarios, NOT one1500USD wallet or the user's planned100USDC. Real100USDC feasibility and minimum sizes require a separate assessment.
- BUY follows a fresh source BUY. Another source BUY of the same open token adds to that PAPER lot only while the whole position, including fees, stays within the existing 5 USD budget. The wallet stays within five such positions, 25 USD. A source SELL closes the fraction of the source position immediately before that sell, counting buys and sells we did not copy. A first detected BUY is not proof that the source book was empty. An unknown opening position or a gap does not invent a fraction. A sell without a recorded source size leaves the position open. No additional take-profit or stop-loss.
- Only source timestamps AND first-seen timestamps after persistent activation. Historical activity is never filled retrospectively. Maximum source age90seconds; observer polling30seconds adds latency.
- Fetch current decision book, fix BUY limit at ask+2c / SELL floor at bid-2c, wait at least250ms, fetch a NEW source-timestamp book. Arrival must be <=5seconds after decision, fresh<=3seconds and before market close; otherwise no fill. No chasing. Full-or-none,50% displayed depth, market tick/minimum sizes, both entry/exit fees. Source price is evidence only, never a simulated fill price.
- Conservative fee reserve rate*notional keeps acquisition+fees<=5USD; this may buy less than5USD notional or fail market minimum. No silent limit increase.
- If a sale cannot fill, keep exposure to later source sells or official settlement. Verify official CLOB condition and winner token; release simulated payout300seconds after first official observation. Loss can consume full entry cost. No provisional payout.

## Audit / persistence
Independent cash accounts, unique copy ledger debits/credits, durable processed source-event keys, full local entry/exit evidence with source transaction, detection/fill timestamps, metadata and both books. Atomic position/cash/ledger updates; cash/exposure/PnL invariant checked before each loop. Interrupted events are marked ABORTED_ON_RESTART, not replayed at historical prices. Ledger mismatch halts copy engine; transient fetch errors remain visible and retry. Existing baseline accounts and losses are untouched.

Public activity v1 fingerprints lack log indices: identical source fills may collapse and indexed activity can arrive late. This is polling-based signal-copy approximation, not guaranteed complete chain reconstruction. Archive source activities, including skipped events, for coverage assessment.

## Dashboard / reports
Three Copy accounts appear in BTC selector, cards, journal, chart and Wallets section. Each reports net PnL, fees, realized drawdown, independent windows, decisions and errors. BTC view holds shared BTC/ETH copy scenarios. Daily export has wallet_copy_daily (period results) and wallet_copy_cumulative; private hourly report has wallet_copy_execution plus error. Do not sum daily and cumulative totals or treat repeated hourly records as new trades. Report amounts for trades are microUSD/shares1e6; account summaries are USD. Full quote evidence remains in localSQLite; bounded reports flag truncation.

## Evaluation precommitment
Do not tune rules on the first wins/losses. Compare the same forward interval for all3 wallets, report skipped/missing signals, gross/net PnL, both fees, copy delays, independent windows and drawdown. At least200 settled independent windows per wallet across14 days is a review threshold, not proof. Before promoting a candidate, require positive net outcomes after execution stress and positive lower confidence bound using day/window grouping and correction for3wallet selection; report inconclusive results honestly. No automatic live promotion. Stop or repair on accounting/future-data errors; never erase losses.

## Validation
12 focused copy regressions cover delayed fills vs source price, both fees/sales, restart/deduplication, stale/pre-activation events, depth/minimum rejection, official payout delay/idempotency, token/fee/pause checks, independent wallets, cash corruption,5m metadata, daily export, historical backlog, identity validation and daily loss cap. Full suite and UI tests recorded in PROJECT_STATE. Mac deployment requires fresh0.6.0 worker and wallet_copy_execution timestamps; publication alone is not deployment.
