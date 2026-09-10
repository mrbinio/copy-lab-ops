# Copy Lab — hunt 09:59 UTC check (2026-09-10)

**Site:** https://mrbinio.github.io/copy-lab-ops/now.html  
**Executor:** `@PolyCop_BOT` only. Copy **off**.

---

## Executive summary

The board’s “last hunt 2026-09-10 09:59 UTC” is real. GitHub Actions started the :50 UTC job at 09:51, finished 09:59 UTC (11:59 in Poland). **1002** new names, **36** simmed. Nobody cleared 90d + both windows + conc ≤ 0.45 + non-candle + CopyGrade. The file’s `pick` is **bbb17367162806** — do not paste. One Portugal market, conc 1.0, 76 days, 90d only +$4.8.

Copy stays off. Antblack and 86shin stay Paused.

---

## What the 09:59 run actually said

| Name | 60d | 90d | Why no |
|---|---|---|---|
| bbb17367162806 | +$21.1 | +$4.8 | conc 1.0, Portugal 27 Jun, 76d |
| citra | +$1.5 | +$6.4 | conc 1.0, LoL Worlds 2025 |
| SSCCAAMM | +$3.2 | +$2.7 | conc 1.0, Trump 2024 |
| N34 | +$34.4 | $0 | 90d dead |

GitHub cron after that (:20 / :50 from 10:20 UTC onward) had not fired by 12:17 UTC. GitHub often skips schedule. Not a Mac problem.

CI still runs the committed hunt script, so live `hunt.json` has no `journal` / `lanes` keys. The board tape falls back to the log.

---

## Next decision

Copy stays off. Do not enable bbb17367162806.

---

## Changelog

```
2026-09-10  09:51–09:59 UTC  GitHub hunt-and-publish. 1002 checked. No copyable name.
2026-09-10  12:17 UTC  Checked live hunt.json + Actions. Timestamp is real. Copy off.
```
