# Copy Lab — Claude on the 24/7 hunt (2026-09-11)

**Site:** https://mrbinio.github.io/copy-lab-ops/now.html?v=0746  
**Stamp:** `BUILD 07:46 UTC`  
**Executor:** `@PolyCop_BOT` only. Copy **off**.

---

## Executive summary

`ANTHROPIC_API_KEY` is on `mrbinio/polymarket-copy-lab`. Hunt scripts are on `main` (`77949bd`). After each hunt cycle GitHub runs `scripts/claude_solutions.py` and publishes `ops/data/solutions.json` to the board. The next cycle reads `next_cats` / extra offsets. Copy still does **not** enable. Claude cannot say buy, Turn On Copy, or deposit more.

The hunt job already in flight started before this commit, so the first Claude pass is the **next** loop.

---

## What changed

- Workflow env: `ANTHROPIC_API_KEY`
- `scripts/claude_solutions.py` after every hunt cycle
- `hunt_next.py` goes deeper on the named cat (offset 250/300)
- Pages data publish copies `solutions.json`

This cycle’s seed: closest almost is **cassino (FINANCE)** — still NIE (conc 1.00, 4 fills). Next hunt: deeper **SPORTS**, then POLITICS, FINANCE.

---

## Numbers (unchanged)

Cash ~$39.08. Hole −$13.58. Antblack and 86shin Paused.

---

## Next decision

Wait for the next hunt job to write `source: claude` on Co robić. If the card stays `source: lab`, check the hunt log for `solutions skipped` or an Anthropic HTTP error. Copy stays off.

---

## Changelog

```
2026-09-11  08:05 UTC  Hunt loop uses GitHub Anthropic secret. Copy off.
```
