# Copy Lab — hunt 24/7 loop (2026-09-10)

**Site:** https://mrbinio.github.io/copy-lab-ops/now.html  
**Stamp:** `BUILD 12:28 UTC`  
**Executor:** `@PolyCop_BOT` only. Copy **off**.

---

## Executive summary

Damian asked for hunt 24/7. GitHub cron twice an hour was skipping slots (last tape 09:59 UTC, then idle). Hunt now runs as a **~5.5 h loop** on Actions, ~10 min pause between cycles, watchdog every 20 min if the job died. Still **does not enable copy**.

This is GitHub-hosted, not a VPS. A job can last at most ~6 h; the watchdog starts the next loop. If GitHub is fully down, hunt is down.

---

## What changed

- `scripts/hunt_loop.sh` — cycle hunt → publish JSON → pause 10 min. Pulse stays `running` for the whole loop.
- `.github/workflows/hunt-pages.yml` — timeout 350 min, cron `7,27,47 * * * *`, concurrency group `copy-lab-hunt`.
- Board copy no longer says “twice an hour / :20 and :50”.

---

## Numbers (unchanged)

Cash ~$39.08. Hole −$13.58. Antblack Paused, 86shin Paused.

---

## Next decision

Copy stays off. Watch the pulse: `HUNT DZIAŁA` means the loop is up.

---

## Changelog

```
2026-09-10  12:28 UTC  Hunt 24/7 loop on GitHub Actions. Pause 10 min. Copy off.
```
