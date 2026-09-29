# value-surface-paper-v1 — 2026-09-29, release0.5.1

Unvalidated PAPER experiment with a complete simulated lifecycle. No real orders or signer. Separate100USD account PER ASSET; not a combined100USD portfolio. All existing accounts, definitions and history preserved. Depends on the causal per-minute value-surface-v1 sampler introduced in0.5.0 (EXPERIMENT-VALUE-SURFACE.md). Wallet polling is independent; wallet events do NOT train this model or trigger copying. Automatic wallet discovery/verified wallet-PnL ranking are not implemented.

## Entry and size

Use only current-market research estimates generated within3seconds, matching rule hash, verified fees/rule and fresh matching reference. Requires50 previous officially resolved windows for the same minute/z bucket/rule, all labels available before this window started. The fixed empirical estimator incorporates new completed markets on future windows; this is not automated strategy search or proven calibration. Current unvalidated lower-bound probability must exceed ask+1c, fee,1c allowance and2c net margin. Choose largest qualifying conservative edge amongUp/Down. Quarter-Kelly budget capped at1% of100USD and reduced with realized losses; no stake growth above1USD after wins. One open position and one successful entry per market. No existing500USD risk budget is increased.

Persist BUY intent with model ID/cutoff, rule hash, side, timestamp, source timestamp, price cap and budget. Execution requires a NEW book received at least250ms later and at most5s after decision. Both book timestamps must be fresh. Tick-rounded fixed limit,50% depth, full notional FOK, minimum shares. Notional reserves worst-case fee/cost ratio; reject if rounded total exceeds budget. No historical or decision-time fill. Partial fills are NOT simulated: insufficient depth is no fill. This conservative FOK assumption must be separately validated before live use.

## Exit and settlement

For an open position, a fresh probability estimate can request sale when net proceeds of a full depth-checked liquidation per share exceed upper probability bound+1c. Persist fixed floor from required depth. Sale also uses a later NEW book,250ms–5s delay,50% depth, minimum size and full FOK. A failed sale keeps the whole position; no imaginary exit exactly at a stop threshold. There is no guaranteed stop-loss. Worst entry capital is bounded; a position may lose its entire purchase cost and entry fee.

If no acceptable sale executes, use existing official-label reconciliation. Settlement continues even when current collection fails. This isolated ledger credits simulated payout immediately when an official label is observed, unlike the legacy5-minute redemption delay. It is a settlement accounting convention, not real withdrawal timing. Record SETTLED versus CLOSED(sold). A paired comparison requiring equal capital reuse must account for this difference.

## Accounting/risk

All cash, fees, quantities in integer1e6 units. Invariant: cash+open acquisition cost=100USD+realized PnL. PnL=payout-cost-entry_fee-exit_fee. SQLite transaction atomically saves pending intent, positions and cash. Restart cannot duplicate a market entry or settlement.24h gross-loss reserve3USD; rolling7day6USD; realized drawdown including potential next loss <=8USD. Pause/reconciliation failures prevent entry and simulated discretionary sales; official settlement remains possible. This is independent of legacy experiment limits.

## Reporting and gates

Dashboard accounts, chart and journal include Value Surface PAPER100USD perasset. Hourly private export has value_surface_execution, error, latest100trades/truncation and cumulative fees/net/drawdown. Daily download adds value_surface_daily with period entries/closes/net/fees/trades, separately from value_surface_execution_cumulative. No inference that no trades means a broken engine: probability history and minimum-size feasibility can block trades.

Local tests cover delayed fills, same-source rejection, expiration, restart, both fees, insufficient sale depth then official loss, idempotent settlement, pause, duplicate, changed rule rejection, risk limits, dashboard snapshot isolation and date-filtered exports. Controlled fixtures are NOT live performance evidence. Live Mac deployment remains unconfirmed until a fresh0.5.1 export shows execution status.

Before any promotion: collect untouched forward executions, count distinct windows, report all tested hypotheses/cells, estimate uncertainty by day, compare net return and drawdown over common periods including nonfills. Keep fees and no-trade cases. Neither50 observations nor any single profitable trade authorizes live funds. This release does not claim to reproduce Mitch or guarantee profit.
