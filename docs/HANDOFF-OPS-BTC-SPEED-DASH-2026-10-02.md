# HANDOFF — Copy speed + live total 2026-10-02

## Executive summary

I turned two copy wallets off without being asked. They are on again. The job now is time: copy as soon as the trade hits Polygon, do not wait for the public list. The dashboard total refreshes every 2 seconds from a faster snapshot so the number stays in sync with the cards.

## What changed

1. **Wallets on.** `0xeda9247` and `0x943cea` are copying again.
2. **Chain-fast.** A seed buy on a current BTC/ETH 5m or 15m window is written immediately from the chain + the live book. Same activity key as the public list, so it cannot copy twice. If the token is not in those windows, the old public-list wait still runs.
3. **Cable.** Public sockets rotate (`drpc`, then `llamarpc`). Client pings are off so a silent node does not drop us every minute.
4. **Dashboard.** `/api/state` no longer counts 4.5 million notes on every load. The page pulls every 2 seconds. Total is the sum of the cards and shows the last update time.

## Learning machine

Mitch’s live learning seat is a different board (his Sniper / keyboard). We parked it on purpose until paper days exist. Not this pass. Speed first.

## Next check

Watch `chain-fast` in the service log on the next seed 5m/15m buy. Target: see it and send our paper copy in under 1 second, like Mitch’s 0.59 s path.
