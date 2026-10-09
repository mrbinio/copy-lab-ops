# BTC Lab — pełna dokumentacja do audytu

Data: **9 października 2026**, Europe/Stockholm. PAPER. `clob_live` = false. LIVE u Mitcha wyłączone.

Ten plik jest briefingiem dla kolejnego audytu. Liczby z pulpitu z **14:57 CEST** (ostatni lekki check). Proces na Macu żyje niezależnie od gita.

---

## 1. Co to jest

BTC Lab to **prywatna PAPER-kopiarka** rynków Polymarket **BTC/ETH Up/Down 5m i 15m**, działająca na Macu Damiana. Nie składa prawdziwych zleceń. Jedyny executor LIVE poza tym labem to **PolyCop Telegram** — tu go nie dodajemy i nie włączamy drugiego bota (FrenFlow / Poly Syncer / PolyTrackers zostają poza projektem).

Są **trzy osobne księgi**. Nie sumuj ich.

| Księga | Spec | Co robi | LIVE |
|---|---|---|---|
| Kwalifikator (Portfele) | `wallet-signal-copy-v1` + `copy-paper-v2` + roster `paper-roster-v3` | Kopiuje odkryte/seed portfele na 5m i 15m BTC/ETH | nie |
| Mitch | `mitch-copy-wallets-v1` | Kopiuje 5 wskazanych portfeli, **tylko BTC 15m** | nie |
| Strategie 5–15 min | `early-v1`, `late-v1`, `mid-window-v1/v2`, `value-v1`, `value-surface-paper-v1`, `eth-mid-window-v1` | Własne sygnały z referencji Chainlink/TWAP, **nie z portfeli** | nie |

Rezerwa zysku (40%) jest widoczna na Portfelach i Mitchu. To kolumna `reserved` na kontach PAPER, nie saldo giełdy.

---

## 2. Czego nie ruszać bez decyzji Damiana

- Nie włączaj `clob_live` / `live_enabled`.
- Nie resetuj księgi Mitcha (**dziś 0 / łącznie −110,36**; wczoraj 8.10 było **−202,45** — to ten sam minus, nowy dzień zeruje „dziś”).
- Nie kasuj historii, WAL, sqlite.
- Nie podnoś limitów ryzyka ($5 / 5 pozycji / $25 kwalifikator; $20 / $5 Mitch).
- Nie obniżaj rezerwy 40% i nie wyłączaj banku.
- Nie zmieniaj bramki Mitcha **1,0 s** ani `CHAIN_SOURCES` bez nowej decyzji.
- Nie zmieniaj pauzy Mitcha na auto-retest.
- Nie recykluj starego Top 8 jako LIVE copy.
- Nie dodawaj drugiego copy bota.
- Pasmo **20–70¢** zostaje tylko na kwalifikatorze (`copy_policy.py`).
- Nie commituj `.env`, `configs/monitor.json`, haseł, hashów, klucza Alchemy, tokenu tunelu, sqlite.
- Restart papieru **nie** za to, że book jest STALE.
- Unit testy nie są dowodem ścieżki live na Macu.

Copy LIVE (PolyCop) zostaje wyłączone, dopóki portfel nie przejdzie 60d+90d lab sim, dywersyfikacji, non-candle i CopyGrade veto. Ten dokument opisuje **PAPER lab**, nie promocję do LIVE.

---

## 3. Gdzie to leży

### Repo (kod źródłowy)

```
/Users/damianbiniarz/Projects/copy-lab-ops
  branch: ops/btc-reconcile-2026-10-05
  GitHub: mrbinio/copy-lab-ops
  HEAD przy ostatnim deployu: e001caf  (działający release może być nowszy niż HEAD)
```

| Ścieżka | Rola |
|---|---|
| `btc-lab/lab/` | Python: worker, copy, Mitch, roster, chain, server |
| `btc-lab/tests/` | unittest |
| `btc-lab/deploy/` | launchd, watchdog, tunel, zegar, backup |
| `lab/` | Dashboard: `index.html`, `app.js`, `style.css` |
| `docs/` i `ops/docs/` | Handoffy (ten sam zestaw, kopiowane) |
| `.cursor/rules/profit-bank.mdc` | Stała: 40% rezerwy |

