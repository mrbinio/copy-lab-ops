# Polymarket Copy Lab — Handoff for Mitch (v1.0 → v1.1)

**Author:** Damian  
**Date:** 2026-08-17  
**Purpose:** Document what changed after the first live eval, why, early v1.1 results, and the plan ahead — same spirit as your “save every change and why” workflow.

---

## 1. Executive summary

| | v1.0 | v1.1 (W1, live) |
|--|------|-----------------|
| **Goal** | Prove copy pipeline + dashboard eval | Narrow roster, cleaner attribution, safer caps |
| **Roster** | 8 wallets (mixed esport/sport) | **4 active** + 5 old **paused** (backup) |
| **Seed** | ~$53 USDC | ~$53 USDC (after top-up) |
| **Spend limit / wallet** | $40 | **$30** |
| **Fixed copy** | $5 | $5 |
| **Max Yes/No** | $5 | $5 (unchanged — critical) |
| **Eval window** | ~48h (extended informally) | **~21h** (closed early after LoL stress) |
| **In-window settled net** | ~**+$156** (34 resolved) | **+$15.94** (4 resolved, 4W/0L, 0 open) |

**Bottom line:** v1.0 proved the process works. v1.1 trades less often (fewer wallets) but with tighter risk controls. Early pace is slower than v1.0’s first night — expected, not a failure yet.

---

## 2. What we ran in v1.0

### Setup
- **PolyCop** execution only; local dashboard (`:8765`) for monitoring and in-window settled PnL.
- **Scout:** Polymarket 30d leaderboard → mid-tier filters → isolated backtests under PolyCop rules.
- **Genome:** `configs/v1.0.0.json` — 8 wallets, Fixed $5, ignore &lt; $20, prices 0.15–0.85, Total Spend $40, Max Yes/No $5.

### Roster (v1.0)
acorp, Skritopoolniy, sulumos, Sassy-Bucket, 0xE30E…, SineNooneEI, CORGI8, laozishudaosan

### Result
- **~+$156** in-window settled net over the eval period; **33–34** resolved positions.
- Process validated: scout → backtest → PolyCop → dashboard eval → withdraw profit to Kraken.
- **Issues learned:**
  1. **8 wallets** → hard to know *who* made money; correlated sport/esport nights (many “No” on same soccer slate).
  2. **Spend $40 × 8 tasks** → theoretical exposure far above seed; real constraint was cash, not a single shared cap.
  3. **Withdrawals** during eval reduced buffer; seed not protected.
  4. **UMA redeem latency** — Querétaro won at 0.9995 but stayed “open” ~12–24h (`redeemable: false`, status `proposed`). PolyCop Auto Redeem could not claim until Polymarket finalized. No Polymarket web account needed — bot redeems when allowed.

---

## 3. What changed in v1.1 and why

### 3.1 Roster: 8 → 4 active (5 paused, not deleted)

**Active (v1.1 W1):**

| Wallet | Why kept / added |
|--------|------------------|
| **acorp** | Top isolated backtest sim PnL in v1.0 roster; live contributor (e.g. Querétaro copy). |
| **Skritopoolniy** | #2 sim PnL in v1.0 backtests. |
| **sulumos** | #3 sim PnL; strong scout score. |
| **Iamnobody.Nobody** | **New** from fresh leaderboard scout + isolated backtest (**+$14.49** sim @ $30 spend). Replaces weaker v1.0 picks. |

**Paused (fallback — not deleted):**  
CORGI8, SineNooneEI, 0xE30E…, Sassy-Bucket, laozishudaosan  

*Reason:* If v1.1 underperforms, we can revert without re-scouting. **Did not use “Turn On All Copy”** so old wallets stay paused.

**Dropped from active (not in v1.1):**
- SineNooneEI, CORGI8, laozishudaosan — **0 sim PnL** in isolated backtests under our filters.
- Sassy-Bucket — positive but replaced by stronger Iamnobody scout result.
- 0xE30E… — 5th in v1.0 sim ranking; lower edge than top 4 + Iamnobody.

**Why not 5 wallets?**  
With ~$53 seed, 4 copies already approaches sensible exposure. A 5th wallet adds correlation more than edge at this bankroll. Revisit after **48h v1.1 eval** if net &gt; 0 and attribution is clear.

### 3.2 Bankroll & spend

| Parameter | v1.0 | v1.1 | Why |
|-----------|------|------|-----|
| Seed | ~$53 | ~$53 | Same PolyCop W1 wallet after partial withdraw + $30 top-up |
| Spend limit / copy task | $40 | **$30** | ~$10 buffer; less max open exposure per trader |
| Fixed amount | $5 | $5 | Unchanged — matches backtests |

### 3.3 Safety settings (verified on all 4 active tasks)

Every active copy task checked in PolyCop UI:

- Fixed Amount: **$5**
- Max Per Trade: **$5**
- **Max Per Yes/No: $5** ← prevents stacking multiple $5 on same outcome (v1.0 lesson)
- Max Per Market: **$5**
- Ignore trades &lt; **$20**
- Min / Max price: **0.15 / 0.85**
- Copy Buy + Sell: **ON**
- Reverse Copy: **OFF**
- Auto Redeem: **ON**

### 3.4 Monitoring

