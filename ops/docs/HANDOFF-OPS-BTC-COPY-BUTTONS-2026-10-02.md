# HANDOFF — Copy buttons and the −$86 total 2026-10-02

## Executive summary

The paper on/off buttons were already working. The −$86 total is old paper tickets plus copy losses. Copy cards had no button, so losing seed copies kept trading. Copy now has the same on/off. The two seeds that are already negative on our books are off. Mitch can still make money on the same addresses because he is faster and does not take every 5m/15m buy.

## What was wrong

1. **Total does not reset when you press Off.** Off only stops new entries. Late, BTC 3–7, value, and old copy tickets stay in the sum. No new paper entries since 12:09.
2. **Copy had no switch.** Dashboard total kept moving because `0xeebde7a` was still being copied.
3. **Same wallet, different result.** Our paper copy is 2–25 seconds late and buys every BTC/ETH 5m/15m signal. Mitch’s 0.59 s path buys closer to the source price and is pickier. Example today: source 37¢, our paper 3¢ after 25 s.

## Seed copy PnL on our books

- `0x162174…` +$2.71 — left on
- `0xeebde7a…` about flat closed, 5 open — left on
- `0xeda9247…` −$18.44 — turned off
- `0x943cea…` −$13.91 — turned off

## What changed

Copy cards have **Wyłącz nowe zakłady**. Live store paused the two losing seeds. Total line now says old tickets stay in the number.

## Next decision

Leave the two plus/flat seeds on until the chain cable is under 1 second, or turn `0xeebde7a` off from the page if today’s open tickets look bad.