Python importowany przez launchd pochodzi z **wydania**, nie z checkoutu gita:

```
~/Library/Application Support/BTC Lab/
  releases/<id>/btc-lab/lab/     ← Python runtime
  releases/<id>/lab/             ← HTML/JS serwowane z no-store
  data/lab.sqlite                ← ~6 GB + WAL; tryb odczytu: file:path?mode=ro
  logs/                          ← service.log, launch.*.log, dashboard-state-BTC.json
  configs/                       ← port, hash hasła, clob_live; NIE commituj
```

Aktualne wydanie przy ostatnich wdrożeniach: `releases/b009e2b8b429-1790926011187411000/`.

Deploy: skopiować zmienione `.py` do `{release}/btc-lab/lab/` i HTML/JS do `{release}/lab/`. Restart:

```
# najpierw launch-attempts.json — 5 w 600s czeka
launchctl kickstart -k gui/$(id -u)/com.btc-lab.paper
```

Sandbox Cursora nie zapisuje Application Support — kopie i `launchctl` wymagają uprawnień `all`.

### Aplikacja / dostęp

| Co | Wartość |
|---|---|
| Port | **8769** |
| Lokalnie | `http://127.0.0.1:8769/` |
| Zdalnie | `https://btc.damianbiniarz.com` (Cloudflare Access, potem basic auth, user `damian`) |
| Login | tylko Damian; Mitch może dostać read-only — nie dodawaj innych |
| Loopback GET | `/`, `/index.html`, `/app.js`, `/style.css`, `/api/state` bez 401 (żeby Cursor/localhost działał) |
| Sesja | cookie `lab_sess` po HTML/Basic |
| Cache JS/CSS | `?v=20261008-dash-fix` |
| Worker | **0.6.7**, status `RECORDING` / czasem `DEGRADED` |
| Healthz | 200 tylko gdy heartbeat &lt; 30 s **i** status RECORDING/PAUSED. DEGRADED (stary reference) → **503** mimo żywego procesu |

Zakładki pulpitu (`lab/index.html`): Portfele `#wynik`, Mitch `#mitch`, Historia `#dziennik`, Obserwacje `#obserwacje`, Kandydaci `#kandydaci`, 5–15 min `#strategie`, Diagnostyka `#diagnostyka`.

Tłumacz Chrome/Cursor psuje polskie etykiety. HTML ma `translate="no"` — user musi wyłączyć translator strony.

---

## 4. Procesy launchd

| Label | Rola |
|---|---|
| `com.btc-lab.paper` | Worker BTC+ETH + serwer 8769 (`lab.supervisor`) |
| `com.btc-lab.watchdog` | Restart przy martwym heartbeacie |
| `com.btc-lab.stay-awake` | `caffeinate` |
| `com.btc-lab.tunnel-watch` | Cloudflare tunnel |
| `com.btc-lab.clock` / `timesync` | Zegar (offset do `time.apple.com`) |
| `com.btc-lab.reports` | Opcjonalny hourly report |

Watchdog: 5 restartów w 600 s → stop automatycznych prób. Nie kasuj bazy, żeby „naprawić” start.

`healthz` 503 przy STALE reference **nie** jest sygnałem do `kickstart`. Book STALE też nie.

---

## 5. Ścieżka sygnału (wspólna)

```
Polygon WSS TransferSingle (blockmachine, fallback drpc)
    → wallet_chain_monitor.ChainMonitor
        → paragon OrderFilled  albo  last_trade_price dopasowany do transferu
    → kolejka hot_path (COPY / CHAIN / DB / READ osobne pule)
    → mitch_copy  LUB  wallet_copy
    → PAPER fill na CLOB book (FOK, 50% depth, obie opłaty)
    → sqlite + snapshot /api/state
```

