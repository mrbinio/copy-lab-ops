# Skip review v1 — 2026-09-30

New forward-only skip evidence records original event, source/first-seen/decision timestamps and latency. Price/age rejection records the decision book already fetched; missing books stay null. A separate bounded background task reviews at most five expired skipped BUY signals per cycle against an official closed CLOB market with exact condition/token matching. Failures retry; completed reviews are durable and deduplicated. Report wallet_copy_execution.skip_review exposes latest100 records, total and truncation.

Outcome is NOT counterfactual profit: source_side_won records the market outcome, counterfactual_pnl stays null. No assumed execution at source price, no ledger or risk-limit changes. Original source history is not backfilled. Rejected SELLs remain in decision evidence, not the BUY outcome queue.

This is not complete Mitch replication. Polling remains30s, BUY age10s and price band +/-3c unchanged. Mitch states ~1s copying and >+10c skip; downside threshold and scoring method unspecified. Delayed alternative fills and copied-sale replay are still required to measure economic cost of skipped signals. No UI panel added; data available in existing exports. Publication is not Mac deployment.

Validation:16 wallet-copy/skip tests and4 watchdog tests pass. Full141-test run had one timing-sensitive watchdog timeout; isolated retry passed. No live orders.
