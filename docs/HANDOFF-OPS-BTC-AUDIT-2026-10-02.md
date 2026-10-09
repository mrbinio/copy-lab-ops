# HANDOFF — Full project audit 2026-10-02

## Executive summary

Real money spent is still $0; the $10 is not on Polymarket yet. Paper copy is down **$98.10** closed across eight wallets, with only `4096b159` positive at **+$4.97**. The audit found the root cause of the speed problem and it is fixed: the chain monitor's operator allowlist was stale, so the fast path had matched **zero** events since it was written. After the fix, on-chain detection lands in **0.25–0.86 s** and the first copies went out in **0.92 s**. The hourly report was failing twice over — dead release path plus a 954 kB payload against a 700 kB limit — and now uploads at 283 kB.

## What I changed after the audit

Damian chose the window-based gate, keeping both losing copy wallets on, and a repaired report job.

1. **`classify_transfer` no longer gates on the operator.** A seed fill is recognised by who receives or sends the token. `0xe111180000d2663c0091e4f400237545b87b996b` was added to `EXCHANGE_OPERATORS`, which is now diagnostic only.
2. **`ChainBridge` gates on the open market window.** A token that is not in a live BTC/ETH 5m or 15m window returns immediately and increments `off_market`. Previously an unsupported trade could hold a queue slot for the full 60-second poll; with matching finally working that would have starved the trades we can actually copy.
3. **Window set survives a gamma hiccup.** `_current_windows` returns the last good set instead of an empty list, so a transient API failure no longer drops every event.
4. **Fast-row size is real.** It was hardcoded to 5 shares; it now comes from the transfer value.
5. **Queue raised 10 → 30.** One `queue full` drop was observed in the first minutes; a seed can fill ten times inside a single block.
6. **Report trimmed.** `capped()` drops `skip_review` to a count and caps `recent_trades`, `recent_errors`, `recent_decisions`, `reasons` and `complete_set_observer.recent_windows`, each with an explicit `_truncated` marker. The hourly job was also repointed from the deleted release to `b009e2b8b429-…`.

Verification after deploy: 8 of 8 chain inserts under one second (0.25 / 0.40 / 0.86 s), no disconnects, no dropped events, report `status.json` `{"ok": true}`. 186 tests pass.

## Root cause: chain-fast had never fired

`wallet_chain_monitor.EXCHANGE_OPERATORS` holds two addresses. A 120-second live probe on blockmachine captured **13 seed buys, all 13 operated by `0xe111180000d2663c0091e4f400237545b87b996b`**, which is not in that set. `classify_transfer` therefore returns no wallet and the event is dropped before `ChainBridge` is reached. All 13 transactions were later confirmed as `type=TRADE` rows in the Data API, so these are genuine trades, not transfers.

Consequence: `chain_fast` rows all-time = 0, `chain_accelerated` since restart = 0. Copy lag is entirely the REST path.

Other operators seen on the same contract in 120 s: `0xe2222d27…` (571), `0xa1200000…` (426), `0xada100db…` (176). The allowlist approach needs replacing, not extending — these look like rotating relayer addresses.

## Second finding: we cannot copy most of what the seeds trade

Seed activity in the last 3 hours: **2 171** trades in supported `btc/eth-updown-5m/15m`, **898** in markets the copier rejects — mostly hourly `bitcoin-up-or-down-october-2-2026-<h>am-et`. Copy events in 2 h include **195 UNSUPPORTED_MARKET**. We copy a subset of each seed's behaviour and that subset is the losing part.

## Numbers