Publiczna lista aktywności (Data API) nadal zasila obserwacje i kwalifikator. **Mitch BUY z listy publicznej jest zakazany.**

Klucz deduplikacji kolektora: `txHash + type + token + side` **bez size i log index**. Kilka filli jednego tx zderza się w jeden wiersz. To jest znany limit — kopia nie jest pełną rekonstrukcją księgi źródła.

Feed referencji: RTDS Chainlink + TWAP 30/60. Book CLOB. Worker wersja `0.6.7`.

---

## 6. Mitch — `mitch-copy-wallets-v1`

**Pliki:** `btc-lab/lab/mitch_copy.py`, `wallet_chain_monitor.py`, `order_fill.py`, testy `test_mitch_copy.py`, `test_chain_monitor.py`, `test_order_fill.py`. UI: `#mitch` w `lab/index.html` + `renderMitch()` w `lab/app.js`.

### Portfele (sztywna lista)

| Adres | Etykieta | Limit okna |
|---|---|---|
| `0x16217458…096b159` | 096b159 | $20 |
| `0xeda9247a…5cf589` | 0x9f672c31 | $20 |
| `0x943cea74…7e77c2` | 0xdc27 | $20 |
| `0x454c48b4…1865cf` | checkr3 | $20 |
| `0xa82365c8…386215` | mihaXd | $5 |

Tylko **BTC Up/Down 15m**. mihaXd 5m: werdykt Mitcha 7.10 — nie kopiować.

### Sizing

`min(D, 15) + 0.05 * max(D−15, 0)`, potem cap okna. Jednostronnie: nasza cena ≤ źródło + **10¢**. Lepsza cena OK.

Papierowy bankroll $500/konto — tylko żeby cap okna nie mylił się z pustym kontem. Wiążą okna $20/$5.

### Bramka czasu — to jest reguła 1 s

```
MAX_BUY_AGE = 1.0
CHAIN_SOURCES = ('order_filled', 'market_trade')
```

- Nowy BUY tylko gdy źródło to paragon `order_filled` albo `market_trade` (print o tym samym tx i size).
- Wiek &gt; 1,0 s → `LATE_BUY_NOT_COPIED`.
- `chain_fast` / `chain_accelerated` / `source_second` / lista publiczna → `MITCH_NEED_CHAIN`, **nie kupują**.
- `chain_fast` grzeje arkusz najwyżej 1 s.
- Czekanie na arkusz przy BUY też 1 s.
- Paragon bez dodatkowego `eth_getBlockByNumber` (szybciej).
- Pięć portfeli Mitcha: retry paragonu co **50 ms**, deadline **0,85 s**.
- Inne portfele (kwalifikator): poll 0,5 s / timeout 2 s.

SELL: wiek 90 s jest jeszcze dozwolony (zamknięcie pozycji). BUY nie.

### Pauza Mitcha

Ujemny zamknięty wynik **dziś albo od startu** → pauza BUY/ADD. SELL i settlement zostają. **Brak auto-retestu.** Pauza nie schodzi po późniejszym plusie. Przy starcie procesu pauzują już czerwone.

Stan 9.10 ~14:57: cztery na pauzie (0x9f672c31 −39,49; 0xdc27 −63,36; checkr3 −16,71; mihaXd +9,19 all / dziś 0 — pauza zostaje). 096b159: 0 kopii, bez pauzy.

Start księgi Mitcha: `1791308151.5852091` — nie resetować.

### Dlaczego −202 vs jego +322

8.10: nasze kopie 8–80 s po jego cenie, z listy publicznej, po gorszym asku. Jego +322 to **jego** księga. Nasza spóźniona kopia robiła odwrotność krawędzi. Naprawa = 1 s + chain-only + pauza, nie reset −202.

Po wdrożeniu (8.10 rano) 0 nowych `MITCH_BUY`. Do 14:57 9.10 nadal 0.

---

## 7. Kwalifikator — Portfele

