# Proportional copying: independent PAPER allocation proposal, 2026-10-01

Status: pure allocation/accounting functions implemented and 11 unit tests passed.
NOT wired to WalletCopy, NOT deployed, no claim of improved returns.
This is our documented policy proposal, not Mitch's private code or exact algorithm.

Current wallet_copy.py on main and chain-monitor-hybrid still uses fixed <=5USD,
one position per wallet and a full close on the first SELL. Those rules remain active.
The new module is intentionally isolated until source inventory and transactional
partial-lot persistence are implemented. Do not install this branch expecting
different dashboard behaviour.

Implemented:
- Sell the same fraction of a VERIFIED pre-event wallet/token position.
- Reject missing/inconsistent source inventory instead of treating any SELL as a full exit.
- Compute capacity for several positions within the same existing 5USD wallet exposure cap,
  retaining 15USD daily and 30USD weekly gross-loss caps and reserving open exposure.
- Allocate cost and entry fee exactly across partial sales, preserving integer totals.
- These are planning functions only; no book fills, persistent deduplication or orders.

Reproduce:
cd btc-lab/experiments/copy-proportional
python3 -m unittest -v test_copy_allocation
11 tests passed locally. These do not establish integration or profitability.

Remaining integration gates (assistant-owned, no dependency on Mitch):
1. Establish source wallet/token inventory at a known timestamp, reconcile all subsequent
   fills/transfers, handle late/missing/duplicated events and restarts. Public current
   positions after a SELL are not a pre-SELL balance.
2. Atomic persisted sale event + exact shares/cost/fees/proceeds updates. Failed FOK
   must not consume the local position; source state still advances independently.
3. Preserve existing historical positions/policies. Isolate new experiment accounts
   and identify policy in dashboard/export; no silent historical reinterpretation.
4. Test feed->decision->delayed fresh bid/ask->ledger->daily report including
   several buys, partial sells, out-of-order events, minimum size, restart and settlement.
5. Compare source versus PAPER execution with price, latency, missing/skipped events,
   fees and realized/unrealized PnL separately. No success claims from unit tests.

Unknown rules must be named as our choices, not attributed to Mitch.
