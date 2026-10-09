# HANDOFF — BTC Lab copy audit 2026-10-02

## Executive summary

Paper copy was dead for about 19 hours even though the source wallets were still trading. The copier was stuck on a backlog of old discovery wallets and never reached the four live seeds. That is now fixed on the Mac. Two paper copies landed at 12:10. Real Polymarket orders still failed until the CLOB client was upgraded to v2; the next qualifying copy will try a real buy again.

## What was wrong

1. **Copy queue starvation.** `wallet_copy.step()` took the oldest 100 unprocessed activity rows. After discovery was turned off, hundreds of inactive-wallet rows stayed unprocessed forever. Seed trades never entered that window. Last copy decision before the fix: 2026-10-01 17:28. Seeds were still trading this morning.
2. **Stale book killed copies.** Copy reused the 3-second book clock. 344 copy errors were `stale/future book`. Worker collection was also failing the same way.
3. **Own strategies were losing money.** BTC 3–7 v1/v2, value, and ETH 3–7 were still placing paper tickets while math said they lose at those prices.
4. **CLOB v1 is rejected by Polymarket.** `py-clob-client==0.34.6` posts order version 1. Venue answers `invalid order version, please use the latest clob-client`. Paper copies therefore never became real buys.
5. **Disk is almost full.** About 2.3 GB free. Database is 6.9 GB. A vacuum would fail.

## What changed

- Copy now processes only the four seed wallets. Inactive backlog is marked `SKIPPED_INACTIVE`. Stale seed backlog is marked old in one SQL pass.
- Copy book clock is 15 seconds. Worker book clock is 8 seconds. A stale book skips that cycle instead of taking the whole collector down.
- New entries off by default for mid-window v1/v2, value, value-surface, ETH 3–7. Early stays on. Dashboard cards have on/off buttons.
- Live CLOB uses `py-clob-client-v2==1.1.0`, FOK market buy with a price cap, and skips wallets whose paper result is negative.
- Copy ledger mismatch no longer kills the copier forever.

Not done: Alchemy → QuickNode (need your URL). Chain still waits for the public trade list for the exact price. No git push.

## Numbers after restart (12:10–12:13 Stockholm)

- Unprocessed copy rows: 9180 → 1.
- Marked old on restart: 8889. Inactive skipped: 337.
- Paper copies after fix: 2 (`0xeebde7a`, about $5 each).
- First real order attempts with the old client: 2, both rejected (version).
- CLOB v2 initialized at 12:12:45. No new supported-market copy in the next minute (source was on other markets or already had an open copy).

## Next decision

1. Leave live copy on for the two plus wallets (`0x162174…` +$2.71, `0xeebde7a…` +$5.11). Next qualifying BTC/ETH 5m/15m buy will spend up to $5 real.
2. Free disk space. Do not vacuum until there is more than 7 GB free.
3. If you have a cheaper WebSocket URL, send it. Alchemy stays until then.
