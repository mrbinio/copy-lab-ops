# Copy Lab — cash auto + kinetic title live (2026-09-11)

**Site:** https://mrbinio.github.io/copy-lab-ops/now.html?v=1105  
**Stamp:** `BUILD 11:05 UTC`  
**Executor:** `@PolyCop_BOT` only. Copy **off**.

---

## Executive summary

Kinetic title (letter clip + red scan) is on Pages. Cash box now refreshes from Polymarket activity on each hunt cycle, not from Telegram and not by typing. First check: **$39.08**, 0 events since the 9 Sep stamp, 0 open value. Copy off. Intro not built — waiting on Damian.

---

## What changed and why

`$39.08` was a lab stamp in `snapshot.json`. Hunt did not touch it. The board now sets `cash_usd` from that stamp plus Data API activity and `/value` positions. Wallet stays in `POLYCOP_WALLET` or local `configs/monitor.json`. Never in Pages JS.

Telegram bot balance is not a public API. A deposit that never hits `/activity` will not move the number until a trade or redeem shows up.

GitHub hunt needs secret **`POLYCOP_WALLET`** (same address as `poly_wallet`). It is not on the repo yet — without it the job prints `cash skip` and leaves the stamp.

## Numbers

Cash **$39.08**. Positions **$0**. Activity net since stamp **$0**. Live hole **−$13.58**. Antblack and 86shin Paused. Live hunt kept: **1050** checked, `2026-09-11T10:47:26Z`. Copy off.

## Next decision

1. Add GitHub secret `POLYCOP_WALLET` so 24/7 hunt can refresh cash.  
2. Intro after login: say yes or no (idea in chat, not built).

---

## Changelog

```
2026-09-11  11:05 UTC  Kinetic title live. Cash from Polymarket activity. Copy off.
```
