# value-surface-v1 and wallet-observer-v1 — 2026-09-29

Status: research instrumentation and advisory calculations, not an executing strategy or proven edge. No signer, keys, orders, capital transfers or automatic production parameter promotion.

## Continuous wallet research

BTC worker starts three independent asyncio polling loops, one per specified wallet, every30 seconds after completion, even with no activity. Public documented legacy GET /activity is used. All requests have the existing8-second timeout. Indexed chain activity is not direct blockchain subscription or guaranteed real-time delivery. Development access returned403; production connectivity/schema remains to be verified. Errors are not reported as inactivity.

Initial lookback24h; fixed end timestamp,120-second overlap, up to4 pages of500 rows. A page limit reports INCOMPLETE_PAGE_LIMIT and does not advance the cursor. A late indexed record older than overlap may be missed. Historical completeness is always false. Fingerprints include transaction hash/type/token/side/amount/timestamp; lack of log index can collapse identical fills. Do not calculate verified wallet profit from this table. Raw observations are retained in wallet_activity with first_seen and source_ts, survive restart and are deduplicated. First_seen is the earliest time OUR process knew the record, not an executable historic entry. API returns, transfers, splits, merges, rebates and external funding must be reconciled before any wallet ranking. No profitable-wallet label is assigned.

Hourly private exports contain statuses and latest100 observations, total count and truncation flag. This is bounded inspection, not a complete archive. No dashboard panel added. Authentication-protected /api/state contains research state.

## Independent probability, timing and sizing

BTC and ETH collect one first valid observation per elapsed minute per15-minute market, independent of existing strategy risk pauses. Reuse current normalized books and RTDS (no added book network requests). Store full two-sided snapshots with source/arrival times, reference, rule hash and signed volatility-normalized distance. Reject unverified rule/fees, stale reference/books, missing history. Discovery/reference failures remain explicit rather than fabricated samples.

Candidate population is separate per asset database, rule hash, elapsed minute and floor(z) bucket clipped[-4,4]. Prior official labels must be available before the new market START; current and future windows excluded. Each market counts once per cell. Minimum50 prior labeled windows per cell permits an UNVALIDATED estimate; it is not permission to trade.95%Wilson lower/upper bounds describe binomial uncertainty, not calibrated prediction intervals; regime dependence and many tested cells require forward/day-block assessment. Model ID hashes contributing market/label records. Definitions are versioned, never silently optimized on outcomes.

For each side compute conservative purchase cost at ask+1c (capped below1), fee and1c/share allowance; require lower-bound probability minus those costs >2c/share. Fractional Kelly (quarter Kelly, using lower bound) is capped at1% of the100USD scenario. Minimum order may make the candidate untradeable; never round size UP through the cap. Reject rather than increase risk. Compare net bid with upper probability bound+1c for an exit-value advisory. This is an economic hold-versus-sell comparison, not a guaranteed optimal stopping rule.

No candidate is marked executable: tick rounding, arrival-book depth, partial/nonfill, price changes and true exit inventory must be incorporated in a separate shadow execution stage. Existing paper accounts/thresholds and historical PnL are unchanged. Wallet behaviour is recorded independently, not fed into probability until timestamps/identity/coverage are validated.

## Next acceptance gate

Review recording coverage by minute, distinct markets, reference/book age and missing official labels. Then freeze ONE candidate cell/rule on a training-only period, reserve subsequent untouched windows, and compare net-after-cost forward performance and drawdown with no-trade and existing baseline. Report all examined cells (multiple-testing bias), invalid/missing windows and confidence by day. Reject missing coverage, nonpositive net advantage, or minimum-size incompatibility at100USD. Do not promote because50/200 samples or a calendar deadline was reached. This release prepares inputs/advisories; it does not claim this gate has passed.

## Deployment and verification

Existing macOS installer backs up both databases and preserves credentials/port. Additive tables only. Confirm worker0.5.0, recent wallet checked_at with POLL_OK or explicit ERROR, and opportunity_research updated_at/status for BTC/ETH in hourly export. No Mac access from the assistant and no deployment confirmation at publication. A403 must be diagnosed on the runtime; no proxy/geoblock bypass or credentials are requested.
