# v0.5.1 — 2026-09-29: isolated value-surface PAPER execution

Prepared and locally tested:99 Python tests and5 JavaScript export cases passed, app.js syntax checked. Publication is not Mac deployment. New value-surface-paper-v1 has its own100USD scenario per asset, <=1USD all-in entry, delayed fresh-book FOK buys/sales with50% depth, both fees, independent limits and official-label settlement. Existing accounts/thresholds/history untouched. Dashboard account/chart/journal and separate daily/cumulative exports added. See EXPERIMENT-VALUE-EXECUTION.md for exact rules, settlement timing and limitations. No signal until previous per-cell official history is sufficient; minimum order may prevent trades. No promised profitability or immediate activity. Wallet events are observed independently, not used for automatic copy trading, training or wallet discovery. Require fresh worker0.5.1 and value_surface_execution timestamps to confirm installation.

---
# v0.5.0 — 2026-09-29: continuous wallet observation and full-window value research

Source prepared and tested; Mac deployment NOT yet confirmed. See EXPERIMENT-VALUE-SURFACE.md. BTC worker polls the three user-supplied public wallets every 30 seconds, including inactivity; errors and page limits are explicit. Independent per-asset minute-level causal samples support probability/cost/size and exit-value research. No new orders, no changes to existing accounts, risk limits or thresholds. Hourly private report includes observer status, bounded activity and value research; no new dashboard panel is included.

The 2026-09-29T06:05Z private export independently confirmed BTC and ETH v0.4.2 RECORDING/FRESH; this is not a confirmation of v0.5.0. New deployment evidence requires v0.5.0 plus new observer/research timestamps. The public activity endpoint returned403 from the development environment; live wallet schema/access on Mac remains unverified. Polling does not claim direct chain subscriptions or complete historical wallet PnL.

---
# v0.4.2 — 2026-09-28: target-reference watchdog

Confirmed code defect: an open RTDS socket with PONG/unrelated messages but no advancing valid TWAP60 could remain stale indefinitely. A20-second monotonic deadline now forces reconnect through existing disconnect cleanup/backoff. Only an advancing accepted TWAP60 source timestamp extends the deadline; PONG, rejected data and other topics do not. Applies separately to BTC and ETH. No strategy/risk/history changes. Fresh data and exact next opening are still required for trading. Sept28 11:03UTC export showed BTC reference4215s old while worker heartbeat was fresh; this is consistent with the defect, not proof of the remote root cause.

83 Python tests passed locally, including silence, PONG/duplicate flood, advancing target and socket failure. Mac deployment and recovery remain unconfirmed until a new export shows0.4.2 and advancing fresh BTC TWAP60. Publication is not a Mac update.

---
# v0.4.1 — 2026-09-28: complete-set observer, source ready

Adds observation-only BTC/ETH UP+DOWN cost and delayed quote probes, per-window records and both report exports. No orders, simulated ledger fills or changes to existing strategies/risk. Read EXPERIMENT-COMPLETE-SET.md. 78 Python tests passed across the suite; an additional export/isolation test is checked separately. Mac update required; publication is not deployment.

Mac0.4.0 confirmed by private export2026-09-28T06:03:36Z, BTC/ETH fresh. BTC mid weekly gross losses25.426114USD plus next5USD+fee exceed30USD limit, explaining risk pause. ETH26closed net-2.240430USD fees5.097477. These are paper results, not live eligibility.

---
# v0.4.0 — 2026-09-27: ETH PAPER source ready; Mac deployment unconfirmed

Adds an isolated ETH 15-minute normalized-momentum experiment `eth-mid-window-v1`, separate worker and `data/eth/lab.sqlite`, authenticated BTC/ETH dashboard selector, per-asset daily downloads and `assets.ETH` in hourly private reports. Existing BTC accounts, paired exits, thresholds and history are preserved. Read EXPERIMENT-ETH.md for frozen entry/exit/execution rules, isolation boundaries and review criteria. ETH is an unvalidated experiment, not Mitch's corrected v8 and not proven diversification.

Local verification:73 Python tests and5 JS export cases passed, plus DOM interaction checks for asset switching, distinct account/cards, PL guide and returning to BTC. Public-data smoke check on2026-09-27 confirmed ETH rule/fee parsing, both books and fresh ETH/USD TWAP60. Missing mid-window opening correctly blocked entry. Browser visual rendering was not independently checked (browser binary download unavailable). No Mac or profitability claim follows from these tests.

