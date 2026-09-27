# ETH 15-minute PAPER research — eth-mid-window-v1

Frozen specification, 2026-09-27. New, separate hypothesis; no live execution.

## Why and what
Test whether persistent ETH direction relative to its own Chainlink TWAP60 opening can produce positive net results at executable Polymarket quotes. This is an unproven continuation hypothesis. The existing dimensionless BTC mid-window baseline is deliberately used as a controlled comparison, not as an optimized ETH model. No BTC dollar-distance threshold, model weights or historical training rows are used. It is not Mitch's v8 (which he described as 3–5 minutes, 55–80c and hold to settlement).

Entry: elapsed 180–420 seconds inclusive; ask 50–80c; 30 seconds of direction persistence (20+ observations, no gap >5s); volatility-normalized distance magnitude >=1; spread <=3c. A current ETH reference and exact observed opening are required. Both books must be fresh (<=3s), reference <=5s, fees/rule verified, market accepting orders, ledger reconciled, loss budgets available. Changed rules, missing opening, feed gaps and wrong-asset messages cannot be substituted with BTC or exchange spot.

Execution: $5 virtual notional plus fees; decision cap ask+1c, maximum80c; new arrival snapshot after >=250ms plus request time, only50% displayed depth, whole-size fill or rejection, tick/minimum checks. Exit attempts before600s at +10%/-20% net of both fees or from590s, fixed decision bid floor and delayed fresh arrival depth. No fill leaves full position exposed. Official CLOB winner alone settles remaining positions; simulated cash release follows the existing300s delay. A stop is not a guaranteed loss cap.

Separate virtual$500 account, one open/pending position,1.1% all-in entry ceiling, rolling24h3% gross loss budget,7d6%,8% realized peak drawdown reserve, identical to baseline controls. None are instructions for the user's100USDC account. BTC+ETH correlation can create concurrent losses; these isolated balances do not represent a funded diversified portfolio.

## Isolation and UI
- `data/lab.sqlite` retains BTC unchanged; `data/eth/lab.sqlite` owns ETH accounts, books, reference history, decisions, trades and labels.
- Supervisor starts a separate worker with `LAB_ASSET=ETH`. Ordinary data faults are contained in that worker. Fatal child exit triggers existing whole-service restart policy; not fully independent host availability.
- Root `data/PAUSE` blocks both assets; `data/eth/PAUSE` blocks ETH entries. Settlement continues.
- Private dashboard header has BTC/ETH selector. Account, journal, reference, decision reasons and reports follow selected asset. A missing ETH backend never displays BTC results as ETH.
- `/api/state?asset=ETH` and `/api/report?asset=ETH&date=YYYY-MM-DD` retain authentication and read-only behavior. Default endpoints remain BTC. Report IDs and filenames identify ETH.
- Hourly private report retains BTC top-level fields and adds `assets.ETH`, including its own export/heartbeat times. ETH report failure is explicit; BTC still exports. Existing token/schedule preserved. Daily downloads are per selected asset.
- ETH does not train the BTC value model, create BTC training examples or start the paired BTC exit experiment. Model UI says NOT USED. No separate real-money execution path exists.
- Installer tests first, backs up both existing databases, retains credentials and configured origin port. Mac deployment requires running the installer, not merely publishing this source. Existing diagnostic script remains primarily BTC; confirm ETH in private dashboard/API/hourly report.

## Evidence and acceptance
Public Gamma ETH market inspected2026-09-26 and a real public-feed smoke check2026-09-27: ETH15m exact description, ETH/USD60s source, active/accepting, exponent1 and rate0.07. Development smoke check had FRESH RTDS and both books; opening was absent because started mid-window, so no entry occurred. This is connectivity/parser evidence, not trading performance or Mac deployment.

Start history only from deployment. Keep all rejected windows and loss history. Review after >=14 calendar days and >=100 distinct entered/closed ETH windows, extending when uncertainty remains; these are review gates, not profitability guarantees. Compare BTC mid-window over the same calendar period and matched windows where feasible, including inactive/rejected windows, realized net PnL, fees, drawdown, invalid-data coverage, latency and minimum-order feasibility. Bootstrap by day to respect time clustering; no automatic live promotion. Require positive untouched-forward net with a positive lower95% day-block interval and acceptable drawdown before further PAPER expansion. Reject this version for expansion if net remains nonpositive or advantage disappears under conservative execution stress; no post-hoc parameter tuning on this test. Do not test multiple threshold variations simultaneously then select the luckiest.

Raw books are retained for later stress replay; market-data/SQLite storage and API load increase with the second worker. Monitor disk and coverage in reports. Host24/7 uptime and long-term retention are not newly guaranteed.