**Pliki:** `wallet_copy.py`, `copy_policy.py`, `wallet_roster.py`, `wallet_observation.py`, `wallet_observer.py`, `wallet_discovery.py`, `wallet_watch.py`, `copy_totals.py`, `profit_bank.py`. Testy: `test_wallet_copy.py`, `test_wallet_roster.py`, `test_copy_policy.py`, `test_copy_totals.py`.

Start kopiowania: `wallet_copy_start` `{"at": 1790703742.889763}` (~29.09) — nie resetować.

### Execution (`copy-exec-v4` / `copy-paper-v2`)

| Limit | Wartość |
|---|---|
| Konto PAPER | $500 na portfel (osobne, nie jeden portfel) |
| Pozycja | $5 all-in (cost+entry fee) |
| Otwarte | max 5, wallet cap $25 |
| Do pierwszego wyniku okresu | max **2** otwarte |
| Pasmo ceny źródła | **20–70¢** |
| Odchylenie fill vs źródło | ±**10¢** (`DEVIATION`) |
| Wiek sygnału | **90 s** (`source_ts` i `first_seen`) |
| Fill | FOK, 50% depth, obie opłaty, ask w paśmie źródła |
| Brak ceny źródła | skip (`SOURCE_PRICE_MISSING`), nie podstawiaj arkusza |

BUY na pauzie: blokada. SELL i official settlement: tak. Oficjalny payout `RESOLVED` liczy się do pauzy **zanim** cash się przesunie (300 s wait nie jest waitem przed stratą).

### Roster `paper-roster-v3`

Stany: `observed` → `paper_test` → `paper_active` → `paused`.

| Przejście | Próg |
|---|---|
| observed → paper_test | ≥20 naszych settled, ≥5 okien, net ≥ $0.01, 0 dni kalendarza |
| paper_test → paper_active | ≥30 copy trades, net ≥ $0.01 |
| dowolny copying → paused | **net okresu &lt; 0** (zamknięte otwarte **od `since`**) |
| paused → paper_test | jedna obserwacja na plus, `min_pause_days: 0` |

Okres pauzy = zamknięcia z `opened >= roster.since` (copy-start albo ostatni retest/activate), **nie** kalendarz „dziś” i nie lifetime. Brak zamknięcia ≠ zero i nie pauzuje.

70% best-day to **notatka niepewności**, nie weto.

**Retest:** lifetime-czerwony portfel **może wrócić** po jednej obserwacji plus. Nowy okres od `since=now`, 0 zamknięć → kopiuje do pierwszego wyniku. To jest obecna reguła, nie bug. Audytorzy często mylą lifetime minus z okresem od `since`.

**Activate resetuje `since`.** Po promocji do `paper_active` nowy stint jest pusty. Trade otwarty przed activate, zamknięty po, **nie** liczy się do nowego okresu (`period_closes` filtruje po `opened`).

### Discovery `discovery-v1`

Publiczny month table to lead, nie score. Admit do `observed` po screenie: nasze rynki 5m/15m, min 10 naszych trade, share ≥ 0.25, historia ≥ 1 dzień. `paper_test` jest później i używa **naszych** hipotetycznych kopii, nie month PnL źródła.

Seed (obserwowane od początku): 096b159, 365cf589, 207e77c2, eebde7a0. Paper extra: Atomforge, honey-spot.

### Obserwacja `copy-observe-v2`

Osobna księga hipotetyczna od jawnego startu. Nie jest PAPER PnL. Nie promuje i nie przywraca. Independent hold-to-settlement tickets też osobno — nie dodawaj do sumy Portfeli.

---

## 8. Własne strategie 5–15 min (zakładka Strategie)

**Pliki:** `strategy.py`, `mid_window.py`, `mid_window_v2.py`, `value_execution.py`, `opportunity_research.py`, `strategy_control.py`. Domyślnie **pauza** (`DEFAULT_PAUSED`) na mid/value/late/eth. `early-v1` jest toggleable.

