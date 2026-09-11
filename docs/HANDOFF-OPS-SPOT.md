# Copy Lab — live spot prices on the board (2026-09-11)

**Site:** https://mrbinio.github.io/copy-lab-ops/now.html?v=0636  
**Stamp:** `BUILD 06:36 UTC`  
**Executor:** `@PolyCop_BOT` only. Copy **off**.

---

## Executive summary

Damian asked for a cryptocurrency price graph that updates continuously. GitHub Pages cannot push ticks, so the **open tab** talks to Binance: REST for the first paint, then WebSocket so BTC / ETH / SOL and the 3-hour / 1-minute line keep moving. If the socket dies, REST every 3 seconds. This is market context, **not** a copy signal. 5-minute candle wallets stay NO.

Copy stays off. Antblack and 86shin stay Paused.

---

## What changed

- Co robić: **Ceny spot** — three live tickers + one line chart. Tap a coin to switch the chart.
- Feed runs only after login, stops on logout. GitHub does not host prices.
- FAQ: where the prices come from.

---

## Numbers (unchanged)

Cash ~$39.08. Hole −$13.58.

---

## Next decision

Copy stays off. The chart is for eyes, not for enabling a wallet.

---

## Changelog

```
2026-09-11  06:36 UTC  Live BTC/ETH/SOL from Binance on Co robić. Copy off.
```
