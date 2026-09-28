# Complete-set observer v1 — 2026-09-28

Observation only, not a trading strategy or evidence of realised arbitrage. BTC and ETH retain their separate existing accounts and limits. Worker 0.4.1 records existing REST snapshots even while strategy risk limits block entries. No additional network requests or orders. Both daily downloads and hourly private reports contain complete_set_observer and complete_set_error.

## Frozen measurement

Only recognised active-window rules and verified fee metadata. Both books must be <=1 second old, not future dated, with source and receipt skew <=250ms. This bounds skew; it does NOT create synchronized exchange snapshots. Same-market complementary tokens are mapped by the existing market parser. Equal quantity max(5 shares, both market minimums); 50% depth haircut; per-level tick validation; conservative upward microdollar fees. Maximum measured combined acquisition cost including fees 10 USD. Assumed operating reserve 0.02 USD per set, explicitly not verified merge/gas costs. Net quote = quantity - both purchase costs - both fees - reserve.

A positive quote starts a probe. Recheck at a later actual poll, at least250ms and at most5s later, both source timestamps newer and receipts after the delay. Freeze each leg's price cap. Record both/one/neither leg available and actual elapsed delay. One leg available records full-loss exposure and an explicitly optimistic same-snapshot unwind diagnostic using bid depth and sale fees; this is NOT delayed liquidation or realised PnL. Independent FOK orders are not atomic. Restart discards pending probes; no backfill.

One aggregate row per observed market persists in complete_set_windows. Last192 windows exported, entire table retained. Counts are repeated snapshots, not distinct independent opportunities. Repeated positive delayed checks must not be summed as profit or capital turnover. Raw books already remain in observations. Freshness must use updated_at; an old aggregate is not an active collector. REST polling misses fast opportunities and cannot establish executable edge.

## Decision gate

First review after7 days of recording: coverage, distinct positive windows, duration, skew, depths, minimum orders and orphan exposure. Zero valid positive windows => reject this implementation as an actionable candidate, not proof that no arbitrage exists anywhere. Positive quotes => only justify a timestamped WebSocket recorder and sequential-execution replay; not live trading. Require independently measured merge/collateral costs, budget reuse timing and conservative failed-second-leg liquidation before any net performance claim. A100USDC wallet is separate from virtual500USD accounts;10USD measurement size is not permission to risk10USD live.

## Large-loss diagnosis and next research boundaries

Early/Late hold to resolution: losing the full5USD plus fee is designed behaviour, not by itself a ledger bug. At100USDC that is over5% per ticket. Do not port paper sizing into live. Existing paired exit experiment remains frozen and preserves full-loss cases when sales fail; don't claim stop guarantees. Retain losses and risk pauses. Do not lower stop thresholds after inspecting these same trades.

Research beyond direction bets: complete-set mispricing first; market-making/rewards only after queue/adverse-selection data; longer crypto windows and non-sports prediction markets require separate rules/cost/liquidity inventory. Spot crypto/FX strategies are not interchangeable with prediction contracts and need separate data, venue costs and risk design. None is implemented or declared profitable by this release.

Sources checked2026-09-28: https://docs.polymarket.com/trading/positions/manage ; https://docs.polymarket.com/trading/fees ; https://arxiv.org/abs/2508.03474 ; https://arxiv.org/abs/2607.26245 . Historical research is not proof of present achievable returns.
