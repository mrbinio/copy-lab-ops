# BTC Lab — current state

Release: 0.2.0. Scope: BTC paper research only. Sports, wallet copying, PolyCop and Telegram project excluded.

## Implemented

- Read-only collectors, three isolated paper books, transactional ledger, delayed depth simulation and official winner reconciliation.
- Transparent candidate model and reconstructed early/late baselines.
- Responsive English/Polish dashboard with an explicit optional synthetic design preview.
- Deployment configuration, authentication, tests and operating runbook.

## Operational truth

- A user-local macOS Intel/Monterey installer is available in `deploy/install-macos.sh`. It configures authenticated loopback access, a launch agent, bounded restart attempts and rotating logs. The user confirmed startup, HTTP 200, orderbooks, verified fee metadata and RTDS spot/TWAP streams on their Mac on 2026-09-18 (v0.1). Remote access remains a separate setup step.

- The user runs the service on their private Mac. No direct remote host access or external availability monitoring has been established.
- No actual private dashboard endpoint or external heartbeat monitor exists yet.
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

Rule-specific TWAP60 reference selection, exact E18 prices and opening evidence, separate model dataset schema, safe gap handling and explicit dashboard reference label. Baseline paper strategies retain existing risk and signal thresholds; no live orders. The complete supported rule text and 15-minute event times are checked. Unknown descriptions and absent exact opening observations still skip trades. v0.2 has not yet been installed or observed on the user's Mac. Local tests include TWAP versus spot divergence and official winner overriding provisional direction.
