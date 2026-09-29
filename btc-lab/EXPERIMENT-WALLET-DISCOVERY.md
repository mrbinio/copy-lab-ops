# wallet-discovery-v1 — read-only candidate screening

Official endpoint/schema: https://docs.polymarket.com/api-reference/core/get-trader-leaderboard-rankings (checked2026-09-29).
Request documented legacy /v1/leaderboard, category CRYPTO, orderBy PNL, limit50, periods WEEK and MONTH. A v2 counterpart is documented; no silent schema fallback.

Every hour after scan completion on BTC worker, retain wallets present in both lists with positive finite reported PnL and volume. This is a bounded shortlist, not a full-market search, independent confirmation, or a selection of proven profitable copy targets. Periods overlap. Selection/survivorship bias, open inventory, transfers, fees, delay, depth, price slippage and asset/window specificity remain unverified. No funds move; no auto-follow/copy and no trading rules change. Original three-wallet observations remain separate and run every30seconds after completion. Failure retains last successful candidates with explicit stale/error state and timestamp. Scan snapshots retained in SQLite.

Next evidence needed before paper copy qualification: reconcile activity/positions/cashflows, identify BTC/ETH markets, compare source-time/first-seen latency, simulate copies at newly available orderbooks including fees/depth, keep a frozen forward shortlist and include losses/inactive periods. Ranking profit is not expected follower profit.
