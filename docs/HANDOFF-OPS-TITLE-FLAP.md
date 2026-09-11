# Copy Lab — split-flap title, take 2 (2026-09-11)

**Local:** http://127.0.0.1:8805/ops/now.html?v=1043  
**Stamp:** `BUILD 10:43 UTC`  
**Executor:** `@PolyCop_BOT` only. Copy **off**.

---

## Executive summary

Fade-in was too weak; the first flap pass looked like static text plus a gray slab on the red line (broken shine overlay). The headline is now a **solari board**: each glyph sits in its own tile with a split line, rolls, and locks. Last line stays red. After lock, one letter on the red line ticks every ~7s so the board does not die as plain type. PL↔EN and return to **Co robić** replay it. Hunt refresh does not. Reduced-motion = static sentence. Copy off.

---

## What changed and why

- Removed the `mix-blend` shine on `włączasz.` / `copy.` — that overlay was the gray rectangle.
- Tiles + 3D `rotateX` flip so the motion reads as a board, not opacity.
- Slower roll (~2s) so you can actually see glyphs lock.
- Idle tick on the last line; replay on language and when coming back to the Do tab.

## Numbers

Copy still off. Cash ~$39.08. Live hole −$13.58. No PolyCop change.

---

## Changelog

```
2026-09-11  10:43 UTC  Solari-tile title; drop shine slab; idle tick; wrap by word. Copy off.
```
