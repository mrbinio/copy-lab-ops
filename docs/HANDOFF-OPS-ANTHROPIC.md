# Copy Lab — Claude hunts the next $5 path (2026-09-11)

**Site:** https://mrbinio.github.io/copy-lab-ops/now.html?v=0746  
**Stamp:** `BUILD 07:46 UTC`  
**Executor:** `@PolyCop_BOT` only. Copy **off**.

---

## Executive summary

Damian wanted Anthropic to actually help find a reasonable way to earn, not just explain rejects. After each hunt cycle the lab now writes **Najbliższa ścieżka** + **Hunt teraz szuka** on Co robić. That plan steers the next leaderboard offsets. Copy still does **not** enable. Claude cannot say buy / Turn On Copy / deposit more.

No `ANTHROPIC_API_KEY` in this machine yet, so the first card is from lab numbers (same gates). When the GitHub secret exists and this hunt code is on `main`, Claude refines the sentences; `next_cats` / extra offsets still clamp to POLITICS…ECONOMICS.

---

## What changed

- `scripts/claude_solutions.py` → `ops/data/solutions.json`
- Hunt loop runs it after every cycle; next `hunt_next.py` goes deeper on the named cat (offset 250/300)
- Board brief: NIE WŁĄCZAJ + path + next search
- Fallback without a key still names the closest almost-wallet and where hunt looks next

This cycle’s numbers: closest almost is trueblueaussie (SPORTS) — still NIE (conc 1.0, 0 fills, <90d). Next hunt: SPORTS / POLITICS / FINANCE, not candles, not All Copy.

---

## Numbers (unchanged)

Cash ~$39.08. Hole −$13.58. Antblack and 86shin Paused.

---

## Next decision

Add GitHub secret `ANTHROPIC_API_KEY` on `mrbinio/polymarket-copy-lab` and put hunt scripts on `main` if Claude should run 24/7. Copy stays off until Damian asks to commit/push the lab repo.

---

## Changelog

```
2026-09-11  07:46 UTC  Solutions card + hunt focus. Claude optional. Copy off.
```