| Item | Value |
| --- | --- |
| Real CLOB spend | $0 (every order rejected: deposit wallet flow) |
| Copy closed P&L | −$98.10 total; `4096b159` +$4.97, `3e6eba30` −$28.35, `365cf589` −$25.49, `207e77c2` −$21.53 |
| Open copy positions | 75 across 8 wallets (`3e6eba30` alone 30) |
| Paper strategies | `early-v1` +$3.39, `mid-window-v2` −$8.30, `late-v1` −$18.51, `mid-window-v1` −$24.22, `value-surface` −$4.75 |
| Copy lag before the fix | 6 copies: 2.09–6.14 s (see 1.12–4.84 s, send 0.45–1.4 s). None under 1 s |
| Copy lag after the fix | chain detection 0.25–0.86 s; first copies 0.92 s and 2.14 s |
| Chain cable | 0 disconnects since 14:06; previously 56/hour on drpc |
| Tests | 183/183 pass |
| Disk | 37 GB free (82% used); `lab.sqlite` 6.9 GB; ETH 2.0 GB; backups 17 GB |
| Prune backlog | >2 000 000 rows older than 48 h; clearing at ~48 000/hour, so ~2–3 days. File only shrinks on VACUUM |
| Copy event mix (2 h) | 2 011 SOURCE_TOO_OLD, 253 POSITION_ALREADY_OPEN, 195 UNSUPPORTED_MARKET, 59 NOT_BUY_OR_SELL, 31 MARKET_CLOSED, 30 COPIED_BUY, 1 COPIED_SELL |

## Ops defects

1. **Report sender dead — fixed.** `com.btc-lab.reports` ran `releases/06f178045f60-…/venv/bin/python`, deleted during the disk cleanup. 239 runs, last exit 78 EX_CONFIG. Repointing it exposed a second failure: the payload had grown to 954 275 bytes against the script's own 700 000 limit, so `publish()` raised before any upload. `wallet_copy_execution` alone was 584 kB, mostly `skip_review`. Now 282 578 bytes and `status.json` reports `ok`.
2. **CLOB auth noise.** Startup logs `POST /auth/api-key → 400 Could not create api key`, then the client initialises anyway. Harmless today because orders are rejected earlier, but it should be understood before real money flows.
3. **No root `.gitignore`.** `btc-lab/.gitignore` covers `.env`, `*.sqlite*`, `__pycache__`. The repository root has none, so `ops/` and any file dropped at the top level are commit candidates.

## Security check

No secret material is tracked. The only matching file is `btc-lab/.env.example` with empty values. The single long hex string in the repo is the `TransferSingle` event topic, not a key. Live `config.json`, the dashboard password hash, the CLOB private key and the report upload token all live under `~/Library/Application Support/BTC Lab/` and are outside the repository. The report token was never read during this audit: the failure was identified from the payload size alone. The dashboard answers `401` without credentials on `/` and `/api/state`.

## Git state

Branch `main`, level with `origin/main`, nothing pushed. Uncommitted: 17 modified files, `strategy_control.py` and its test, 8 handoffs under `docs/`, plus the untracked `ops/docs/` copies.

## Switch state (verified persisted)

`state.strategy_pauses` = `mid-window-v1: true`, `copy-0xeda9247…: false`, `copy-0x943cea…: false`. Everything else falls back to `DEFAULT_PAUSED`, so `mid-window-v2`, `value-v1`, `value-surface-paper-v1`, `eth-mid-window-v1` and `late-v1` are off; `early-v1` and the other two copy wallets are on. The buttons do persist. Note that the two explicitly re-enabled copy wallets are the second and third worst performers.

## Next decision

1. Deposit $10 on polymarket.com with `…36a3bF01`, then wire the funder address and `signature_type=3`. Speed is no longer the blocker; the venue rejection is.
2. The remaining second inside a copy is our own guard: two order-book snapshots 0.25 s apart before a paper fill. That is the anti-stale-fill check. Do not weaken it without a decision.
3. Hourly markets stay uncopied. Supporting `bitcoin-up-or-down-…-<h>am-et` would roughly double the trades we mirror from these seeds, but the copy sizing, exit and settlement logic all assume a 5m/15m window. That is a separate pass.
4. Both losing copy wallets stay on by Damian's call: `copy-0xeda9247…` (−$25.49), `copy-0x943cea…` (−$21.53).
5. Add a root `.gitignore` before any commit. Nothing has been pushed.
