# Copy Lab — live gate looked broken (2026-09-11)

**Site:** https://mrbinio.github.io/copy-lab-ops/now.html?v=0736  
**Stamp:** `BUILD 07:36 UTC`  
**Executor:** `@PolyCop_BOT` only. Copy **off**.

---

## Executive summary

Damian said the site does not work. GitHub Pages was up (`BUILD 06:55`). The live URL shows the login card. Without Firebase it painted a **red** “Wpisz email i hasło ze czatu” before anyone typed anything, so the gate looked like an error. That line is gone until a real miss (empty email, unknown email, wrong password).

Copy stays off. Antblack and 86shin stay Paused.

---

## What changed and why

- First paint: empty gate message. The lede already says email + password.
- Login and hunt refresh catch errors instead of dying silently.
- Phone header is static so it does not cover “Nic nie włączasz.”
- Tab switch scrolls to the top.

---

## Numbers (unchanged)

Cash ~$39.08. Hole −$13.58.

---

## Next decision

Copy stays off. Open the URL, email + page password, Otwórz.

---

## Changelog

```
2026-09-11  07:36 UTC  Gate: no red false error on first paint. Copy off.
```
