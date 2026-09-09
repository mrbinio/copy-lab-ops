/* Copy Lab board. Does not place trades. */
(function () {
  const I18N = {
    pl: {
      "gate.lede": "Zdalna tablica. Nie handluje. Hasło z czatu, dopóki nie ma Google.",
      "gate.google": "Dalej z Google",
      "gate.pass": "Hasło strony",
      "gate.open": "Otwórz",
      "gate.needPass": "Wpisz hasło ze czatu.",
      "gate.wrong": "Złe hasło.",
      "gate.noGoogle": "Google jeszcze nie jest na tej stronie. Wpisz hasło ze czatu.",
      "top.sub": "Tylko @PolyCop_BOT · strona nie handluje",
      "nav.do": "Co robić",
      "nav.sim": "Symulacja",
      "nav.poly": "PolyCop",
      "nav.money": "Kasa",
      "nav.how": "Jak to działa",
      "do.kicker": "Dzisiaj",
      "do.title": "Nic nie włączasz.",
      "do.lead": "Hunt już szuka portfela. W Telegramie nie klikasz. Copy zostaje wyłączony.",
      "do.jump": "Zobacz symulację →",
      "do.jumpPoly": "Kartka PolyCop →",
      "do.copy": "Copy w PolyCop",
      "do.cash": "Twoje USDC w bocie",
      "do.s1t": "Teraz",
      "do.s1": "Copy OFF. Dwa razy na godzinę hunt sprawdza nowe nazwy. Ty nic nie robisz.",
      "do.s2t": "Następne",
      "do.s2": "Lab znajdzie jeden portfel z 90 dniami historii, zyskiem w 60d i 90d, bez jednego eventa. Adres pojawi się tutaj.",
      "do.s3t": "Potem",
      "do.s3": "Wklejasz ten jeden adres w @PolyCop_BOT. Reszta Paused. Klikasz Turn On Copy — nie All Copy.",
      "do.warn": "Turn On All Copy włącza całą starą listę. Tak poszła strata −$13.58 na invorserze.",
      "lane.title": "Rynki teraz",
      "lane.lead": "Który tor ma edge, a który jest martwy. Hunt przepisuje to o :20 i :50 UTC. Klik otwiera nazwy w Symulacji. Copy sam się nie przełącza.",
      "lane.headWait": "Najsilniejszy tor: {name}. Copy zostaje off.",
      "lane.headNone": "Żaden tor nie przeszedł sitów. Crypto-świece zostają NIE.",
      "lane.wait": "WAIT",
      "lane.no": "NIE",
      "lane.cold": "SŁABO",
      "lane.open": "Nazwy →",
      "lane.clear": "Wszystkie rynki",
      "lane.filter": "Filtr rynku: {name}.",
      "lane.switchNo": "Nie przełączaj copy.",
      "lane.switchLook": "Patrz tutaj. Nie włączaj.",
      "lane.switchOnly": "Jedyny WAIT. Nadal nie włączasz.",
      "lane.tennis": "Tenis",
      "lane.finance": "Finanse / akcje / Fed",
      "lane.politics": "Polityka",
      "lane.crypto": "Crypto · świece 5 min",
      "lane.culture": "Kultura / eventy",
      "lane.cluster": "Sport · mundial cluster",
      "lane.nba": "NBA",
      "lane.tech": "Tech",
      "lane.sports": "Sport · reszta",
      "res.title": "Jakie rozwiązania badamy",
      "res.lead": "Hunt nie zamyka się na jednego maskota. Copy zostaje off.",
      "res.nowK": "Teraz",
      "res.nowT": "Już leci, dwa razy na godzinę",
      "res.now1": "Sport — tenis (Antblack WAIT). Esport wycięty po invorserze.",
      "res.now2": "Polityka, kultura, tech, finanse, ekonomia — te same sity $5 / $15.",
      "res.now3": "Ostatni bieg: 994 nowe nazwy. Nikt nie przeszedł 90d + książka + CopyGrade.",
      "res.now4": "WAIT na tablicy: Antblack (76d tenis), 86shin (polityka, cienka próbka).",
      "res.nextK": "Następne biegi",
      "res.nextT": "To będzie hunt o :20 i :50 UTC",
      "res.next1": "Głębsze leaderboardy (wyższe offsety), nie te same 50 nazw z góry.",
      "res.next2": "CopyGrade jeszcze raz — Dreamlawn dostał rate limit, sim tylko +$4.4.",
      "res.next3": "Szukamy 90d+ z conc ≤ 0.45, nie świece, nie Avoid — lepszych niż Antblack.",
      "res.next4": "Sport bez esportu i bez mundial-cluster (Jittz / Daemon99).",
      "res.laterK": "Jeszcze można",
      "res.laterT": "Nie w tym cyklu, ale w zasięgu labu",
      "res.later1": "Crypto, które nie jest świecą Bitcoin 5 min.",
      "res.later2": "NBA / tenis osobno, weather / geo jeśli jest na tablicy.",
      "res.later3": "Merlin all-time mid-tier, którego pierwszy pass nie doszedł.",
      "res.later4": "Nigdy: Top 8, invorser, PoppyG / Bromsloy, CopyGrade Avoid.",
      "poly.title": "Kartka do PolyCop",
      "poly.lead": "Przygotowana jak ostatnio: jeden adres, reszta Paused, małe capy. Copy zostaje off. Z tej sesji nie klikam Telegrama — nie ma API. Ty nic nie włączasz.",
      "poly.off": "COPY OFF — kartka gotowa, bot niehandluje.",
      "poly.pauseK": "To zostaje Paused (nie Active, nie All Copy)",
      "sim.title": "Symulacja",
      "sim.lead": "To nie Twoja żywa kasa. Lab sprawdza: gdybyś kopiował za $5, ignore poniżej $20, max $15 w rynku.",
      "sim.p1k": "Dziś",
      "sim.p1t": "Hunt, copy off",
      "sim.p2k": "Później, może",
      "sim.p2t": "Antblack, tenis",
      "sim.p3k": "Nigdy",
      "sim.p3t": "Tłusty sim",
      "sim.charts": "Wykresy",
      "sim.chartsLead": "Jeden język, jeden wniosek pod każdym wykresem.",
      "sim.aTitle": "Ile nazw odpada zanim copy ma sens?",
      "sim.aAsk": "Każdy słupek to liczba portfeli. Zaczynamy od całej tablicy miesiąca, potem odrzucamy za krótką historię, potem liczymy sim, na końcu zostają ci z zyskiem w 60d i 90d.",
      "sim.bTitle": "Gdybyś kopiował za $5 — co dały 90 dni?",
      "sim.bAsk": "To symulacja, nie live. Żółty = WAIT, jeszcze nie włączamy. Szary = odrzut, nawet gdy słupek jest wysoki.",
      "sim.cTitle": "Zysk z jednego eventa, czy z książki?",
      "sim.cAsk": "Jaki procent P&L siedzi w jednym rynku. Powyżej 0.45 (45%) = loteria. Czerwony = nie kopiujemy.",
      "sim.table": "Wyniki huntu",
      "sim.thCall": "Werdykt",
      "sim.thWallet": "Portfel",
      "sim.thDays": "Dni",
      "sim.thWhy": "Dlaczego",
      "sim.wait": "CZEKAJ",
      "sim.no": "NIE",
      "sim.axisCount": "Ile portfeli",
      "sim.axisPnl": "Sim $ przy copy $5 (nie live)",
      "sim.axisConc": "0 = wiele rynków · 1 = jeden event · czerwony > 0.45",
      "sim.funnelLabs": "Oglądane|Za nowe|Miało 60d|Policzyliśmy sim|Zysk 60d i 90d",
      "money.title": "Skąd te pieniądze",
      "money.lead": "To Twoje USDC w portfelu PolyCop. Ta strona nic nie trzyma.",
      "money.cash": "Teraz w PolyCop W1",
      "money.hole": "Noc invorser (esport)",
      "money.spend": "Limit w rynku, jeśli włączysz",
      "money.sl": "Nowy stop (nie $42)",
      "money.k1": "Czyje",
      "money.t1": "Twoje, w Telegramie",
      "money.p1": "Portfel handlowy @PolyCop_BOT (W1). GitHub i hunt nie wpłacają i nie wypłacają.",
      "money.k2": "Jak zeszło do ~$39",
      "money.t2": "~$53 → invorser → $39.08",
      "money.p2": "Noc 21–22 Aug 2026: copy invorser (LoL / CS / Dota). $52.66 → $39.08, −$13.58. Bot sam wyłączył copy.",
      "money.k3": "$15 i $31",
      "money.t3": "Limity, nie nowa kasa",
      "money.p3": "$15 = ile wolno mieć w rynku później. $31 = nowy stop na saldzie. Nic z tego nie rusza się dziś.",
      "how.title": "Jak to działa",
      "how.lead": "Krótko. Bez mieszania języków.",
      "how.q1": "Co to za strona?",
      "how.a1": "Tablica lab. Nie kupuje i nie sprzedaje. Copy tylko w @PolyCop_BOT. Bez drugiego bota.",
      "how.q2": "Kto ustawia portfele w PolyCop?",
      "how.a2": "Lab (Cursor) przygotowuje jeden adres tutaj. Hunt tylko szuka. Z tej sesji nie da się kliknąć Telegrama. Ty nie składasz listy od zera. Gdy przyjdzie czas: wklejasz jeden adres i Turn On Copy.",
      "how.q3": "Czego nie wciskasz?",
      "how.a3": "Turn On All Copy. To włącza wszystkich — tak spalił się invorser.",
      "how.q4": "Gdzie jest symulacja?",
      "how.a4": "Zakładka Symulacja: trzy ścieżki, trzy wykresy, tabela huntu. Odświeża się co 15 sekund. Hunt na GitHubie o :20 i :50 UTC.",
      "how.q5": "Kiedy w ogóle włączamy?",
      "how.a5": "Gdy WAIT ma też ≥90 dni, zysk w 60d i 90d, conc ≤ 0.45, CopyGrade nie Avoid. Dziś tego nie ma.",
      "how.card": "Kartka do PolyCop (na później)",
      "how.cardLead": "Lab ją wypełnia. Nie wciskasz All Copy.",
      "how.ban": "Tego nie wklejasz",
      "pred.a": "Prognoza: $0 dodatkowej straty z copy. Hunt sprawdził {n} nowych portfeli. Nikt nie przeszedł 90d + książka + CopyGrade naraz. Czekamy. Nie ruszamy $39.",
      "pred.b": "Lab: 60d {w60} / 90d {w90} przy copy $5, tenis, conc 0.11. Tempo 60d ≈ ${per30} / 30 dni — nie obietnica. Historia 76 dni. Dziury −$13.58 szybko nie zasypie.",
      "pred.c": "Wysokie simy to jeden event, świece Bitcoin 5 min albo CopyGrade Avoid. Wklejenie ich = ten sam błąd co invorser.",
      "read.funnel": "Teraz: {u} nazw → {drop} za nowe → tylko {both} z zyskiem w 60d i 90d. Krótki ostatni słupek to norma.",
      "read.pnl": "Żółty / CZEKAJ: {names}. Wysoki szary słupek to nie pick.",
      "read.conc": "{hot} Czerwony = jeden event. Tego nie wklejasz.",
      "read.concNone": "W tej paczce nie ma czerwonych słupków. ",
      "hunt.line": "Hunt :20 i :50 UTC. Ostatni bieg: {n} nowych nazw. CZEKAJ = prawie. NIE = odrzut. Hunt nie włącza bota.",
      "hunt.missing": "Brak pliku huntu",
      "hunt.running": "HUNT DZIAŁA · ",
      "hunt.last": "ostatni hunt ",
      "cap.active": "Aktywne portfele",
      "cap.activeV": "Antblack — przygotowany, Paused. Copy OFF. Reszta też Paused.",
      "cap.addr": "Adres",
      "cap.fixed": "Fixed / max Yes-No / max rynek",
      "cap.ignore": "Ignore poniżej",
      "cap.spend": "Total spend",
      "cap.sl": "Balance SL",
      "cap.all": "Turn On All Copy",
      "cap.never": "Nigdy"
    },
    en: {
      "gate.lede": "Remote board. Does not trade. Password from chat until Google is on.",
      "gate.google": "Continue with Google",
      "gate.pass": "Page password",
      "gate.open": "Open",
      "gate.needPass": "Enter the page password from chat.",
      "gate.wrong": "Wrong password.",
      "gate.noGoogle": "Google is not on this deploy yet. Enter the page password from chat.",
      "top.sub": "PolyCop only · this page does not trade",
      "nav.do": "What to do",
      "nav.sim": "Simulation",
      "nav.poly": "PolyCop",
      "nav.money": "Cash",
      "nav.how": "How it works",
      "do.kicker": "Today",
      "do.title": "Do not enable copy.",
      "do.lead": "Hunt is already searching. You do nothing in Telegram. Copy stays off.",
      "do.jump": "See the simulation →",
      "do.jumpPoly": "PolyCop card →",
      "do.copy": "Copy in PolyCop",
      "do.cash": "Your USDC in the bot",
      "do.s1t": "Now",
      "do.s1": "Copy OFF. Hunt checks new names twice an hour. You do nothing.",
      "do.s2t": "Next",
      "do.s2": "Lab finds one wallet with 90 days, profit in 60d and 90d, not one event. The address appears here.",
      "do.s3t": "Then",
      "do.s3": "Paste that one address in @PolyCop_BOT. Everyone else Paused. Press Turn On Copy — not All Copy.",
      "do.warn": "Turn On All Copy enables the whole old list. That is how invorser lost −$13.58.",
      "lane.title": "Markets now",
      "lane.lead": "Which book has an edge and which is dead. Hunt rewrites this at :20 and :50 UTC. Click opens names in Simulation. Copy does not switch itself.",
      "lane.headWait": "Strongest lane: {name}. Copy stays off.",
      "lane.headNone": "No lane cleared the gates. Candle crypto stays NO.",
      "lane.wait": "WAIT",
      "lane.no": "NO",
      "lane.cold": "THIN",
      "lane.open": "Names →",
      "lane.clear": "All markets",
      "lane.filter": "Market filter: {name}.",
      "lane.switchNo": "Do not switch copy.",
      "lane.switchLook": "Watch here. Do not enable.",
      "lane.switchOnly": "Only WAIT. Still do not enable.",
      "lane.tennis": "Tennis",
      "lane.finance": "Finance / stocks / Fed",
      "lane.politics": "Politics",
      "lane.crypto": "Crypto · 5-min candles",
      "lane.culture": "Culture / events",
      "lane.cluster": "Sports · World Cup cluster",
      "lane.nba": "NBA",
      "lane.tech": "Tech",
      "lane.sports": "Sports · other",
      "res.title": "What we are researching",
      "res.lead": "Hunt is not one locked mascot. Copy stays off.",
      "res.nowK": "Now",
      "res.nowT": "Already running, twice an hour",
      "res.now1": "Sports — tennis (Antblack WAIT). Esports cut after invorser.",
      "res.now2": "Politics, culture, tech, finance, economics — same $5 / $15 gates.",
      "res.now3": "Last run: 994 new names. Nobody cleared 90d + book + CopyGrade.",
      "res.now4": "WAIT on the board: Antblack (76d tennis), 86shin (politics, thin sample).",
      "res.nextK": "Next runs",
      "res.nextT": "Hunt at :20 and :50 UTC",
      "res.next1": "Deeper leaderboards (higher offsets), not the same top 50.",
      "res.next2": "CopyGrade again — Dreamlawn hit rate limit, sim only +$4.4.",
      "res.next3": "Hunt 90d+ with conc ≤ 0.45, no candles, not Avoid — better than Antblack.",
      "res.next4": "Sports without esports and without World Cup clusters (Jittz / Daemon99).",
      "res.laterK": "Still on the table",
      "res.laterT": "Not this cycle, still in lab reach",
      "res.later1": "Crypto that is not 5-minute Bitcoin candles.",
      "res.later2": "NBA / tennis split, weather / geo if the board has it.",
      "res.later3": "Merlin all-time mid-tier the first pass did not reach.",
      "res.later4": "Never: Top 8, invorser, PoppyG / Bromsloy, CopyGrade Avoid.",
      "poly.title": "PolyCop card",
      "poly.lead": "Prepared like last time: one address, everyone else Paused, small caps. Copy stays off. This session does not click Telegram — no API. You enable nothing.",
      "poly.off": "COPY OFF — card ready, bot is not trading.",
      "poly.pauseK": "These stay Paused (not Active, not All Copy)",
      "sim.title": "Simulation",
      "sim.lead": "Not your live cash. Lab test: copy at $5, ignore under $20, $15 max in market.",
      "sim.p1k": "Today",
      "sim.p1t": "Hunt, copy off",
      "sim.p2k": "Later, maybe",
      "sim.p2t": "Antblack tennis",
      "sim.p3k": "Never",
      "sim.p3t": "Fat sim",
      "sim.charts": "Charts",
      "sim.chartsLead": "One language. One takeaway under each chart.",
      "sim.aTitle": "How many names die before copy?",
      "sim.aAsk": "Each bar is a wallet count. Full month board, drop too-new names, simulate a slice, keep those in profit on both 60d and 90d.",
      "sim.bTitle": "If you copied at $5, what did 90 days pay?",
      "sim.bAsk": "This is a sim, not live. Yellow = WAIT, still off. Grey = rejected even if the bar is tall.",
      "sim.cTitle": "One event, or a real book?",
      "sim.cAsk": "Share of P&L in one market. Above 0.45 (45%) is a lottery. Red = do not copy.",
      "sim.table": "Hunt results",
      "sim.thCall": "Call",
      "sim.thWallet": "Wallet",
      "sim.thDays": "Days",
      "sim.thWhy": "Why",
      "sim.wait": "WAIT",
      "sim.no": "NO",
      "sim.axisCount": "How many wallets",
      "sim.axisPnl": "Lab $ at $5 copy (not live)",
      "sim.axisConc": "0 = many markets · 1 = one event · red > 0.45",
      "sim.funnelLabs": "Looked at|Too new|Had 60d|We simulated|Profit 60d and 90d",
      "money.title": "Where the money is",
      "money.lead": "Your USDC in the PolyCop wallet. This site holds nothing.",
      "money.cash": "Now in PolyCop W1",
      "money.hole": "Invorser night (esports)",
      "money.spend": "Max in market if you enable",
      "money.sl": "New stop (not $42)",
      "money.k1": "Whose",
      "money.t1": "Yours, in Telegram",
      "money.p1": "Trading wallet of @PolyCop_BOT (W1). GitHub and hunt do not move cash.",
      "money.k2": "How it got to ~$39",
      "money.t2": "~$53 → invorser → $39.08",
      "money.p2": "21–22 Aug 2026: copy invorser (LoL / CS / Dota). $52.66 → $39.08, −$13.58. The bot paused copy.",
      "money.k3": "$15 and $31",
      "money.t3": "Caps, not extra cash",
      "money.p3": "$15 = max in market later. $31 = new balance stop. Nothing moves today.",
      "how.title": "How it works",
      "how.lead": "Short. One language.",
      "how.q1": "What is this page?",
      "how.a1": "A lab board. It does not buy or sell. Copy only in @PolyCop_BOT. No second bot.",
      "how.q2": "Who sets PolyCop wallets?",
      "how.a2": "The lab (Cursor) prepares one address here. Hunt only searches. This session cannot click Telegram. You do not rebuild the list. When it is time: paste one address and Turn On Copy.",
      "how.q3": "What do you not press?",
      "how.a3": "Turn On All Copy. That enables everyone — that is how invorser burned.",
      "how.q4": "Where is the simulation?",
      "how.a4": "The Simulation tab: three paths, three charts, hunt table. The open page refreshes every 15s. Hunt on GitHub at :20 and :50 UTC.",
      "how.q5": "When do we enable?",
      "how.a5": "When WAIT also has ≥90 days, both windows green, conc ≤ 0.45, CopyGrade not Avoid. Not today.",
      "how.card": "PolyCop paste card (later)",
      "how.cardLead": "The lab fills it. Do not press All Copy.",
      "how.ban": "Do not paste",
      "pred.a": "Forecast: $0 extra copy loss. Hunt checked {n} new wallets. Nobody cleared 90d + book + CopyGrade together. Wait. Do not bleed the $39.",
      "pred.b": "Lab: 60d {w60} / 90d {w90} at $5 copy, tennis, conc 0.11. 60d pace ≈ ${per30} / 30 days — not a promise. 76-day track. Does not fill a −$13.58 hole fast.",
      "pred.c": "Fat sims are one event, 5-min Bitcoin candles, or CopyGrade Avoid. Pasting them is the invorser error again.",
      "read.funnel": "Now: {u} names → {drop} too new → only {both} in profit on 60d and 90d. A tiny last bar is expected.",
      "read.pnl": "Yellow / WAIT: {names}. A tall grey bar is not a pick.",
      "read.conc": "{hot} Red = one event. Do not paste.",
      "read.concNone": "No red bars in this slice. ",
      "hunt.line": "Hunt at :20 and :50 UTC. Last run: {n} new names. WAIT = almost. NO = reject. Hunt never enables the bot.",
      "hunt.missing": "Hunt file missing",
      "hunt.running": "HUNT RUNNING · ",
      "hunt.last": "last hunt ",
      "cap.active": "Active wallets",
      "cap.activeV": "Antblack — prepared, Paused. Copy OFF. Everyone else Paused too.",
      "cap.addr": "Address",
      "cap.fixed": "Fixed / max Yes-No / max market",
      "cap.ignore": "Ignore below",
      "cap.spend": "Total spend",
      "cap.sl": "Balance SL",
      "cap.all": "Turn On All Copy",
      "cap.never": "Never"
    }
  };

  const charts = {};
  const state = { snap: null, user: null, role: null, hunt: null, lang: "pl", lane: null };
  const LANE_ORDER = ["tennis", "finance", "politics", "crypto", "culture", "cluster", "nba", "tech", "sports"];
  const VIEWS = ["do", "sim", "poly", "money", "how"];

  function $(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
  function t(key) {
    const pack = I18N[state.lang] || I18N.pl;
    return pack[key] || (I18N.en[key] || key);
  }
  function fmt(key, vars) {
    return t(key).replace(/\{(\w+)\}/g, function (_, k) {
      return vars[k] == null ? "" : String(vars[k]);
    });
  }
  function money(n, digits) {
    if (n == null || Number.isNaN(Number(n))) return "—";
    const d = digits == null ? 1 : digits;
    const v = Number(n);
    return (v < 0 ? "−$" : "+$") + Math.abs(v).toFixed(d);
  }
  function usd(n) {
    if (n == null || Number.isNaN(Number(n))) return "—";
    return "$" + Number(n).toFixed(2);
  }
  function conc(n) {
    if (n == null || Number.isNaN(Number(n))) return "—";
    return Number(n).toFixed(2);
  }
  async function sha256hex(text) {
    const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
    return Array.from(new Uint8Array(buf)).map(function (b) {
      return b.toString(16).padStart(2, "0");
    }).join("");
  }
  function unlocked() { return sessionStorage.getItem("copy-lab-ok") === "1"; }
  function unlockSession() { sessionStorage.setItem("copy-lab-ok", "1"); }
  function roleOf(email) {
    const cfg = window.OPS_CONFIG || { owners: [], viewers: [] };
    const e = (email || "").toLowerCase();
    if ((cfg.owners || []).map(function (x) { return x.toLowerCase(); }).indexOf(e) !== -1) return "owner";
    if ((cfg.viewers || []).map(function (x) { return x.toLowerCase(); }).indexOf(e) !== -1) return "viewer";
    return null;
  }

  function applyLang() {
    document.documentElement.lang = state.lang;
    document.querySelectorAll("[data-i18n]").forEach(function (el) {
      el.textContent = t(el.getAttribute("data-i18n"));
    });
    document.querySelectorAll(".lang button").forEach(function (btn) {
      btn.classList.toggle("on", btn.getAttribute("data-lang") === state.lang);
    });
    try { localStorage.setItem("copy-lab-lang", state.lang); } catch (e) { /* ignore */ }
  }

  function viewFromHash() {
    const h = (location.hash || "").replace("#", "");
    return VIEWS.indexOf(h) !== -1 ? h : "do";
  }

  function showView(name) {
    const view = VIEWS.indexOf(name) !== -1 ? name : "do";
    VIEWS.forEach(function (id) {
      const el = $("view-" + id);
      if (!el) return;
      const on = id === view;
      el.classList.toggle("hidden", !on);
      el.hidden = !on;
    });
    document.querySelectorAll(".nav button").forEach(function (btn) {
      btn.classList.toggle("on", btn.getAttribute("data-view") === view);
    });
    try { history.replaceState(null, "", "#" + view); } catch (e) { /* ignore */ }
    if (view === "sim") {
      Object.keys(charts).forEach(function (id) {
        if (charts[id] && typeof charts[id].resize === "function") charts[id].resize();
      });
    }
  }

  function setLang(lang) {
    state.lang = lang === "en" ? "en" : "pl";
    applyLang();
    if (state.snap) renderAll();
  }

  function showApp() {
    $("gate").classList.add("hidden");
    $("gate").hidden = true;
    $("app").classList.remove("hidden");
    $("app").hidden = false;
    $("who").textContent = (state.user && state.user.email) || "damianbiniarz@gmail.com";
    applyLang();
    showView(viewFromHash());
  }

  function showGate(msg) {
    $("app").classList.add("hidden");
    $("app").hidden = true;
    $("gate").classList.remove("hidden");
    $("gate").hidden = false;
    $("gate-msg").textContent = msg || "";
  }

  async function tryPageCode() {
    const typed = ($("page-code").value || "").trim();
    const expect = (window.OPS_CONFIG && window.OPS_CONFIG.pageCodeSha256) || "";
    if (!typed || !expect) {
      showGate(t("gate.needPass"));
      return;
    }
    const hex = await sha256hex(typed);
    if (hex !== expect) {
      showGate(t("gate.wrong"));
      return;
    }
    unlockSession();
    state.role = "owner";
    showApp();
    renderAll();
  }

  function firebaseReady() {
    const cfg = window.OPS_CONFIG && window.OPS_CONFIG.firebase;
    return cfg && cfg.apiKey && window.firebase;
  }

  function classifyHunt(row, official) {
    const cg = row.copygrade || {};
    const label = String(cg.label || "");
    const w60 = Number(row.w60 || 0);
    const w90 = Number(row.w90 || 0);
    const c = Number(row.conc || 1);
    const days = Number(row.history_days || 0);
    const copies = Number(row.copies || 0);
    const candle = Number(row.candle || 0);
    const o60 = official && official.w60 != null ? Number(official.w60) : 17;
    const o90 = official && official.w90 != null ? Number(official.w90) : 9.2;
    if (label.indexOf("Avoid") !== -1) {
      return { call: "reject", why: state.lang === "pl" ? "CopyGrade Avoid — follower nie jest płacony po prowizji." : "CopyGrade Avoid — follower is not paid after fees." };
    }
    if (candle > 0.25) {
      return { call: "reject", why: state.lang === "pl" ? "Książka świec 5 min. Copy $5 się kręci w miejscu." : "5-minute candle book. A $5 copier churns." };
    }
    if (w60 <= 0 || w90 <= 0) {
      return { call: "reject", why: state.lang === "pl" ? "Brak zysku w 60d albo 90d w labie." : "Not profitable in both 60d and 90d lab windows." };
    }
    if (c > 0.45) {
      return { call: "reject", why: state.lang === "pl"
        ? ("Top rynek " + Math.round(c * 100) + "% |PnL| — jeden event, nie książka.")
        : ("Top market " + Math.round(c * 100) + "% of |PnL| — one event, not a book.") };
    }
    if (copies < 6) {
      return { call: "reject", why: state.lang === "pl" ? "Za mało filli do skopiowania przy spend $15." : "Fewer than 6 copyable fills under $15 spend." };
    }
    if (w60 > o60 && w90 > o90 && c <= 0.45 && days >= 90) {
      return { call: "wait", why: state.lang === "pl" ? "Lepszy od Antblack na obu oknach, 90d track. Copy i tak wyłączasz Ty." : "Beats Antblack on both windows with a 90d track. Still your enable in PolyCop." };
    }
    if (days < 90) {
      return { call: "wait", why: state.lang === "pl" ? "Oba okna na plusie, track pod 90 dni — ryzyko serii." : "Both windows green, track under 90 days — streak risk." };
    }
    if (w60 < 8 && w90 < 8) {
      return { call: "reject", why: state.lang === "pl" ? "Za mały edge względem dziury $13.58." : "Lab edge too small versus a $13.58 hole." };
    }
    return { call: "wait", why: state.lang === "pl" ? "Część sitów, nie wszystkie." : "Partial gates only." };
  }

  function officialWatch(s) {
    return ((s.board || {}).options || []).find(function (r) { return r.name === "Antblack"; }) || s.solution || {};
  }

  function fieldRows(s, hunt) {
    const known = {};
    const rows = ((s.board || {}).options || []).slice();
    rows.forEach(function (r) { known[(r.name || "").toLowerCase()] = true; });
    const official = officialWatch(s);
    (hunt && hunt.candidates || []).forEach(function (h) {
      const name = h.username || "";
      if (known[name.toLowerCase()]) return;
      known[name.toLowerCase()] = true;
      const cls = classifyHunt(h, official);
      rows.push({
        name: name,
        domain: h.cat || h.domain || "",
        source: "hunt",
        call: cls.call,
        why_short: cls.why,
        meaning: cls.why,
        w60: h.w60,
        w90: h.w90,
        days: h.history_days,
        conc: h.conc
      });
    });
    rows.sort(function (a, b) {
      if (a.call === "wait" && b.call !== "wait") return -1;
      if (b.call === "wait" && a.call !== "wait") return 1;
      return (Number(b.w90) || 0) - (Number(a.w90) || 0);
    });
    return rows;
  }

  function rowLane(r) {
    const name = String(r.name || "").toLowerCase();
    const place = [r.domain, r.cat, r.source, r.top_market].join(" ").toLowerCase();
    const cat = String(r.cat || "").toUpperCase();
    if (name === "antblack") return "tennis";
    if (name === "86shin") return "politics";
    if (name === "poppyg" || name === "bromsloy142515") return "crypto";
    if (name === "gabriell11") return "culture";
    if (name === "jittz" || name === "daemon99" || name === "0x760f1063" || name === "gambamaster") return "cluster";
    if (name === "martingaleking") return "nba";
    if (name === "dreamlawn") return "finance";
    if (/candle|bitcoin|btc 5|up or down|5-min|5 min/.test(place)) return "crypto";
    if (/gta|culture/.test(place)) return "culture";
    if (/world cup|mundial/.test(place)) return "cluster";
    if (/\bnba\b/.test(place)) return "nba";
    if (/tennis|tenis/.test(place)) return "tennis";
    if (/politic|thai/.test(place) || cat === "POLITICS") return "politics";
    if (/econ|fed|financ|stock|akcj|interest rate/.test(place) ||
        cat === "FINANCE" || cat === "ECONOMICS") return "finance";
    if (cat === "TECH" || /\btech\b/.test(place)) return "tech";
    if (/sport|esport/.test(place) || cat === "SPORTS") return "sports";
    return "sports";
  }

  function buildLanes(s, rows) {
    const bags = {};
    LANE_ORDER.forEach(function (id) { bags[id] = []; });
    rows.forEach(function (r) {
      const id = rowLane(r);
      if (!bags[id]) bags[id] = [];
      bags[id].push(r);
    });
    (s.do_not_copy || []).forEach(function (b) {
      const fake = { name: b.name, domain: b.why || "", call: "reject", why_short: b.why };
      const id = rowLane(fake);
      const have = (bags[id] || []).some(function (r) {
        return (r.name || "").toLowerCase() === (b.name || "").toLowerCase();
      });
      if (!have) bags[id].push(fake);
    });
    return LANE_ORDER.map(function (id) {
      const list = bags[id] || [];
      const waits = list.filter(function (r) { return r.call === "wait"; });
      const best = (waits[0] || list.slice().sort(function (a, b) {
        return (Number(b.w90) || 0) - (Number(a.w90) || 0);
      })[0] || null);
      let tone = "cold";
      if (id === "crypto" || id === "culture" || id === "cluster") tone = "no";
      if (waits.length) tone = "wait";
      else if (list.length && list.every(function (r) { return r.call === "reject"; })) tone = "no";
      if (id === "crypto") tone = "no";
      let why = "";
      if (id === "crypto") {
        why = state.lang === "pl"
          ? "Bitcoin 5 min. Copy $5 się kręci. PoppyG / Bromsloy zostają NIE."
          : "5-minute Bitcoin. A $5 copier churns. PoppyG / Bromsloy stay NO.";
      } else if (best) {
        why = best.why_short || best.meaning || "";
      } else {
        why = state.lang === "pl" ? "Hunt nie znalazł nazwy na tym torze." : "Hunt found no name on this lane.";
      }
      let move = t("lane.switchNo");
      if (tone === "wait" && waits.length === 1 && id === "tennis") move = t("lane.switchOnly");
      else if (tone === "wait") move = t("lane.switchLook");
      return {
        id: id,
        tone: tone,
        waits: waits.length,
        n: list.length,
        best: best,
        why: why,
        move: move
      };
    });
  }

  function renderLanes(s, rows) {
    const lanes = buildLanes(s, rows);
    const waits = lanes.filter(function (l) { return l.tone === "wait"; });
    const top = waits[0];
    if ($("lane-head")) {
      $("lane-head").textContent = top
        ? fmt("lane.headWait", { name: t("lane." + top.id) })
        : t("lane.headNone");
    }
    if (!$("lane-grid")) return;
    $("lane-grid").innerHTML = lanes.map(function (l) {
      const bestName = l.best ? l.best.name : "—";
      const nums = l.best && l.best.w90 != null
        ? ("60d " + money(l.best.w60) + " · 90d " + money(l.best.w90))
        : "";
      const on = state.lane === l.id ? " on" : "";
      return '<button type="button" class="lane ' + l.tone + on + '" data-lane="' + l.id + '">' +
        '<p class="kicker">' + esc(t("lane." + l.tone)) + "</p>" +
        "<h3>" + esc(t("lane." + l.id)) + "</h3>" +
        '<p class="who-best">' + esc(bestName) + (nums ? " · " + nums : "") + "</p>" +
        "<p>" + esc(l.why) + "</p>" +
        '<p class="move">' + esc(l.move) + " · " + esc(t("lane.open")) + "</p>" +
        "</button>";
    }).join("");
    $("lane-grid").querySelectorAll("[data-lane]").forEach(function (btn) {
      btn.onclick = function () {
        state.lane = btn.getAttribute("data-lane");
        showView("sim");
        renderAll();
      };
    });
    if ($("lane-filter")) {
      if (state.lane) {
        $("lane-filter").hidden = false;
        $("lane-filter").innerHTML = esc(fmt("lane.filter", { name: t("lane." + state.lane) })) +
          " <button type='button' class='btn ghost' id='lane-clear'>" + esc(t("lane.clear")) + "</button>";
        const clr = $("lane-clear");
        if (clr) clr.onclick = function () { state.lane = null; renderAll(); };
      } else {
        $("lane-filter").hidden = true;
        $("lane-filter").textContent = "";
      }
    }
  }

  function rowHtml(r) {
    const call = r.call === "wait" ? "wait" : "reject";
    return '<tr class="' + call + '"><td><span class="pill ' + call + '">' +
      (call === "wait" ? t("sim.wait") : t("sim.no")) + "</span></td>" +
      '<td><span class="name">' + esc(r.name) + '</span><span class="src">' +
      esc((r.domain || "") + (r.source ? " · " + r.source : "")) + "</span></td>" +
      "<td>" + money(r.w60) + "</td><td>" + money(r.w90) + "</td>" +
      "<td>" + (r.days != null ? Math.round(r.days) + "d" : "—") + "</td>" +
      "<td>" + conc(r.conc) + "</td>" +
      "<td>" + esc(r.why_short || r.meaning || "") + "</td></tr>";
  }

  function drawH(id, labels, data, colors, xTitle) {
    if (!$(id) || !window.Chart) return;
    if (charts[id]) charts[id].destroy();
    Chart.defaults.color = "#b4b4b0";
    Chart.defaults.borderColor = "#2a2a2e";
    Chart.defaults.font.family = "Instrument Sans, Segoe UI, sans-serif";
    charts[id] = new Chart($(id).getContext("2d"), {
      type: "bar",
      data: {
        labels: labels,
        datasets: [{
          data: data,
          backgroundColor: colors || "#8bb4ff",
          borderRadius: 8,
          borderSkipped: false
        }]
      },
      options: {
        indexAxis: "y",
        animation: { duration: 700, easing: "easeOutQuart" },
        plugins: { legend: { display: false } },
        scales: {
          x: {
            beginAtZero: true,
            title: { display: true, text: xTitle },
            grid: { color: "rgba(255,255,255,0.06)" }
          },
          y: { ticks: { autoSkip: false }, grid: { display: false } }
        }
      }
    });
  }

  function renderCharts(s, rows) {
    const f = s.funnel_month || {};
    drawH("chart-funnel",
      t("sim.funnelLabs").split("|"),
      [f.unique || 0, f.history_lt_60d || 0, f.history_pass || 0, f.simulated || 0, f.both_windows || 0],
      "#8bb4ff",
      t("sim.axisCount")
    );
    const top = rows.slice(0, 8);
    drawH("chart-pnl",
      top.map(function (r) { return r.name; }),
      top.map(function (r) { return Number(r.w90) || 0; }),
      top.map(function (r) { return r.call === "wait" ? "#ffc14a" : "rgba(255,255,255,0.18)"; }),
      t("sim.axisPnl")
    );
    const concRows = (s.concentration || []).slice(0, 8);
    drawH("chart-conc",
      concRows.map(function (c) { return c.name; }),
      concRows.map(function (c) { return c.share; }),
      concRows.map(function (c) { return c.share > 0.45 ? "#ff5d5d" : "#8bb4ff"; }),
      t("sim.axisConc")
    );
  }

  function renderChartReads(s, rows) {
    const f = s.funnel_month || {};
    if ($("read-funnel")) {
      $("read-funnel").textContent = fmt("read.funnel", {
        u: f.unique || 0, drop: f.history_lt_60d || 0, both: f.both_windows || 0
      });
    }
    const wait = rows.filter(function (r) { return r.call === "wait"; });
    const names = wait.slice(0, 3).map(function (r) { return r.name; }).join(", ") || "—";
    if ($("read-pnl")) $("read-pnl").textContent = fmt("read.pnl", { names: names });
    const hot = (s.concentration || []).filter(function (c) { return c.share > 0.45; }).slice(0, 3)
      .map(function (c) { return c.name; });
    if ($("read-conc")) {
      $("read-conc").textContent = fmt("read.conc", {
        hot: hot.length ? hot.join(", ") + "." : t("read.concNone")
      });
    }
  }

  function renderPredict(s, hunt) {
    const n = hunt && hunt.checked ? hunt.checked : 0;
    const ant = officialWatch(s);
    const per30 = ant.w60 != null ? (Number(ant.w60) / 2).toFixed(1) : "8.5";
    if ($("pred-a")) $("pred-a").textContent = fmt("pred.a", { n: n });
    if ($("pred-b")) {
      $("pred-b").textContent = fmt("pred.b", {
        w60: money(ant.w60), w90: money(ant.w90), per30: per30
      });
    }
    if ($("pred-c")) $("pred-c").textContent = t("pred.c");
  }

  function renderBans(s) {
    const onBoard = {};
    ((s.board || {}).options || []).forEach(function (r) { onBoard[(r.name || "").toLowerCase()] = true; });
    $("ban-list").innerHTML = (s.do_not_copy || []).filter(function (r) {
      return !onBoard[(r.name || "").toLowerCase()];
    }).map(function (r) {
      return "<li><b>" + esc(r.name) + "</b> — " + esc(r.why) + "</li>";
    }).join("");
  }

  function rosterHtml(s) {
    const p = (s.board && s.board.override) || s.solution || {};
    const caps = s.caps_if_enabled_later || {};
    const rows = [
      [t("cap.active"), t("cap.activeV")],
      [t("cap.addr"), p.address || ""],
      [t("cap.fixed"), "$" + (caps.fixed_usd || 5)],
      [t("cap.ignore"), "$" + (caps.ignore_below_usd || 20)],
      [t("cap.spend"), "$" + (caps.total_spend_usd || 15)],
      [t("cap.sl"), "$" + (caps.balance_sl_usd || 31)],
      [t("cap.all"), t("cap.never")]
    ];
    return "<p class='addr'>" + esc(p.name ? p.name + " · " : "") + esc(p.address || "") +
      "</p><table class='caps'><tbody>" + rows.map(function (r) {
        return "<tr><td>" + esc(r[0]) + "</td><td>" + esc(r[1]) + "</td></tr>";
      }).join("") + "</tbody></table>";
  }

  function renderOverride(s) {
    const html = rosterHtml(s);
    if ($("override-box")) $("override-box").innerHTML = html;
    if ($("poly-box")) $("poly-box").innerHTML = html;
    if ($("poly-pause")) {
      const names = {};
      (s.do_not_copy || []).forEach(function (r) {
        names[(r.name || "").toLowerCase()] = r;
      });
      ((s.board || {}).options || []).forEach(function (r) {
        if (r.call === "reject") names[(r.name || "").toLowerCase()] = { name: r.name, why: r.why_short || r.meaning };
      });
      $("poly-pause").innerHTML = Object.keys(names).map(function (k) {
        const r = names[k];
        return "<li><b>" + esc(r.name) + "</b> — " + esc(r.why || "") + "</li>";
      }).join("");
    }
  }

  async function loadHunt() {
    try {
      const h = await (await fetch("./data/hunt.json?t=" + Date.now())).json();
      state.hunt = h;
      let pulse = "";
      try {
        const p = await (await fetch("./data/pulse.json?t=" + Date.now())).json();
        if (p.hunt === "running") pulse = t("hunt.running");
      } catch (e) { /* optional */ }
      const when = h.updated_at ? String(h.updated_at).replace("T", " ").slice(0, 16) + " UTC" : "?";
      $("hunt-pulse").textContent = pulse + t("hunt.last") + when;
      $("hunt-plain").textContent = fmt("hunt.line", { n: h.checked || 0 });
    } catch (e) {
      $("hunt-pulse").textContent = t("hunt.missing");
    }
  }

  async function renderAll() {
    const s = state.snap;
    if (!s) return;
    applyLang();
    const cash = usd(s.cash_usd);
    if ($("s-cash")) $("s-cash").textContent = cash;
    if ($("m-cash")) $("m-cash").textContent = cash;
    $("s-live").textContent = money(s.last_live_pnl_usd, 2);
    renderBans(s);
    renderOverride(s);
    await loadHunt();
    const rows = fieldRows(s, state.hunt);
    renderLanes(s, rows);
    const shown = state.lane
      ? rows.filter(function (r) { return rowLane(r) === state.lane; })
      : rows;
    $("field-body").innerHTML = shown.map(rowHtml).join("");
    renderPredict(s, state.hunt);
    renderCharts(s, shown);
    renderChartReads(s, shown);
    if (viewFromHash() === "sim") {
      Object.keys(charts).forEach(function (id) {
        if (charts[id] && typeof charts[id].resize === "function") charts[id].resize();
      });
    }
  }

  async function bootFirebase() {
    if (!firebaseReady()) return false;
    firebase.initializeApp(window.OPS_CONFIG.firebase);
    $("btn-google").hidden = false;
    $("btn-google").onclick = function () {
      firebase.auth().signInWithPopup(new firebase.auth.GoogleAuthProvider());
    };
    firebase.auth().onAuthStateChanged(function (user) {
      if (!user) return;
      const role = roleOf(user.email);
      if (!role) {
        showGate("Google " + user.email + " is not on the allowlist.");
        return;
      }
      unlockSession();
      state.user = user;
      state.role = role;
      showApp();
      renderAll();
    });
    return true;
  }

  function bind() {
    if ($("btn-code")) $("btn-code").onclick = tryPageCode;
    if ($("page-code")) {
      $("page-code").addEventListener("keydown", function (ev) {
        if (ev.key === "Enter") tryPageCode();
      });
    }
    document.querySelectorAll("[data-view]").forEach(function (btn) {
      btn.onclick = function () { showView(btn.getAttribute("data-view")); };
    });
    document.querySelectorAll(".lang button").forEach(function (btn) {
      btn.onclick = function () { setLang(btn.getAttribute("data-lang")); };
    });
    window.addEventListener("hashchange", function () { showView(viewFromHash()); });
  }

  async function main() {
    try {
      const saved = localStorage.getItem("copy-lab-lang");
      if (saved === "en" || saved === "pl") state.lang = saved;
    } catch (e) { state.lang = "pl"; }
    bind();
    applyLang();
    try {
      const fbFile = await fetch("./firebase-config.js", { cache: "no-store" });
      if (fbFile.ok) {
        const el = document.createElement("script");
        el.textContent = await fbFile.text();
        document.head.appendChild(el);
      }
    } catch (e) { /* optional */ }
    state.snap = await (await fetch("./data/snapshot.json?t=" + Date.now())).json();
    const hasFb = await bootFirebase();
    const host = location.hostname;
    if ((host === "127.0.0.1" || host === "localhost") &&
        new URLSearchParams(location.search).get("lab") === "1") {
      unlockSession();
    }
    if (unlocked()) {
      state.role = state.role || "owner";
      showApp();
      renderAll();
    } else if (!hasFb) {
      showGate(t("gate.noGoogle"));
    } else {
      showGate("");
    }
    setInterval(function () {
      if (unlocked()) renderAll();
    }, 15000);
  }

  main().catch(function (err) {
    showGate(String(err));
  });
})();
