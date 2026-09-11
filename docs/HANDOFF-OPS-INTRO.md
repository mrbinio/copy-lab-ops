# Copy Lab — login intro + cash secret (2026-09-11)

**Site:** https://mrbinio.github.io/copy-lab-ops/now.html?v=1120  
**Stamp:** `BUILD 11:20 UTC`  
**Executor:** `@PolyCop_BOT` only. Copy **off**.

---

## Executive summary

After login, once per browser tab: ~1.5s black screen, Copy Lab wordmark, then the kinetic title and board. Skip exists. Hunt refresh does not replay it. Logout plays it again next time.

GitHub hunt can now read the PolyCop wallet from secret `POLYCOP_WALLET` (address only, not the page password). That is how cash stays in sync when the job is not running on Damian’s Mac. Copy off.

---

## What changed and why

Hunt on GitHub is a different computer. It cannot open local `configs/monitor.json`. The address goes in a GitHub secret so `refresh_ops_cash.py` can call Polymarket. The secret is not in Pages JS.

Intro is session-only. `prefers-reduced-motion` skips it.

## Numbers

Cash **$39.08**. Hole **−$13.58**. Copy off. Antblack and 86shin Paused.

## Next decision

None. Copy stays off.

---

## Changelog

```
2026-09-11  11:20 UTC  Login intro. POLYCOP_WALLET for hunt cash. Copy off.
```
