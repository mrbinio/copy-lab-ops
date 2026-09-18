# BTC Lab — paper research v0.2

A standalone BTC 15-minute research service and bilingual dashboard. This directory and the sibling `/lab` website are independent of the older dashboards and the sports/copy-trading project.

**Status: v0.2 adds rule-specific TWAP60 paper research. The user has confirmed local macOS startup and feed connectivity for v0.1; v0.2 still requires the local update. Public Pages remains an interface preview.** No wallet, Kraken integration, signing key, deposits, withdrawals or live order submission are implemented. There is no switch in this version that can enable real-money orders.

## Run locally

Python 3.12 recommended (core tests also run on 3.11). From this directory:

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python3 -m unittest discover -s tests -v
LAB_LOCAL_DEV=1 python3 -m lab.server
```

Open `http://127.0.0.1:8080`. Local development binds only to loopback. Start the public-data collector in a second terminal:

```sh
. .venv/bin/activate
python3 -m lab.worker
```

The collector needs public HTTPS to `gamma-api.polymarket.com` and `clob.polymarket.com`, plus WSS to `ws-live-data.polymarket.com`. Access errors leave the system degraded; they never trigger synthetic trades. No API key is required. Starting partway through a window normally skips that window because the opening tick was not observed.

## What is implemented

- Public Gamma market discovery, explicit outcome/token mapping, source rule hash, current fee metadata.
- Chainlink spot and 30/60-second TWAP collection over RTDS, receive/source timestamps and disconnect markers. TWAP60 is used only for the exact supported BTC 15-minute market description and matching event start/end timestamps. TWAP30 remains recording-only. Spot and TWAP60 use separate reference histories and model datasets.
- Both outcome depth snapshots; delayed arrival snapshot, fixed price cap, 50% depth haircut, full-notional-or-no-fill simulation, minimum size and tick checks.
- A transactional SQLite ledger with integer microdollar amounts, independent virtual accounts, duplicate protection, single writer process lock and restart persistence.
- Official CLOB winner reconciliation. Provisional BTC moves never settle tickets. Five-minute delayed **simulated** cash release, separate pending payout and cash balances.
- Three independent paper accounts: value candidate, late directional baseline inspired by Damian, early directional baseline inspired by Mitch. These two baselines are reconstructions, **not exact reproductions** of the original engines.
- A small regularised logistic challenger, frozen first-200-window chronological 140/60 train/validation split; validation against book Brier score; subsequent windows form forward evidence. It can activate only a paper candidate. It cannot enable live orders.
- Read-only authenticated dashboard/API, EN/PL, responsive mobile layout, paper trade journal, skip reasons, model sample progress, report export, independent freshness fields.
- Docker Compose and HTTPS reverse proxy configuration, bounded process crash restart, backup helper, operator pause file and daily report endpoint.

## Research rules and deliberate boundaries

Each strategy has a **separate $500 virtual research balance**, $5 entry notional and fees outside notional. These are not the user's real holdings. Entries are capped at 1.1% of initial research capital all-in, 3% rolling 24-hour gross losses, 6% rolling seven-day gross losses and an 8% realised peak drawdown budget. The prospective full loss is reserved against each limit. One open or pending-redemption position per strategy; at most one position per strategy per market. A risk pause is not automatically cured by increasing capital.

For the value candidate: price .80–.92, fixed limit at most decision ask + .01, a .03 probability uncertainty deduction and .02/share remaining edge after fees. **v0.1 initially restricts the model to 115–125 seconds remaining** because training observations are recorded at 119–121 seconds. This is narrower than the proposed 180-to-30-second experiment; extrapolation to untrained horizons is not permitted.

The late baseline buys the leading side with a $50 reference distance, 30–300 seconds remaining, price .80–.955. The early baseline uses the same distance, 600–780 seconds remaining, price .60–.64. Both are hypotheses without an asserted probability or profitability.

For TWAP60, the opening reference must be a captured observation from `crypto_prices_twap_sixty` at the exact opening millisecond. Prices retain the E18 decimal string for direction/distance comparisons; floating-point values are used for charting and research features only. The recognized rule is pinned to the complete Gamma description observed on 2026-09-18, including the BTC/USD 60-second Chainlink stream URL, with matching event start/end times. Unknown or changed rules remain blocked. No nearest tick, spot substitution or inferred historical opening is used. Starting mid-window normally skips that window; a new opening can be captured at the next boundary if the feed is intact. Official CLOB winners, not predicted TWAP endpoints, settle positions.

A $100 live account under a 1% all-in risk rule has a $1 risk budget. A five-share order at .80–.92 costs approximately $4–$4.60 before fees, if that market's current minimum is five shares. The service must not silently round up the future live budget. The right next step is to measure minimum-order feasibility in paper, not move money now.

## Always-on deployment

**Infrastructure budget ceiling: EUR 15/month, separate from trading capital.** Planning allowance: up to EUR 10 compute, EUR 3 encrypted off-host backup, EUR 2 contingency. These are cost caps, not provider quotes. No paid AI in the execution path, no paid data, and no server has been purchased. Reassess if an actual offer including applicable tax exceeds the cap.

Use a permitted-region Linux host with Docker Compose, approximately 2 vCPU / 2–4 GB RAM and 40 GB disk. A server account and deployment access are still required; GitHub Pages cannot run this Python process continuously. Do not bypass venue restrictions by choosing a host location.

