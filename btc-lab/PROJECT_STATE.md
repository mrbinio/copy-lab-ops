# v0.6.3 — 2026-09-30: risk sizing, causal copy guards and installer storage

Baseline entry sizing uses remaining cash/day/week/drawdown capacity capped at5USD all-in, conservative fee reserve and final atomic open recheck. Limits/history unchanged; market minimum can still prevent entry. Dashboard shows capacity and explicit exhausted/below-minimum reasons. Copy accounts KEEP their fixed5USD scenario and limits; split open-position/cash/day/week rejection reasons, expose current_block and last30 error details separately from recent decisions.

New copy BUY policy source-band3c-age10s-v1 rejects >10s old signals and asks >3c either direction from original fill at decision and arrival; buy limit cannot exceed source+3c. SELL policy unchanged, no price-band filter impeding exit. Experimental safety thresholds selected before new forward data, not fitted profit optima. Polling remains30s, so eligible copies may be sparse. Old results remain unchanged; no performance promise.

Installer cleanup preserves configured and launch-agent releases plus newest2, removes only recognized installer directories. Backups: preserve newest2 verified quick_check plus ledger-schema backups per asset, then remove older matching backups; skip symlinks/unknown files/journal-bearing backups, never data or credentials. Free-space check before stopping old service. New backups use partial files, integrity check and atomic rename; failure removes own incomplete file. Cleanup occurs during installation, not daily background work. Previously failed journal-bearing files are left alone. Full Mac installer not executed here.

Validation:125 Python tests including cleanup protection, low-space preflight, risk-capacity fit and copy source-price/age/arrival guards;13 JS cases and syntax passed. Publication and Mac deployment separate; require worker0.6.3 and fresh report. No live trading or raised limits.

---
# v0.6.2 — 2026-09-29: ETH 3–7 stop policy

New ETH mid-window entries carry eth-stop10-v1 and config_version eth-mid-window-v1-stop10-v1. Same 10% net stop threshold as new BTC positions, fees included, <=5USD acquisition including fee. Keep entry180–420s and50–80c, existing signal filters, +10% take profit and deadline590s. Protective exits/retries allowed until900s, including after minute10; full-sale delayed FOK may fail and loss can exceed threshold. Legacy positions retain prior policy, no historical resets. BTC and wallet copies unchanged; this does not add stop-loss to wallet copies or Value Surface. Not an optimized/proven profitable ETH strategy.

Validation:120 Python tests passed with added ETH entry policy/cap assertions and ETH failed-sale/retry-after-minute10/fees/no-double-settlement coverage;13 JS cases and syntax passed. Publication is not deployment; require fresh ETH worker0.6.2 plus new position policy to confirm. No real orders.

---
# v0.6.1 — 2026-09-29: restore BTC 3–7 and version loss exits

User explicitly corrected retirement: restore mid-window-v1 entries 180–420 seconds, original 50–80c signal filters. New BTC mid-window and early entries carry risk_policy btc-stop10-v1 and config_version in durable entry evidence. Trigger sale at 10% net loss using executable bids including buy/sell fees; mid-window retains +10% take profit and deadline from590s. Protective/deadline retries may execute after600s until900s, an explicitly disclosed exception to old cutoff. Early has stop only, otherwise holds to settlement. Entry cost+fee <=5USD; conservative fee reserve may reduce size or reject orders below minimum. Full-sale delayed FOK can fail; stop is not a guaranteed maximum loss. Old entries retain old definitions, old results never rewritten. Late stays paused; ETH and wallet-copy rules unchanged. This is user-requested PAPER risk policy, not optimized or proven profitable and not exact Mitch Binance v8.

120 Python tests passed including tighter threshold versus legacy, stale/no-depth rejection, failed arrival/retry after minute10, fees and no double settlement; JS syntax and wallet/export cases pass. Publication does not confirm Mac deployment. Require worker0.6.1 and fresh export. No live orders.

---
# v0.6.0 — 2026-09-29: forward wallet-signal PAPER copying

Implemented isolated buy/sell copy experiment for the three original public wallets, recognized BTC/ETH5m/15m markets. Three virtual500USD benchmarks, <=5USD all-in, one position each,15/30USD gross-loss caps. First source SELL exits full copied lot; NOT exact proportional source sizing or partial exits and NOT Mitch v8 Binance model. Delayed new-book FOK simulation,50% depth, both fees, no historical backfill, official resolution plus300s cash delay. No real orders. After the user requested analysis/correction of losing late-v1 on Sept29, its new BTC entries are also suspended (STRATEGY_RETIRED); thresholds and loss history retained, no claim of repaired profitability. Early and value baselines remain unchanged. Read EXPERIMENT-WALLET-COPY.md.

Dashboard exposes Copy accounts, charts/journal and Wallets copy decisions/errors; reports separate cumulative vs daily outcomes. Wallet discovery continues hourly without auto-copying candidates. Synthetic preview remains removed. Publication and Mac deployment are separate; require0.6.0 plus current wallet_copy_execution to confirm operation. Earliest trades only after activation; no fabricated pre-install history.

Validation:118 Python tests including12 copy tests passed;5 JS export and8 wallet panel scenarios passed; JS syntax valid. This does not validate actual exchange fills or guarantee profits.

---
# v0.5.3 — 2026-09-29: visible wallet observation and discovery; BTC baseline retired

106 Python tests passed;7 wallet panel rendering scenarios,5 JS export cases and app.js syntax passed. Full browser rendering and Mac deployment are not yet confirmed. Supersedes prepared but unpublished0.5.2 below.

Dashboard now shows selected account, trade count and decision reason. No settled trades is labeled explicitly instead of displaying zero as a performance result. Actual realized zeros/losses remain unchanged. A Wallets section exposes all three observers, read timestamps, stale/error states, recorded counts, recent activity and Value Surface status. ETH view directs to the shared BTC observer. Backend snapshot and private hourly export expose discovery state.

New read-only hourly CRYPTO top50 WEEK/MONTH leaderboard intersection produces UNVERIFIED candidates with positive reported PnL/volume in both periods. No automatic copying, no verified profit claim or continuous AI learning. Preserve scan history and last-success state on API errors. See EXPERIMENT-WALLET-DISCOVERY.md.

BTC mid-window-v1 new entries retired; existing positions, settlement and losses retained. Rename misleading Mitch label. Other accounts/risk limits unchanged. Mitch exact replication and copy execution remain NOT implemented; unavailable original code and unspecified fast-move/copy rules prevent claiming identical behavior.

Private export2026-09-29T16:06:08Z confirms Mac0.5.1, fresh worker, three POLL_OK observers, recorded event counts0/579/1857, Value Surface WAITING_VALID_PROBABILITY. This is evidence of observation, not copy trading or current0.5.3 deployment.

---
# v0.5.2 — 2026-09-29: retire misleading BTC mid-window baseline

User explicitly requested withdrawal of BTC mid-window-v1. Worker blocks new entries with STRATEGY_RETIRED, retaining existing exit handling, official settlement, accounts and loss history. Remove misleading Mitch name. ETH and other experiments remain unchanged; no live trading or risk increase. Publication is not Mac deployment.

Mitch's stated v8 (3–5 minutes,55–80c favourite,Binance25USD direction,ask+2c FOK,hold settlement) is NOT implemented by mid-window-v1. Exact replacement remains blocked: unavailable original source; undefined fast-adverse-move interval, precise favourite/opening source conventions and current wallet-copy/position-sizing/exit/probability rules. Do not silently invent these or present wallet observation as copying. The three public-wallet observers and independent Value Surface experiment remain in source; current Mac execution needs a fresh export.

---
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