Last Mac export independently read:2026-09-27T06:02:13Z, worker0.3.1 RECORDING/FRESH, heartbeat age0.829s at export. BTC mid44trades net-10.496186USD, early19 net-1.092873, late42(41closed) net-8.352144 with5.0175USDopencost, value0. Paired13valid/0invalid:baseline+1.249467USD/DD2.641679;candidate+2.442427/DD2.798124. This confirms v0.3.1 deployment and initial forward comparisons, not statistical edge. Continue frozen comparison; do not replace active thresholds after13windows.

Installer preserves origin port and password; backs up both existing databases. Publication alone does not update Mac. ETH deployment proof requires worker0.4.0 and `assets.ETH.worker`, its heartbeat freshness and ETH market/reference identity in a subsequent export. Dashboard selector shows a separate ETH account; it is not a combined100USDC wallet. The existing diagnostic command primarily checks BTC.

---
# v0.3.1 — 2026-09-26: paired PAPER exit experiment; Mac deployment unconfirmed

Adds `paired-exits-v1`: two separate shadow exits on each newly accepted mid-window-v1 entry. Baseline TP +10% / SL -20%; candidate TP +15% / SL -10%. Existing accounts, risk limits, entries and history remain unchanged. Both arms use subsequent polling snapshots, full-fill depth checks and both fees. Gaps/stale quotes invalidate primary paired comparisons. No historical backfill. See EXPERIMENT-PAIRED-EXITS.md for frozen criteria and limitations, including conditional entry selection and polling latency.

Private hourly exports include `exit_comparison`; dashboard downloads include `exit_comparison_cumulative`. No new chart/card is added in this release. Read worker version, comparison updated_at, valid/invalid pairs separately; successful publication is not Mac deployment.

Verification: 67 Python tests passed locally, including delayed execution, fixed limit/depth rejection, duplicate/restart safety, official settlement, unchanged account ledger, and both report exports. These tests do not establish profitability. Last inspected Mac export (2026-09-26T12:01:19Z) still used v0.3.0: mid-window-v1 31 trades, net -11.531324 USD, fees 7.395302 USD. Keep PAPER.

# v0.3.0 — 2026-09-24: source ready, Mac deployment unconfirmed

Daily export now fetches authenticated /api/report afresh, never a cached browser snapshot or preview. Default: previous completed Europe/Stockholm day; optional date selector, DST-aware boundaries and dated filenames. Daily entries, realized results, both fees, recorded skip reasons and data counts are separate from lifetime balances. Full daily trades and up to 10,000 lifetime rows with explicit truncation. Deduplicate overlaps by trade id and period. Repeated cumulative balances with no new trades are valid.

Three existing baseline accounts and their histories remain; one new isolated mid-window-v1 PAPER account implements the authorized 3–7 minute, 50–80 cent hypothesis. Read EXPERIMENT-MID-WINDOW.md for exact frozen signal and sale rules and limitations. No proprietary Mitch model, calibrated probability or profitability is claimed. No real orders.

Schema adds positions.exit_fee default zero and CLOSED for full simulated sales. Both fees count in PnL, cash and gross-loss limits; official settlement cannot pay a sold position again. Dashboard win rate means profitable realized positions. The hourly publisher supports both schemas and is refreshed by the installer if installed already.

Dashboard adds today's net PnL and rolling gross-loss budget usage plus an EN/PL guide for the experiment. Installer preserves the existing port, tests first, backs up SQLite before migration, preserves credentials and data, and refuses incompatible rollback after experimental trades exist. It accepts a pinned commit argument.

Verification: 59 controlled Python tests, three JS export cases, syntax checks; all 32 historical trades in the user's Sept24 export reconcile unchanged in a temporary database. This is not Mac deployment or actual venue fill verification.

Latest inspected runtime: Sept24 18:59 UTC, v0.2.1, DEGRADED/MISSING_OR_STALE with recent worker heartbeat, 429 labels, model samples419; early -2.437825 USD/13 trades, late -16.204976 USD/19 trades, value0. This is a timestamped snapshot, not continuous monitoring. Private report reads succeeded Sept20 and Sept24; uninterrupted hourly coverage has not been audited. Require v0.3.0 in a new export to confirm deployment.

---
Historical documentation below; this update takes precedence.

# BTC Lab — current state

Release: 0.2.1. Scope: BTC paper research only. Sports, wallet copying, PolyCop and Telegram project excluded.

## Implemented

- Read-only collectors, three isolated paper books, transactional ledger, delayed depth simulation and official winner reconciliation.
- Transparent candidate model and reconstructed early/late baselines.
- Responsive English/Polish dashboard with an explicit optional synthetic design preview.
- Deployment configuration, authentication, tests and operating runbook.

## Operational truth