| ID | Wejście | Status |
|---|---|---|
| `early-v1` | remaining 600–780 s, dystans ≥ 50, ask 0.60–0.64 | baseline, toggle |
| `late-v1` | remaining 30–300 s, ask 0.80–0.955 | **PAUSED** |
| `mid-window-v1` | elapsed 180–420 s, ask 0.50–0.60, momentum 30 s, SL 20% / TP 10% w spec (w core stop 10%) | **PAUSED**, UNVALIDATED |
| `mid-window-v2` | 180–420 s, ask 0.55–0.80, favorite side | **PAUSED**, FROZEN; komentarz w pliku vs etykieta core „3–5” — rozjazd do sprawdzenia |
| `value-v1` / `value-surface-paper-v1` | model + krawędź vs fee | **PAUSED**, ledger $100 |
| `eth-mid-window-v1` | ETH analog 3–7 | **PAUSED** |

Te strategie **nie wchodzą** do liczby na Portfelach. Osobne konta w `STRATEGIES`.

Referencja musi być świeża (≤5 s), book ≤3 s. `RULE_UNVERIFIED` / `FEE_UNVERIFIED` / `REFERENCE_STALE` = skip.

---

## 9. Rezerwa zysku

**Plik:** `btc-lab/lab/profit_bank.py`. Wywołania: close path w `wallet_copy.py` i `mitch_copy.py`.

40% każdego **nowego zamkniętego plusu** → `reserved`. `tradable_cash = cash − reserved`. Strata nie rusza rezerwy. Widać jako **Rezerwa zysku**.

9.10 14:57: **275,48** (Mitch 33,88 · kwalifikator 241,60). Mitch stoi, więc jego część nie rośnie.

Okna $20 nadal teoretycznie strzelają przy wysokim cash — **pauza na czerwonym** zatrzymuje recykling, nie sam bank.

---

## 10. Worker, I/O, baza

**Pliki:** `worker.py` (0.6.7), `hot_path.py`, `core.py`, `supervisor.py` (BTC worker + ETH worker + server).

Pule: `IO` 6, `COPY` 4, `CHAIN` 2, `DB` 1 writer, `READ` 2. Book cache max_age **1,0 s**. Research (`_research_once`) w tle, żeby snapshot nie wisiał.

`wallet_activity` last-30 z `busy_timeout`. Last-good snapshot: `logs/dashboard-state-{asset}.json`.

`live_enabled` w snapshot **zawsze False** (`core.py`). Nawet jeśli config miałby klucz, dashboard pokazuje PAPER.

Chain WSS: `wss://rpc-polygon.blockmachine.io`, fallback `polygon.drpc.org`. Alchemy URL w config — nie logować, nie commitować.

---

## 11. Dashboard / auth / znane awarie UI

**Pliki:** `btc-lab/lab/server.py`, `lab/app.js`, `lab/index.html`, `lab/style.css`.

- Snapshot TTL 2 s, lock, last-good jeśli build pada.
- `request_path()` normalizuje absolute-form URI z proxy (inaczej 401).
- `lastMitchSig` musi być zadeklarowany razem z `lastViewSig` (TDZ wyłączał cały `refresh()` → „brak danych” + AWARIA).
- `render()` skip gdy sygnatura liczb ta sama; `overflow-anchor: none`; restore scroll.
- State ~1,8–2,0 MB. Pierwszy fetch ~300 ms. To nie jest „pusty ekran”, jeśli JS żyje.
- `/api/report` nadal 401 bez auth (test: `test_lab.py` AuthTests).

---

## 12. Co udoskonalić (kolejka audytu)

To jest lista luk, nie zgoda na zmianę. Każdy punkt wymaga decyzji Damiana.

### A. Czas — największa dziura między księgami

