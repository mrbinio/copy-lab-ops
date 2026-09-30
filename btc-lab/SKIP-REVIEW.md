# Skip review v2 / worker0.6.4 — 2026-09-30

Observer targets1s per-wallet cycles, measured from cycle start; sequential per-wallet requests, bounded pagination, error backoff2..60s. New persisted activity wakes copy execution via a shared event; fallback scan1s, publication throttled2s when idle. Public indexed API latency remains unbounded: not a promise of1s after chain execution. No direct chain subscription implemented.

For each newly rejected eligible BUY, capture an independent hypothetical5USD all-in ticket using current book, fixed decision ask+2c limit and a subsequent book after>=250ms and<=5s. Require advancing source timestamp, <=5s source age, minimum size and50% depth FOK; fee reserve included. Missing/stale/unfillable data produce unknown PnL, never an invented fill. Pause, invalid/error and >90s source-age rejections do not probe execution. No historical backfill.

Frozen scoring policy skip-hold-arrival-v1 holds to official resolution, subtracts purchase cost and fee. There is no sale fee because it does not sell. This is NOT the source-SELL copy policy, not portfolio returns and not evidence that a skipped real copy would win. Market outcome and cash-scale hypothetical PnL remain separate. Original copy accounts, risk caps and +/-3c/10s entry guards unchanged; Mitch's downside threshold still unspecified. No real orders.

Records are durable/deduplicated, background resolution is bounded and does not block new copies, concurrent updates merge under an immediate transaction. Exports include latest100 reviews/total/truncation; dashboard Wallets shows hypothetical results and delay. Legacy outcome-only records remain unknown, without retroactive fill fabrication.

Validate new release through worker0.6.4, observer poll_seconds1 and new skip_review records. Published source is not Mac deployment. No production latency measurement is available from development tests.
