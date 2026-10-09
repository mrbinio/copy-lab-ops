# HANDOFF — Green tiles on top, 2026-10-05

## Executive summary

The dashboard already had “Plusy u góry”, but that sort used the paper-account number. A tile turns green from the number painted on it: the PAPER result for an active, test, or paused wallet, and the observation net for an observed wallet. Those two numbers are not the same, so a green observed tile could sit under a red one.

Automatic order now follows the color. Green tiles are first, highest result first. Tiles with no result stay in the middle. Red tiles go last. Drag order is still available as “Mój układ”. The first load after this change turns the automatic order on once.

## What changed and why

No trading rule, roster threshold, or account number changed. The card color and the sort key now share one function. A saved manual order from before this change is left in the browser, but the layout switches to automatic green-on-top the first time the new page loads. After that, “Mój układ” still sticks.

## Numbers

No ledger change. `clob_live` stayed false. The paper service was not restarted. Static files are read on each request.

## Changelog

- `lab/app.js` — sort by the same result that paints the tile green or red.
- `lab/index.html` — cache key `app.js?v=20261005-green-top`.

## Next decision

Refresh the dashboard. If a chosen drag order is needed again, use “Mój układ”. Live orders stay off.