1. **Kwalifikator nadal 90 s.** Mitch ma 1 s + chain-only. Kwalifikator kupuje ze 90-sekundowego okna i z publicznej listy. Jeśli celem jest „kopiować krawędź, nie ogon”, kwalifikator powtórzy historię −202.
2. **Kolektor zderza fille** (brak log index / size w kluczu). D i sizing Mitcha liczą się na zdegenerowanym wierszu.
3. `chain_fast` nie ma zegara transakcji źródła — latency tile wtedy kłamie albo jest „nieznany”.
4. Book CLOB często **STALE** przy żywym workerze. Copy BUY czeka max 1 s (Mitch) / 15 s normalize (kwalifikator `max_age=15` na części path). Zmierz, ile skipów to STALE vs LATE.
5. Polygon WSS: timeouty i `events_dropped` rosną (ostatnio rzędu tysięcy). Ile filli Mitcha ginie przed 0,85 s?

### B. Roster / recykling strat

6. `min_pause_days: 0` + retest po jednej obserwacji plus = lifetime-czerwone portfele wracają w nocy (9b9fa354, 8a2e7537 wielokrotnie 8–9.10). PAPER OK jako eksperyment; do LIVE to veto.
7. Activate resetuje `since` — po 30 plusach nowy stint może od razu zjeść plus i pauzować, albo odwrotnie: stare minusy po activate nie pauzują. Świadoma semantyka, łatwo ją źle zauditować.
8. Max 2 open do pierwszego wyniku — sprawdzić, czy retest nie otwiera 2×$5 zanim przyjdzie RESOLVED.

### C. Strategie własne

9. Prawie wszystkie na pauzie. Zakładka 5–15 min jest martwa operacyjnie. Albo zostawić jako archiwum, albo osobny PAPER z jasnym startem.
10. Rozjazd `mid-window-v2`: plik mówi 3–7 min, etykieta core „BTC 3–5”.

### D. Infrastruktura pulpitu

11. `healthz` 503 przy STALE reference (08:57 i 13:57 9.10). Watchdog/kable mogą to źle czytać. Nie restartować; rozważyć osobny `healthz` vs `copy_health`.
12. Snapshot 2 MB / 2 s poll. Ryzyko „brak danych” przy wolnym locku.
13. sqlite ~6 GB. `storage_maintenance.py` istnieje — sprawdzić rotację WAL, nie kasować historii.
14. Tunel: `edge_connected` + HTTP 302. Auth-only zostaje.

### E. LIVE / PolyCop (poza tym labem)

15. Ten lab **nie** jest bramką LIVE. Promocja portfela = 60d+90d sim, dywersyfikacja, non-candle, CopyGrade. Nie recyklować Top 8. PolyCop Telegram jedyny executor.

### F. Testy vs Mac

16. Unittest discover bierze **ostatni** `-p`. Odpalaj jedną paczkę.
17. Testy nie zastępują: healthz, `/api/state`, pauzy na żywych portfelach, age na prawdziwym paragonie.

---

## 13. Mapa plików (gdzie czytać)

### Copy i czas

| Plik | Czytaj gdy |
|---|---|
| `btc-lab/lab/mitch_copy.py` | 1 s, chain sources, pauza, sizing, 5 portfeli |
| `btc-lab/lab/wallet_chain_monitor.py` | WSS, 50 ms / 0,85 s Mitch, 0,5 s / 2 s reszta, `chain_fast` |
| `btc-lab/lab/order_fill.py` | paragon bez extra block fetch |
| `btc-lab/lab/hot_path.py` | pule, cache book 1 s |
| `btc-lab/lab/copy_policy.py` | 20–70¢, ±10¢, FOK |
| `btc-lab/lab/wallet_copy.py` | $5/$25, 90 s, 2 open przed wynikiem, lock_profit |
| `btc-lab/lab/wallet_roster.py` | v3 stany, pauza od `since`, retest, activate |
| `btc-lab/lab/wallet_observation.py` | hipotetyczna księga 90 s |
| `btc-lab/lab/copy_totals.py` | board dziś/tydzień/all, latency note |
| `btc-lab/lab/profit_bank.py` | 40% |

### Worker / UI / ops

