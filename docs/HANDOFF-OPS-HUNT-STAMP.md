# Copy Lab — hunt stamp caught up (2026-09-10)

**Site:** https://mrbinio.github.io/copy-lab-ops/now.html?v=1244  
**Stamp:** `BUILD 12:44 UTC`  
**Executor:** `@PolyCop_BOT` only. Copy **off**.

---

## Executive summary

The 24/7 loop was running, but the board still showed **09:59 UTC** because pulse goes live at job start and `hunt.json` only after a full cycle (~8 min). First cycle finished **12:39 UTC** (973 names). Damian looked at ~12:37, so the old stamp was still correct then.

Board now says **HUNT DZIAŁA od {start} · ostatni skończony {tape}**. Next loop (after this job) also pushes `hunt.json` every ~90s mid-cycle so the tape timestamp does not sit still for eight minutes.

Copy stays off. File pick is still a one-event reject — do not paste.

---

## What changed

- Pulse at t=0 no longer republishes the checkout `hunt.json`.
- Heartbeat publish every 90s during the loop (needs main; current job keeps the old script until it ends).
- Hunt keeps the last tape on disk while a new cycle scans.
- Board: running-since vs last finished.

---

## Numbers

Cash ~$39.08. Hole −$13.58. Antblack Paused, 86shin Paused. Last cycle: 973 checked, 12:39 UTC.

---

## Next decision

Copy stays off. Refresh the board. Next tape ~10 min after 12:39, then ~8 min to finish.

---

## Changelog

```
2026-09-10  12:39 UTC  First 24/7 cycle published (973 names). Copy off.
2026-09-10  12:44 UTC  Board shows loop start vs last finished tape.
```
