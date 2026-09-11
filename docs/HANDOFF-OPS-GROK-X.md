# Copy Lab — Grok X filter after Claude (2026-09-11)

**Site:** https://mrbinio.github.io/copy-lab-ops/now.html?v=0855  
**Stamp:** `BUILD 08:55 UTC`  
**Executor:** `@PolyCop_BOT` only. Copy **off**.

---

## Executive summary

After each hunt cycle Claude writes the $5 path, then Grok searches **X** for the 3–5 closest nicks. It may mark `news_spike` (one match / vote / post) so the next hunt skips that nick. It **cannot** enable copy, clear conc > 0.45, candles, or CopyGrade Avoid.

Without `XAI_API_KEY` the card says the X filter is waiting. Same pattern as Claude: secret on `mrbinio/polymarket-copy-lab`, then the 24/7 job can call xAI.

---

## What changed

- `scripts/grok_x_filter.py` after `claude_solutions.py`
- `hunt_next.py` skips `x_skip` usernames
- Workflow env: `XAI_API_KEY`
- Board: **Filtr X** on Co robić

API: `POST https://api.x.ai/v1/responses` with tool `x_search`, last 14 days, `store: false`.

---

## Numbers (unchanged)

Cash ~$39.08. Hole −$13.58. Antblack and 86shin Paused. Closest almost still cassino (FINANCE, conc 1.00) until a new hunt+Claude+X cycle.

---

## Next decision

Add GitHub secret `XAI_API_KEY` (console.x.ai) like the Anthropic key. Copy stays off.

---

## Changelog

```
2026-09-11  08:55 UTC  Grok X filter after Claude. Copy off.
```