| Plik | Czytaj gdy |
|---|---|
| `btc-lab/lab/worker.py` | pętla, 0.6.7, clob_live gate, RTDS |
| `btc-lab/lab/core.py` | snapshot, `live_enabled: False`, STRATEGIES |
| `btc-lab/lab/server.py` | auth, loopback, session, healthz |
| `btc-lab/lab/strategy.py` + `mid_window*.py` | własne strategie |
| `btc-lab/lab/strategy_control.py` | które ID są na pauzie |
| `lab/app.js` / `index.html` / `style.css` | pulpit |
| `btc-lab/deploy/*` | launchd, tunel, zegar, watchdog |
| `btc-lab/EXPERIMENT-WALLET-COPY.md` | zamrożony spec 29.09 (90 s, 3 portfele) — **nadpisany** przez v2/v3 i Mitcha; nie używać jako current |

### Handoffy kluczowe (nie wszystkie 130)

- `docs/HANDOFF-OPS-BTC-MITCH-STOP-2026-10-08.md` — 1 s + pauza Mitch
- `docs/HANDOFF-OPS-BTC-MITCH-SPEED-2026-10-07.md` — prędkość łańcucha
- `docs/HANDOFF-OPS-BTC-LOSS-AUDIT-2026-10-07.md` — skąd −202
- `docs/HANDOFF-OPS-BTC-COPY-POLICY-2026-10-05.md` — 20–70¢, ±10¢, SELL na pauzie
- `docs/HANDOFF-OPS-BTC-ROSTER-V3-2026-10-05.md` — roster
- `docs/HANDOFF-OPS-BTC-DASH-BLANK-2026-10-08.md` — pusty pulpit
- `docs/HANDOFF-OPS-BTC-TUNNEL-2026-10-07.md` — tunel

Reguła Cursora: `.cursor/rules/profit-bank.mdc`.

---

## 14. Jak sprawdzać na żywo (lekki audyt)

Nie rób godzinnego dumpa. Co 30 min wystarczy:

1. Zegar: `clock_status.status == synced` (offset zwykle &lt; 100 ms vs `time.apple.com`).
2. `GET /healthz`, `GET /`, `GET /api/state?asset=BTC`. LIVE false. Worker RECORDING (albo DEGRADED + STALE → **nie restart**).
3. Mitch: ujemny net albo ujemne dziś → `paused=true`. 096b159 przy 0 kopii może być nie-paused.
4. Kwalifikator: `paper_test` / `paper_active` z **okresem od `since` po `opened`** &lt; 0 i nadal copying → naprawa. Lifetime minus przy świeżym retest i 0 zamknięć = zgodnie z regułą.
5. Rezerwa nie spada przy stratach.

Endpointy: tylko `127.0.0.1:8769`. Nie wołaj zdalnego URL z hasłem w czacie.

Stan 9.10 14:57: healthz 200, worker RECORDING, book STALE, Mitch −110,36 / 4 pauzy, 9 paper_test bez minusa od `since`, rezerwa 275,48.

---

## 15. Testy

```
python3 -m unittest discover -s btc-lab/tests -p 'test_mitch_copy.py'
python3 -m unittest discover -s btc-lab/tests -p 'test_wallet_copy.py'
python3 -m unittest discover -s btc-lab/tests -p 'test_wallet_roster.py'
python3 -m unittest discover -s btc-lab/tests -p 'test_chain_monitor.py'
```

Discover honoruje **ostatni** `-p`. Nie łącz wielu `-p`.

---

## 16. Changelog tego briefu

- Zebranie aktualnego kodu (Mitch 1 s, kwalifikator 90 s, roster v3, bank 40%, dashboard dash-fix) i stanu z 9.10.
- Lista luk do następnego audytu bez włączania LIVE i bez resetu −202.

## Następna decyzja

Czy kwalifikator ma dostać tę samą bramkę 1 s + chain-only co Mitch, czy 90 s zostaje jako osobny eksperyment discovery. Czy retest `min_pause_days: 0` zostaje na PAPER. LIVE nadal off.
