# Copy Lab — guide tab (2026-09-09)

**Site:** https://mrbinio.github.io/copy-lab-ops/now.html  
**Stamp:** `BUILD 21:48 UTC · guide tab`  
**Docs:** https://github.com/mrbinio/polymarket-copy-lab (private)  
**Executor:** PolyCop Telegram `@PolyCop_BOT` only. Copy stays **off**.

---

## Executive summary

Damian asked for a full **Instrukcja / Guide** tab (Polish + English) on the live board: what the page is, what each block is for, hunt cadence, gates, and who sets PolyCop. He also asked the lab (Cursor) to configure wallets so he would only tap enable.

**Answer:** the lab prepares **one** Active wallet + caps on the Board. This session cannot click Telegram (no PolyCop API). He must **not** tap **Turn On All Copy** — that enables the whole list (invorser). If gates ever pass, the tap is **Turn On Copy** on a 1-wallet roster. Not today.

---

## What changed and why

- New tab **Board | Instrukcja / Guide** (`#board` / `#guide`).
- Guide covers: purpose, each Board block, $5 / $15 / SL $31, 60d+90d+conc+CopyGrade, hunt `:20` and `:50` UTC, 15s page poll, never All Copy, GitHub docs.
- Cache-bust assets: `dash-2148.css`, `dash-2148.js`, `access-2148.js`. Safari: open `now.html`.

---

## Numbers (unchanged)

Cash ~$39.08. Live hole −$13.58 (invorser esports). If override later: 1 wallet, $5 caps, spend $15, SL $31. Hunt still has no name that clears 90d + book + CopyGrade together.

---

## Changelog

```
2026-09-09  21:48 UTC  Guide tab PL+EN. Who sets PolyCop: lab prepares card; Damian never All Copy.
2026-09-09  21:41 UTC  Dark board + How this page works. Hunt :20/:50 UTC.
```

---

## Next decision

Copy **off**. Finish Google login (Firebase web SDK still missing). Do not enable PolyCop until a WAIT name also clears 90d + gates.