- A user-local macOS Intel/Monterey installer is available in `deploy/install-macos.sh`. It configures authenticated loopback access, a launch agent, bounded restart attempts and rotating logs. The user confirmed startup, HTTP 200, orderbooks, verified fee metadata and RTDS spot/TWAP streams on their Mac on 2026-09-18 (v0.1). The user subsequently confirmed remote browser access through Cloudflare.

- The user runs the service on their private Mac. No direct remote host access or external availability monitoring has been established.
- The user confirmed browser access through Cloudflare Access/Tunnel at btc.damianbiniarz.com. This does not grant the reviewing assistant authenticated runtime access. No independent heartbeat monitoring is verified.
- No runtime wallet or Kraken connection exists. No money was moved.
- No profitability claim. Any design preview is synthetic.
- Development public-data access is intermittent; real RTDS and Gamma were received during debugging. Transaction lifecycle tests use controlled fixtures; this is not a forward performance record.
- GitHub is code and static hosting. It is not the continuous Python runtime.

## Budget

Infrastructure planning ceiling: EUR 15/month. No purchase made. Virtual research bankroll: $500 independently per strategy; not combined into one reported account. Future capital feasibility must be assessed separately from research balance.

## Next bounded task

2026-09-18 follow-up: settlement supervision runs independently of current-market collection failures. Reconciliation failures block new paper entries, accounting conflicts persist a pause, and the empty-chart indicator is corrected. Regression coverage added for these failure paths.

Connect a persistent host in a permitted location; deploy this release; validate real API contracts, fee metadata, rule recognition and reference opening coverage; enable backups and independent monitoring. Begin with recording quality. Do not infer successful paper trading from a running dashboard.

## Research backlog

1. Golden dataset and Nautilus parity.
2. Validate v0.2 TWAP60 forward recording, exact opening coverage and execution on the Mac.
3. CLOB websocket recording with resync and gap handling.
4. Compressed event archive, disk/clock monitoring, external heartbeat and backup restore.
5. Multiweek untouched forward evaluation, daily-block confidence intervals and operating-cost accounting.
6. Any real-money test remains a separate explicit decision, with current venue eligibility, minimum orders and collateral requirements checked then.

## Change discipline

Store source/config/model versions with the experiment. Freeze tested definitions. Never reset losing trades, relabel provisional outcomes as final, hide fees, promote a paper candidate to real orders, increase stakes or transfer funds autonomously. This code has no real-order path.

## v0.2 update

Rule-specific TWAP60 reference selection, exact E18 prices and opening evidence, separate model dataset schema, safe gap handling and explicit dashboard reference label. Baseline paper strategies retain existing risk and signal thresholds; no live orders. The complete supported rule text and 15-minute event times are checked. Unknown descriptions and absent exact opening observations still skip trades. The user's 2026-09-18 logs and 2026-09-19 PAPER_SERVICE export confirm v0.2 ran on the Mac; v0.2.1 deployment is not yet verified. Local tests include TWAP versus spot divergence and official winner overriding provisional direction.

## v0.2.1 sampling correction — 2026-09-19

The training collector now uses the existing value-model horizon of 115–125 seconds remaining instead of 119–121. This is an explicit sampling-policy change, not a change to entry thresholds, sizing, risk limits or live eligibility. The first valid observation per market is retained by the database primary key, including across restarts. New rows include sampling_policy=first-valid-model-horizon-v2, actual remaining time and reference/book source timestamps. Older rows remain unchanged and identifiable by absent sampling_policy. The feature schema stays compatible: actual remaining time was already included in the feature vector. Evaluate results across the policy change; no claim of an unchanged sampling distribution.

Reference/history are now selected after awaited REST book collection. Both books must still be fresh when a training example is saved. No backdating, synthetic history, or capture outside the horizon. Extended network/reconciliation stalls may still miss the full horizon; this patch reduces loss from normal polling, not a guarantee of full coverage. Future coverage metrics should count eligible windows and capture failures separately.

Validation: 38 local controlled tests passed, including capture at 118 seconds, 115/125 boundaries, rejection outside the horizon, reference refresh during HTTP, stale second book, unsupported rules and duplicate prevention after restart. Not a macOS deployment test or proof of profitability.

User export at 2026-09-19 13:22:03 UTC: PAPER_SERVICE, v0.2.0, RECORDING/FRESH at export time; 385522 observations, 68 official labels; last model refresh 62/200 labelled examples. Early baseline: 6 settled, 4 wins, +1.325860 USD net; late baseline: 5 settled, 3 wins, -8.480440 USD net; value model: no trades. These are independent virtual 500 USD accounts. Small samples do not establish profitability. The snapshot cannot quantify how many eligible training windows were missed.


