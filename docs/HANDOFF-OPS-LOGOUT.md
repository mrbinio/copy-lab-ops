# Copy Lab — sign out / switch account (2026-09-10)

**Site:** https://mrbinio.github.io/copy-lab-ops/now.html  
**Stamp:** `BUILD 08:27 UTC`  
**Executor:** `@PolyCop_BOT` only. Copy **off**.

---

## Executive summary

The board had no way out of a session. After Damian or Mitch logged in, the other email could not take over without closing the tab. Header now has **Wyloguj / zmień konto** (EN: Sign out / switch account). It clears the session, empties the form, and returns to the gate.

Copy stays off. Hunt still does not enable.

---

## What changed

- Session keys `copy-lab-ok`, `copy-lab-email`, `copy-lab-role` are removed on logout.
- Firebase sign-out runs when Google auth is wired. Password fields are cleared so the next person types a different email.
- Gate copy: PL „Sesja skasowana. Wpisz inny email z listy.” / EN „Signed out. Enter a different allowlisted email.”

---

## Numbers (unchanged)

Cash ~$39.08. Hole −$13.58. PolyCop NY: Antblack Paused, 86shin Paused.

---

## Next decision

Copy stays off. Same WAIT bar as this morning.

---

## Changelog

```
2026-09-10  08:27 UTC  Header logout / switch account. Stamp BUILD 08:27.
2026-09-10  08:32 UTC  Published full UI to mrbinio/copy-lab-ops (b385589). Live stamp BUILD 08:27.
```
