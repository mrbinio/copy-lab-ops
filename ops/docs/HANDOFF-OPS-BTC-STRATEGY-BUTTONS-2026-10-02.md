# HANDOFF — Strategy on/off buttons 2026-10-02

## Executive summary

Paper strategy cards on the dashboard have on/off buttons. Losing paper strategies stay off. Early now also has a button, so Damian can kill it from the page if it turns bad. Copy-wallet cards still have no button.

## What changed

`pauses()` now lists every toggleable strategy, including `early-v1` (on by default). `late-v1` is retired in code and no longer shows a dead button. Live service restarted with the file.

## How to use

On a paper card: **Wyłącz nowe zakłady** stops new entries. Open tickets still settle. **Włącz nowe zakłady** turns them back on. Already off: BTC 3–7 v1/v2, value, value-surface, ETH 3–7. Still on: Early.

Copy cards (`copy-0x…`) are not these switches. Those are seed-wallet copies.

## Next decision

Add the same on/off on copy wallets only if Damian wants to kill a bad seed from the page.
