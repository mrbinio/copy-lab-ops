# Copy Lab — English brief no longer mixes Polish (2026-09-11)

**Site:** https://mrbinio.github.io/copy-lab-ops/now.html?v=1008  
**Stamp:** `BUILD 10:08 UTC`  
**Executor:** `@PolyCop_BOT` only. Copy **off**.

---

## Executive summary

The English **What to do today** card was interpolating Polish gap text (`jeden event`, `za mało filli`) into `path_en`. Lab now writes `missing_pl` / `missing_en` separately. EN view also strips leftover Polish if a model mixes languages. Copy stays off.

---

## What changed

- `scripts/claude_solutions.py` English gaps
- `scripts/grok_x_filter.py` uses `missing_en` on the EN path
- `ops/dash-0827.js` `enClean` on the brief card

---

## Numbers (unchanged)

Cash ~$39.08. Hole −$13.58. Antblack and 86shin Paused.

---

## Changelog

```
2026-09-11  10:08 UTC  EN What to do today is English-only. Copy off.
```