- Dashboard eval **stopped** for v1.0, **restarted** for v1.1 (clean window).
- Balance override synced from PolyCop (~$53.24).
- Genome: `configs/v1.1-esport.json`  
- Machine-readable log: `data/eval-log.json`

---

## 4. Final v1.1 results (~21h — eval closed 2026-08-17)

*Snapshot: 2026-08-17 ~20:20 UTC+2 — all positions settled, 0 open*

| Metric | v1.1 (final) | v1.0 (full eval) |
|--------|--------------|------------------|
| Settled net | **+$15.94** | ~**+$156** |
| Resolved | 4 | 34 |
| W / L | **4 / 0** | — |
| Open unrealized | **$0** | — |
| Copy state | **Stop All Copy** (paused mid-eval after LoL drawdown) | — |

**Settlements (in-window):**
- LoL T1 vs DN SOOPers — Game 1 Winner (T1) — **+$8.43**
- Liga MX cluster (América win / draw No / San Luis No) — **+$7.51** combined
- *(Querétaro +$1.24 from early window may fall outside closed-since filter in final API pull)*

**What happened mid-eval:** Four esport-heavy wallets correlated on LoL (T1 BO5, handicaps). Session looked **~−$10** unrealized with copy still on. **Stop All Copy** was correct. Final ledger recovered on T1 Game 1 redeem + Liga MX — **+$15.94** net in-window.

**Post-eval audit (fresh isolated sim under our filters):**
- **acorp** — only wallet with positive sim (~+$6.59); ~65% esport mix
- **Skritopoolniy, sulumos, Iamnobody** — **$0 sim**; 86–100% esport; 2 shared markets between active wallets

**Interpretation:** Process worked (positive close), but **roster choice was wrong** — too correlated, weak re-validation at go-live. Do **not** re-enable all 4 without new scout + overlap check.

---

## 5. Future plan

### Phase A — W1 closeout (done)
- [x] Stop All Copy during LoL stress
- [x] Let remaining positions settle / redeem
- [x] Dashboard eval stopped; final net recorded
- [ ] Optional: withdraw profit above ~$53 seed to Kraken

**Decision (recommended, pending Damian OK):**

| Action | Rationale |
|--------|-----------|
| **Do not** Turn On All Copy (4 wallets) | Correlation + 3/4 wallets failed fresh sim |
| **Next live option A:** **acorp only**, spend $30, 24–48h eval | Best sim + only proven live contributor |
| **Next live option B:** **Pause copy** until W2 sport line ready | Clean separation, less esport concentration |
| Un-pause v1.0 backups | Only if acorp-only also fails — not default |

### Phase B — W2 sport line (after W1 decision)

**Draft genome:** `configs/v1.2-sport.json`

| | W2 sport |
|--|----------|
| Seed | **$30** USDC |
| Spend limit | **$20** (~$10 buffer) |
| Roster | **casualbet2020**, **justbusiness1** (scout + isolated backtest, 2026-08-16) |
| Parallel with W1? | **No** on same spend pool — separate PolyCop sub-wallet **or** pause W1 |

*Aligned with your approach: 2 sport wallets, small bankroll, separate eval.*

### Phase C — Later (optional)
- **Stocks/macro** line — scout with domain filter; longer eval (7d+) due to slow markets
- **Dashboard:** second profile for W2 eval
- **Attribution:** tag settlements by source wallet in dashboard (future code)

---

## 6. Compare & contrast with Mitch (invite)

Would love your read on:

1. **4 vs 2 wallets** at ~$50 seed — too many for W1?
2. **Spend $30 per copy task** vs your sport line caps
3. **Paused fallback roster** — sensible or clutter?
4. **Early v1.1 pace** — wait full 48h or cut faster?

Our repo (local): `polymarket-copy-lab` — scout, backtest, genome JSONs, dashboard. Happy to share wallet addresses or eval screenshots on request.

---

## 7. Quick reference — wallet addresses (v1.1 active)

```
acorp           0x99e42eb9038705165b22f821e27659c1dc41e4c4
Skritopoolniy   0xd06c49e1c86f970bc5c48f91169a607e9b03cdaf
sulumos         0x9db82de5a71ae539bc82f4d9ac3a007c7d742eff
Iamnobody.Nobody 0x48fe10cd940a030eb18348ad812e0c382a4cb2b6
```

**PolyCop W1 trading wallet:** `0xc167E3a76e4b46F533a1dDb11097a03C0DbF4BD3`

---

## 8. Changelog (Mitch-style)

```
2026-08-15  v1.0 live — 8-wallet roster, spend $40, seed ~$53
2026-08-16  v1.0 stop — ~+$156 settled; Querétaro UMA pending
2026-08-16  v1.1 live — 4 active, 5 paused backup, spend $30, +Iamnobody, re-add acorp
2026-08-17  Early check — +$8.75 / 4 resolved / 4W-0L (~8h)
2026-08-17  LoL drawdown — Stop All Copy; session briefly ~−$10 unrealized
2026-08-17  v1.1 CLOSED — +$15.94 settled, 0 open (~21h); roster audit → keep acorp only or pause
2026-08-??    W2 sport planned — $30 seed, 2 wallets, separate eval
```

---

*End of handoff — v1.1 closed 2026-08-17.*
