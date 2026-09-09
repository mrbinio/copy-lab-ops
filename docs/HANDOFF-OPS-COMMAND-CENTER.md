# Polymarket Copy Lab — Handoff: Ops command center

**Author:** Damian / agent  
**Date:** 2026-09-09  
**Purpose:** Remote, auth-gated console so research, live stance, and conclusions live in one place — same documentation standard as Mitch v1.1. This site **does not place trades**.

---

## 1. Executive summary

| | |
|--|--|
| **What** | Static ops console (`ops/`) with charts, 60/90d conclusions, live “copy paused”, watch/ban lists, agent log. |
| **Who sees it** | **Firebase Auth (Google)** allowlist. Damian = owner. Mitch = optional **viewer** (read research + stance, no control writes). |
| **Host** | **Cloudflare Pages** from this GitHub repo (`ops/` as root). |
| **State** | **Firebase Firestore** `ops/{stance,notes,commands}` — conclusions and a command queue for the local lab. Not PolyCop. |
| **Git** | Same repo `mrbinio/polymarket-copy-lab`, **private**. Mitch can be a GitHub collaborator when you want him to read `docs/` without the live console. |

**Cannot do:** enable copy, change PolyCop caps, move USDC. Those stay in Telegram @PolyCop_BOT.

---

## 2. Why three vendors (and not three executors)

| Vendor | Job | Not |
|--------|-----|-----|
| **GitHub** | Source of truth: code, `docs/HANDOFF-*.md`, sanitized `ops/data/snapshot.json` | Public dump of dashboard keys |
| **Firebase** | Login + Firestore (stance, notes, command queue) | A trading bot |
| **Cloudflare** | HTTPS site (Pages). Later: Access in front if we want a second lock; tunnel only if we expose local :8765 | Second copy bot |

Local Flask dashboards (`:8765` live, `:8767` scout) stay on the Mac. The ops site is the **remote brain**, not a replacement for PolyCop.

---

## 3. Repo layout

```
docs/HANDOFF-MITCH-v1.1.md
docs/HANDOFF-RESEARCH-60-90-2026-09-09.md
docs/HANDOFF-OPS-COMMAND-CENTER.md          ← this file
ops/index.html                             ← console
ops/styles.css
ops/app.js
ops/data/snapshot.json                     ← committed research snapshot
ops/firebase-config.example.js
ops/firebase-config.js                     ← gitignored; created after Firebase project
firestore.rules
firebase.json
```

`data/*.json` on the Mac stays gitignored (full dumps). Export to ops with:

```bash
python3 scripts/export_ops_snapshot.py
```

---

## 4. Security

**Never commit**

- `configs/monitor.json` (dashboard key, live wallet)
- `configs/scout_dashboard.json`
- `.env`, `bin/ngrok`, `bin/cloudflared`
- Firebase **service account** JSON (if we add Admin SDK later)

Firebase **web** apiKey is a public client key. Protection is: Auth allowlist + Firestore rules + authorized domains (`*.pages.dev`, custom host, `localhost`).

**Roles**

| Email | Role |
|-------|------|
| Damian Google (set in `firebase-config.js` `owners`) | Read + write notes/commands |
| Mitch Google (add to `viewers` when sharing) | Read only |
| Anyone else | Signed in → still blocked |

---

## 5. Local preview (no cloud)

```bash
cd ~/Projects/polymarket-copy-lab
python3 scripts/serve_ops.py
```

Open http://127.0.0.1:8788/ops/  
On localhost, if `firebase-config.js` is missing, the console still opens (lab machine). Production **requires** Google sign-in.

---

## 6. Create the three projects (do this once)

GitHub in this Cursor session is **connected** via Connect GitHub, but `git push` over HTTPS still fails (`Invalid username or token`). Push from Cursor’s Git UI, or install `gh` and `gh auth login`, then:

```bash
gh repo edit mrbinio/polymarket-copy-lab --visibility private
# optional, when sharing docs with Mitch:
gh api repos/mrbinio/polymarket-copy-lab/collaborators/MITCH_GITHUB -X PUT -f permission=pull
```

### Firebase

1. https://console.firebase.google.com → Add project → name **`copy-lab-ops`** (or similar).
2. Authentication → Sign-in method → **Google** → enable.
3. Firestore → create database (production mode) → paste `firestore.rules` from this repo.
4. Project settings → Your apps → Web app → copy config into `ops/firebase-config.js` (from the example).
5. Authentication → Settings → Authorized domains: add the Cloudflare Pages host.

### Cloudflare Pages

1. https://dash.cloudflare.com → Workers & Pages → Create → **Connect GitHub** → `mrbinio/polymarket-copy-lab`.
2. **Root directory:** `ops`  
   **Build command:** *(empty)*  
   **Output:** `/` (static).
3. After first deploy, copy `https://….pages.dev` into Firebase authorized domains.

Optional later: **Cloudflare Access** on that hostname (email allowlist) as a second gate in front of Firebase.

---

## 7. Firestore shape

| Path | Who writes | Meaning |
|------|------------|---------|
| `ops/stance` | owner | `{ copy: "paused", sl_usd: 31, updated_at, note }` |
| `ops/notes/{id}` | owner | Dated conclusions (agent + Damian) |
| `ops/commands/{id}` | owner | Queue for the **local** lab (`run_weekly_screen`, `export_snapshot`). Never `enable_copy`. |

The agent (Cursor) is expected to read `commands` when working locally and append a Mitch-style `docs/HANDOFF-*.md` after each pass.

---

## 8. Sharing with Mitch

Two layers, pick one or both:

1. **GitHub collaborator (pull)** — he reads `docs/` and `ops/` in the private repo. No Firebase login required.
2. **Viewer email on the site** — add his Gmail to `viewers` in `firebase-config.js`, redeploy. He sees charts + stance; he cannot enqueue commands.

Do **not** send him `dashboard_key` or PolyCop Telegram.

---

## 9. Decision log

| Date | Decision |
|------|----------|
| 2026-09-09 | Site is auth-only (Damian). Mitch may be added as read-only. Same private GitHub repo. |
| 2026-09-09 | PolyCop remains the only executor. Ops site is analysis + memory. |

---

## 10. Changelog

```
2026-09-09  Ops console scaffolded (static + Firestore rules + snapshot export)
2026-09-09  Cloud projects: blocked on Git HTTPS token + Firebase/CF dashboard login
```

---

*End of handoff — ops command center, 2026-09-09.*