1. Point an owned hostname to the host; allow ports 80/443 only from the internet. Use SSH keys for administration. Keep the app port private.
2. Clone this repository on the host and enter `btc-lab`.
3. Copy `.env.example` to `.env`, set the hostname, and run `python3 deploy/password.py` locally on that host. Store the generated password privately and place only its hash in `.env`. Never reuse a public client-side dashboard password.
4. Run the tests, then `docker compose up -d --build`.
5. Check `docker compose ps`, `/healthz`, the authenticated dashboard, raw samples, fees, rule parsing and exact opening capture. A successful web page load is not a successful data-feed test.
6. Configure an independent external monitor for HTTPS `/healthz` every 60 seconds and an approved notification destination. Neither monitor nor notifications have been activated by this release.
7. Schedule encrypted off-host database backups and restore drills. The helper uses SQLite's backup API; copying a live database file directly is not a safe backup procedure.

The container starts worker + read-only API and exits if either child exits. Compose permits five failure restarts; manual review is required after repeated crashes. Docker `unhealthy` by itself does not restart a process. A data fault continues recording/retrying where possible, blocks invalid entries and remains visible to the monitor. A ledger conflict/invariant error persists a `PAUSE` file for operator review.

### Pause and recover

```sh
docker compose exec lab touch /data/PAUSE
docker compose logs --tail=100 lab
```

Pausing blocks new entries; reconciliation still runs. Investigate the cause, audit the ledger and restore valid feeds before removing `PAUSE`. Preserve the database when recreating containers. Never use `docker compose down -v` on a running experiment.

### Data volume and backups

v0.1 stores raw observations in SQLite so the first deployment is easy to audit. Disk checks must be monitored. Long-term compressed Parquet export/retention is a pending gate before a multiweek unattended run; do not delete raw evidence to conceal gaps. `deploy/backup.py SOURCE DESTINATION` creates a consistent snapshot and checks integrity. Encrypt and transfer it using the chosen host's backup system. No backup destination is invented or configured here.

## Remote dashboard

The sibling `/lab` folder is suitable for the existing GitHub Pages host. It shows **NOT CONNECTED** without a real backend; the optional **Preview interface** button generates clearly labelled synthetic design data. Preview values are never written to the research database.

The deployed Python service hosts those same assets with its `/api/state` and `/api/report` endpoints, protected by HTTP Basic authentication behind Caddy HTTPS. There are no control/order endpoints. Public Pages should remain a sanitised interface preview; do not commit private runtime snapshots into a public repository. Client-side JavaScript passwords are not access control.

## Verification and remaining promotion gates

Local automated tests cover fee arithmetic, price caps, full-size fills, depth haircut, minimums, token mapping, stale/future data, concurrent duplicate entry, atomic rollback, restart, separate pending payouts, idempotent redemption, conflicting outcomes, risk limits, HTTP authentication, disabled POST order endpoint and a complete mocked collection/arrival/settlement cycle.

Remaining before a trustworthy forward experiment:

1. Deploy to a persistent host, verify actual public endpoints and payloads. The development environment's public API connection timed out; production connectivity has not been demonstrated.
2. Audit per-market opening/settlement rules against the actual market and measure opening-tick coverage. The TWAP60 route is implemented in v0.2; measure exact-boundary coverage and verify behavior on the Mac after updating.
3. External heartbeat alerts, encrypted backup restore, disk/clock monitoring and raw-data retention.
4. Full websocket CLOB capture and independent Nautilus golden-replay parity. Nautilus is **not yet integrated**, and this release does not claim exchange-exact fills.
5. Whole-window chronological research, blocked uncertainty estimates, execution stress, fees/rounding validation against actual responses, and untouched forward results. The small model's holdout Brier gate is an initial diagnostic, not evidence of profit.
6. At least the proposed four-week / 300-trade initial review, extended whenever uncertainty remains. Then a separate decision about a capped venue-valid real-money technical test.

## Current primary references

- [Market metadata and fee schedule](https://docs.polymarket.com/market-data/market-details)
- [Taker fees](https://docs.polymarket.com/trading/fees)
- [RTDS reference streams](https://docs.polymarket.com/market-data/realtime-data)
- [Chainlink TWAP and reconnect limitations](https://docs.polymarket.com/market-data/chainlink-twap)
- [Nautilus Polymarket integration](https://nautilustrader.io/docs/latest/integrations/polymarket/)
- [GitHub Pages is static hosting](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages)

Daily assistant reviews should read this file and `PROJECT_STATE.md`, inspect code/status, and propose improvements. They are research reviews, not host uptime monitoring or a license to change live risk.

## v0.2 TWAP research interpretation

The early/late baselines keep the existing price/time/distance and risk limits, now applied to the market-specific reference. They may produce paper signals before the logistic model has 200 labelled TWAP windows. The logistic model uses only rows with the same `feature_schema`; old spot rows never train a TWAP candidate. Its features remain an empirical research hypothesis, not an analytical TWAP probability formula. Histories reset on disconnection or a source gap above ten seconds; missing data is never replayed synthetically.

Accounts and ledger history are preserved across upgrades. Each new paper position records config version, reference topic, feature schema and exact opening evidence. Account totals may span versions; do not attribute legacy totals to v0.2. No profitability or Nautilus replay parity is established.
