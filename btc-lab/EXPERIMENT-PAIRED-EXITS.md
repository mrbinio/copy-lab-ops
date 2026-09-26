# Paired exits v1 — registered 2026-09-26

Status: implementation for PAPER only. Mac deployment and performance unconfirmed.

## Question and frozen definition

For the same future accepted mid-window-v1 purchases, does a +15% net profit
trigger / -10% net loss trigger improve net results and realised drawdown against
the existing +10% / -20% triggers? No claim of an optimal threshold or profit.
Both use cost plus entry fee as basis; entry fee and sale fee are included in net.
Both attempt a time exit from elapsed 590s and stop attempting sales at 600s.
Unfilled positions await the official outcome, with full stake at risk.

These are two research arms, not new funded accounts or live orders. Entry
selection and risk budgets belong to the existing baseline. Thus results are
conditional on its accepted entries, not a standalone portfolio backtest.
Existing 31 historical mid-window trades are exploratory evidence only; no
retroactive enrolment, profit resets or parameter selection on forward data.
Mitch's actual v8 (3–5 minutes, hold to settlement) is a different hypothesis.

## Execution and evidence

Both arms consume the same collected REST snapshots, without extra requests or
sleeps. A trigger cannot fill on its decision snapshot. The next eligible
snapshot must arrive at least 250ms later, carry a strictly newer source timestamp,
and be fresh within 3s. Actual polling latency (normally seconds, not guaranteed
250ms) is recorded. Fixed floor from decision depth, 50% depth haircut, full
quantity or no fill, current verified fee schedule, tick and minimum size checks.
No quote chasing or partial-fill realism is claimed. Stop trigger is not a cap
on realised loss. The paired baseline has polling latency and is intentionally
reported separately from the existing production PAPER account's realised trades.

SQLite exit_comparison retains source position id, arm, entry basis, pending
intent, decision/arrival timestamps, fee rate, fills, sale fee and net result.
Pending intents survive restarts. Both arms must be completed and valid to enter
the primary paired comparison. Observation gaps >10s before the sale cutoff,
stale books or execution blocks invalidate ranking; affected rows remain visible.
Missing official labels leave an unresolved position rather than a guessed result.
Worker reconciliation includes unresolved research markets even if no model
example exists. Raw books continue in the existing observations table.

Hourly private JSON includes exit_comparison and exit_comparison_error. Dashboard
daily downloads include exit_comparison_cumulative (clearly cumulative, not a
daily total). Rows are microdollars; summary amounts are USD. At most 1000 rows
are exported, with an explicit truncation flag; database history is retained.
Research does not appear as additional trades in the existing trade journal.

## Evaluation gate set before forward results

One planned comparison. Review after at least 100 completed valid pairs spanning
at least 14 calendar days; this is a review gate, not proof of readiness. Report
all enrolled, invalid and unresolved pairs; investigate >5% invalid coverage
before drawing conclusions. Summarise paired net difference by market and by day,
costs, realised drawdown, worst loss and latency distribution. Use day-block
resampling for uncertainty; adjacent windows are not assumed independent.
Candidate qualifies for further PAPER validation only if net PnL is positive,
net difference favours candidate with a 95% interval wholly above zero, and its
realised drawdown does not exceed baseline. Otherwise retain as inconclusive or
reject; do not tune on these data. This does not authorise live trading.

## Installation

Use the pinned existing Mac installer for this commit. It preserves port 8769,
credentials and SQLite data, tests before restarting and backs up the database.
Expect the opening reference to be absent until the next fully observed window.
Confirmation: new private export worker version 0.3.1 and an exit_comparison
object whose updated_at advances. Pairs stay zero until a new baseline entry is
accepted. Old hourly reporter is refreshed by the installer.
