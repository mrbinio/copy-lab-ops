/* Copy Lab board. Does not place trades. */
(function () {
  const I18N = {
    pl: {
      "gate.lede": "Zdalna tablica. Nie handluje. Email z listy + hasło z czatu.",
      "gate.google": "Dalej z Google",
      "gate.email": "Email",
      "gate.pass": "Hasło strony",
      "gate.open": "Otwórz",
      "gate.needPass": "Wpisz hasło ze czatu.",
      "gate.needEmail": "Podaj email z listy.",
      "gate.unknown": "Tego emaila nie ma na liście.",
      "gate.wrong": "Złe hasło.",
      "gate.noGoogle": "Wpisz email i hasło ze czatu.",
      "who.ro": "odczyt",
      "who.out": "Wyloguj / zmień konto",
      "gate.switched": "Sesja skasowana. Wpisz inny email z listy.",
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
      "do.s1": "Copy OFF. Hunt szuka 24/7 na GitHubie (~10 min między biegami). Ty nic nie robisz.",
      "do.s2t": "Następne",
      "do.s2": "Lab znajdzie jeden portfel z 90 dniami historii, zyskiem w 60d i 90d, bez jednego eventa. Adres pojawi się tutaj.",
      "do.s3t": "Potem",
      "do.s3": "Wklejasz ten jeden adres w @PolyCop_BOT. Reszta Paused. Klikasz Turn On Copy — nie All Copy.",
      "do.briefK": "Co robić dziś",
      "do.briefVerb": "NIE WŁĄCZAJ",
      "do.briefWait": "Najcieplejszy tor: {lane} ({name}, 60/90 {w60} / {w90}). To WAIT w labie, nie kupno. Patrz w Symulacji. W Telegramie nic nie klikasz. Antblack i 86shin zostają Paused.",
      "do.briefNone": "Żaden tor nie przeszedł sitów. Dziś nic nie włączasz i nic nie dokupujesz. Crypto-świece zostają NIE.",
      "do.pathK": "Najbliższa ścieżka",
      "do.nextK": "Hunt teraz szuka",
      "do.solClaude": "Claude z taśmy huntu. Nie włącza copy.",
      "do.solLab": "Z liczb huntu. Claude bez klucza — ten sam werdykt z sitów.",
      "do.warn": "Turn On All Copy włącza całą starą listę. Tak poszła strata −$13.58 na invorserze.",
      "lane.title": "Rynki teraz",
      "lane.lead": "Który tor ma edge, a który jest martwy. Hunt przepisuje taśmę w pętli 24/7. Klik otwiera nazwy w Symulacji. Copy sam się nie przełącza.",
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
      "spot.title": "Ceny spot",
      "spot.lead": "Wybierz krypto i zakres. Ceny z Binance, dopóki karta jest otwarta. To nie sygnał do copy. Świece 5 min zostają NIE.",
      "spot.live": "na żywo",
      "spot.poll": "co 3 sekundy",
      "spot.off": "brak feedu — odśwież kartę",
      "spot.chart": "{name} · {range}",
      "spot.chg": "{pct} · 24 godz.",
      "spot.pick": "Krypto",
      "spot.pickPh": "Wybierz z listy",
      "spot.range.h1": "1 godz.",
      "spot.range.h3": "3 godz.",
      "spot.range.w1": "tydzień",
      "spot.range.m1": "miesiąc",
      "spot.range.y1": "rok",
      "res.title": "Jakie rozwiązania badamy",
      "res.lead": "Hunt nie zamyka się na jednego maskota. Copy zostaje off.",
      "res.nowK": "Teraz",
      "res.nowT": "Już leci, 24/7 na GitHubie",
      "res.now1": "Sport — tenis (Antblack WAIT). Esport wycięty po invorserze.",
      "res.now2": "Polityka, kultura, tech, finanse, ekonomia — te same sity $5 / $15.",
      "res.now3": "Ostatni bieg: 994 nowe nazwy. Nikt nie przeszedł 90d + książka + CopyGrade.",
      "res.now4": "WAIT na tablicy: Antblack (76d tenis), 86shin (polityka, cienka próbka).",
      "res.nextK": "Następne biegi",
      "res.nextT": "Pętla 24/7, ~10 min przerwy",
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
      "poly.lead": "Dwa adresy w bocie, oba Paused: Antblack (tenis) i 86shin (polityka). Capy $5 / $20 / $15 / SL $31. Copy off. Nie All Copy.",
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
      "how.a4": "Zakładka Symulacja: trzy ścieżki, trzy wykresy, tabela huntu. Odświeża się co 15 sekund. Hunt 24/7 na GitHubie.",
      "how.q5": "Kiedy w ogóle włączamy?",
      "how.a5": "Gdy WAIT ma też ≥90 dni, zysk w 60d i 90d, conc ≤ 0.45, CopyGrade nie Avoid. Dziś tego nie ma.",
      "how.q6": "Skąd żywe ceny krypto?",
      "how.a6": "Z Binance, w Twojej przeglądarce. Wybierasz krypto i zakres. GitHub ich nie serwuje. Strona nic nie kupuje. To nie sygnał do copy.",
      "how.q7": "Co robi Claude?",
      "how.a7": "Po każdym huncie czyta taśmę i pisze najbliższą ścieżkę $5 / $15 plus gdzie szukać dalej. Nie włącza copy. Sity zostają sitem.",
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
      "hunt.line": "Hunt 24/7 na GitHubie. Ostatni bieg: {n} nowych nazw. CZEKAJ = prawie. NIE = odrzut. Hunt nie włącza bota.",
      "hunt.missing": "Brak pliku huntu",
      "hunt.running": "HUNT DZIAŁA · ",
      "hunt.runningSince": "HUNT DZIAŁA od {t} · ",
      "hunt.last": "ostatni hunt ",
      "hunt.lastDone": "ostatni skończony ",
      "cap.active": "Aktywne portfele",
      "journal.title": "Dziennik huntu",
      "journal.lead": "Ostatni bieg sitka. Hunt nic nie włącza. Czerwone = odrzut. Żółte = prawie, nadal off.",
      "journal.head": "Ostatni bieg: {n} nowych nazw, {q} poszło do sima. Żaden tor nie skoczył na WAIT do włączenia.",
      "journal.headFlip": "Ostatni bieg: {n} nazw. Tor {name} skoczył na WAIT. Nadal nie włączasz.",
      "journal.checked": "Nowe nazwy",
      "journal.queued": "Do sima",
      "journal.pre": "Odpadło przed simem",
      "journal.wait": "WAIT w simie",
      "journal.none": "Brak taśmy z ostatniego biegu.",
      "journal.why.avoid": "CopyGrade Avoid",
      "journal.why.candle": "Świece 5 min",
      "journal.why.one_event": "Jeden event / conc > 0.45",
      "journal.why.no_both": "Brak zysku w 60d i 90d",
      "journal.why.short": "Za krótki track na 90d",
      "journal.why.partial": "Część sitów — nadal WAIT",
      "cap.activeV": "Antblack i 86shin — oba Paused. Copy OFF. Nie All Copy.",
      "cap.addr": "Adres",
      "cap.fixed": "Fixed / max Yes-No / max rynek",
      "cap.ignore": "Ignore poniżej",
      "cap.spend": "Total spend",
      "cap.sl": "Balance SL",
      "cap.all": "Turn On All Copy",
      "cap.paused": "Paused",
      "cap.never": "Nigdy"
    },
    en: {
      "gate.lede": "Remote board. Does not trade. Allowlisted email + password from chat.",
      "gate.google": "Continue with Google",
      "gate.email": "Email",
      "gate.pass": "Page password",
      "gate.open": "Open",
      "gate.needPass": "Enter the page password from chat.",
      "gate.needEmail": "Enter your allowlisted email.",
      "gate.unknown": "This email is not on the list.",
      "gate.wrong": "Wrong password.",
      "gate.noGoogle": "Enter your email and the page password from chat.",
      "who.ro": "read only",
      "who.out": "Sign out / switch account",
      "gate.switched": "Signed out. Enter a different allowlisted email.",
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
      "do.s1": "Copy OFF. Hunt searches 24/7 on GitHub (~10 min between runs). You do nothing.",
      "do.s2t": "Next",
      "do.s2": "Lab finds one wallet with 90 days, profit in 60d and 90d, not one event. The address appears here.",
      "do.s3t": "Then",
      "do.s3": "Paste that one address in @PolyCop_BOT. Everyone else Paused. Press Turn On Copy — not All Copy.",
      "do.briefK": "What to do today",
      "do.briefVerb": "DO NOT ENABLE",
      "do.briefWait": "Warmest lane: {lane} ({name}, 60/90 {w60} / {w90}). That is WAIT in the lab, not a buy. Look in Simulation. Do nothing in Telegram. Antblack and 86shin stay Paused.",
      "do.briefNone": "No lane cleared the gates. Do not enable and do not add cash. Candle crypto stays NO.",
      "do.pathK": "Closest path",
      "do.nextK": "Hunt is searching",
      "do.solClaude": "Claude from the hunt tape. Does not enable copy.",
      "do.solLab": "From hunt numbers. No Claude key — same gate verdict.",
      "do.warn": "Turn On All Copy enables the whole old list. That is how invorser lost −$13.58.",
      "lane.title": "Markets now",
      "lane.lead": "Which book has an edge and which is dead. Hunt rewrites the tape in a 24/7 loop. Click opens names in Simulation. Copy does not switch itself.",
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
      "spot.title": "Spot prices",
      "spot.lead": "Pick a coin and a range. Binance prices while this tab is open. Not a copy signal. 5-min candles stay NO.",
      "spot.live": "live",
      "spot.poll": "every 3 seconds",
      "spot.off": "no feed — refresh the tab",
      "spot.chart": "{name} · {range}",
      "spot.chg": "{pct} · 24h",
      "spot.pick": "Coin",
      "spot.pickPh": "Choose from the list",
      "spot.range.h1": "1 hour",
      "spot.range.h3": "3 hours",
      "spot.range.w1": "week",
      "spot.range.m1": "month",
      "spot.range.y1": "year",
      "res.title": "What we are researching",
      "res.lead": "Hunt is not one locked mascot. Copy stays off.",
      "res.nowK": "Now",
      "res.nowT": "Already running, 24/7 on GitHub",
      "res.now1": "Sports — tennis (Antblack WAIT). Esports cut after invorser.",
      "res.now2": "Politics, culture, tech, finance, economics — same $5 / $15 gates.",
      "res.now3": "Last run: 994 new names. Nobody cleared 90d + book + CopyGrade.",
      "res.now4": "WAIT on the board: Antblack (76d tennis), 86shin (politics, thin sample).",
      "res.nextK": "Next runs",
      "res.nextT": "24/7 loop, ~10 min pause",
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
      "poly.lead": "Two addresses in the bot, both Paused: Antblack (tennis) and 86shin (politics). Caps $5 / $20 / $15 / SL $31. Copy off. Not All Copy.",
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
      "how.a4": "The Simulation tab: three paths, three charts, hunt table. The open page refreshes every 15s. Hunt 24/7 on GitHub.",
      "how.q5": "When do we enable?",
      "how.a5": "When WAIT also has ≥90 days, both windows green, conc ≤ 0.45, CopyGrade not Avoid. Not today.",
      "how.q6": "Where do the live crypto prices come from?",
      "how.a6": "From Binance, in your browser. You pick the coin and the range. GitHub does not serve them. The page does not trade. This is not a signal to enable copy.",
      "how.q7": "What does Claude do?",
      "how.a7": "After each hunt it reads the tape and writes the closest $5 / $15 path plus where to search next. It does not enable copy. The gates stay the gates.",
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
      "hunt.line": "Hunt 24/7 on GitHub. Last run: {n} new names. WAIT = almost. NO = reject. Hunt never enables the bot.",
      "hunt.missing": "Hunt file missing",
      "hunt.running": "HUNT RUNNING · ",
      "hunt.runningSince": "HUNT RUNNING since {t} · ",
      "hunt.last": "last hunt ",
      "hunt.lastDone": "last finished ",
      "cap.active": "Active wallets",
      "journal.title": "Hunt log",
      "journal.lead": "Last sieve run. Hunt never enables copy. Red = reject. Yellow = almost, still off.",
      "journal.head": "Last run: {n} new names, {q} went to sim. No lane flipped to WAIT to enable.",
      "journal.headFlip": "Last run: {n} names. Lane {name} flipped to WAIT. Still do not enable.",
      "journal.checked": "New names",
      "journal.queued": "To sim",
      "journal.pre": "Dropped before sim",
      "journal.wait": "WAIT in sim",
      "journal.none": "No tape from the last run.",
      "journal.why.avoid": "CopyGrade Avoid",
      "journal.why.candle": "5-min candles",
      "journal.why.one_event": "One event / conc > 0.45",
      "journal.why.no_both": "Not profitable in 60d and 90d",
      "journal.why.short": "Track too short for 90d",
      "journal.why.partial": "Partial gates — still WAIT",
      "cap.activeV": "Antblack and 86shin — both Paused. Copy OFF. Not All Copy.",
      "cap.addr": "Address",
      "cap.fixed": "Fixed / max Yes-No / max market",
      "cap.ignore": "Ignore below",
      "cap.spend": "Total spend",
      "cap.sl": "Balance SL",
      "cap.all": "Turn On All Copy",
      "cap.paused": "Paused",
      "cap.never": "Never"
    }
  };

  const charts = {};
  const state = { snap: null, user: null, role: null, hunt: null, solutions: null, lang: "pl", lane: null, gateKey: null };
  const LANE_ORDER = ["tennis", "finance", "politics", "crypto", "culture", "cluster", "nba", "tech", "sports"];
  const VIEWS = ["do", "sim", "poly", "money", "how"];
  const SPOT_FALLBACK = [
    { sym: "BTCUSDT", lab: "BTC", gecko: "bitcoin" },
    { sym: "ETHUSDT", lab: "ETH", gecko: "ethereum" },
    { sym: "SOLUSDT", lab: "SOL", gecko: "solana" },
    { sym: "XRPUSDT", lab: "XRP", gecko: "ripple" },
    { sym: "BNBUSDT", lab: "BNB", gecko: "binancecoin" },
    { sym: "DOGEUSDT", lab: "DOGE", gecko: "dogecoin" },
    { sym: "ADAUSDT", lab: "ADA", gecko: "cardano" },
    { sym: "AVAXUSDT", lab: "AVAX", gecko: "avalanche-2" },
    { sym: "LINKUSDT", lab: "LINK", gecko: "chainlink" },
    { sym: "DOTUSDT", lab: "DOT", gecko: "polkadot" },
    { sym: "LTCUSDT", lab: "LTC", gecko: "litecoin" },
    { sym: "TONUSDT", lab: "TON", gecko: "the-open-network" },
    { sym: "SUIUSDT", lab: "SUI", gecko: "sui" },
    { sym: "UNIUSDT", lab: "UNI", gecko: "uniswap" }
  ];
  const SPOT_GECKO = {};
  SPOT_FALLBACK.forEach(function (p) { if (p.gecko) SPOT_GECKO[p.sym] = p.gecko; });
  const SPOT_RANGES = [
    { id: "h1", interval: "1m", limit: 60, bucket: 60 * 1000 },
    { id: "h3", interval: "1m", limit: 180, bucket: 60 * 1000 },
    { id: "w1", interval: "1h", limit: 168, bucket: 60 * 60 * 1000 },
    { id: "m1", interval: "4h", limit: 186, bucket: 4 * 60 * 60 * 1000 },
    { id: "y1", interval: "1d", limit: 365, bucket: 24 * 60 * 60 * 1000 }
  ];
  const spot = {
    started: false,
    mode: "",
    vis: false,
    range: "h3",
    watch: SPOT_FALLBACK.slice(0, 3),
    catalog: SPOT_FALLBACK.slice(),
    sym: "BTCUSDT",
    px: {},
    chg: {},
    ts: [],
    vs: [],
    ws: null,
    poll: null,
    retry: 0,
    chart: null
  };

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
  function sessionEmail() { return (sessionStorage.getItem("copy-lab-email") || "").toLowerCase(); }
  function sessionRole() { return sessionStorage.getItem("copy-lab-role") || ""; }
  function unlocked() {
    if (sessionStorage.getItem("copy-lab-ok") !== "1") return false;
    const email = sessionEmail();
    const role = sessionRole();
    return !!email && roleOf(email) === role;
  }
  function unlockSession(email, role) {
    sessionStorage.setItem("copy-lab-ok", "1");
    sessionStorage.setItem("copy-lab-email", String(email || "").toLowerCase());
    sessionStorage.setItem("copy-lab-role", role);
  }
  function lockSession() {
    sessionStorage.removeItem("copy-lab-ok");
    sessionStorage.removeItem("copy-lab-email");
    sessionStorage.removeItem("copy-lab-role");
    state.user = null;
    state.role = null;
    document.body.classList.remove("role-viewer");
  }
  function logout() {
    lockSession();
    if ($("page-email")) $("page-email").value = "";
    if ($("page-code")) $("page-code").value = "";
    try {
      if (firebaseReady() && window.firebase && firebase.auth) firebase.auth().signOut();
    } catch (e) { /* optional */ }
    showGate("", "gate.switched");
    applyLang();
    if ($("page-email")) $("page-email").focus();
  }
  function applySessionUser(email, role) {
    state.user = { email: String(email || "").toLowerCase() };
    state.role = role;
    if (role === "viewer") state.lang = "en";
  }
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
    if (state.gateKey && $("gate-msg")) $("gate-msg").textContent = t(state.gateKey);
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
    try { window.scrollTo(0, 0); } catch (e) { /* ignore */ }
    if (view === "sim" || view === "do") {
      Object.keys(charts).forEach(function (id) {
        if (charts[id] && typeof charts[id].resize === "function") charts[id].resize();
      });
      if (spot.chart && typeof spot.chart.resize === "function") spot.chart.resize();
    }
  }

  function setLang(lang) {
    state.lang = lang === "en" ? "en" : "pl";
    applyLang();
    if (state.snap) renderAll();
  }

  function showApp() {
    state.gateKey = null;
    $("gate").classList.add("hidden");
    $("gate").hidden = true;
    $("app").classList.remove("hidden");
    $("app").hidden = false;
    const email = (state.user && state.user.email) || "";
    $("who").textContent = email + (state.role === "viewer" ? " · " + t("who.ro") : "");
    document.body.classList.toggle("role-viewer", state.role === "viewer");
    applyLang();
    showView(viewFromHash());
    startSpot();
  }

  function showGate(msg, key) {
    stopSpot();
    $("app").classList.add("hidden");
    $("app").hidden = true;
    $("gate").classList.remove("hidden");
    $("gate").hidden = false;
    state.gateKey = key || null;
    $("gate-msg").textContent = key ? t(key) : (msg || "");
  }

  async function tryPageCode() {
    try {
      const email = (($("page-email") && $("page-email").value) || "").trim().toLowerCase();
      const typed = ($("page-code").value || "").trim();
      const expect = (window.OPS_CONFIG && window.OPS_CONFIG.pageCodeSha256) || "";
      const role = roleOf(email);
      if (!email) {
        showGate("", "gate.needEmail");
        return;
      }
      if (!role) {
        showGate("", "gate.unknown");
        return;
      }
      if (!typed || !expect) {
        showGate("", "gate.needPass");
        return;
      }
      const hex = await sha256hex(typed);
      if (hex !== expect) {
        showGate("", "gate.wrong");
        return;
      }
      unlockSession(email, role);
      applySessionUser(email, role);
      showApp();
      await renderAll();
    } catch (e) {
      showGate(String((e && e.message) || e));
    }
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

  function pickBriefLane(lanes) {
    const waits = lanes.filter(function (l) { return l.tone === "wait" && l.best; });
    const hunt = waits.filter(function (l) { return l.best.source === "hunt"; });
    const pool = hunt.length ? hunt : waits;
    pool.sort(function (a, b) {
      const d90 = (Number(b.best.w90) || 0) - (Number(a.best.w90) || 0);
      if (d90) return d90;
      return (Number(b.best.w60) || 0) - (Number(a.best.w60) || 0);
    });
    return pool[0] || null;
  }

  function renderBrief(s, rows) {
    const verb = $("do-brief-verb");
    const body = $("do-brief-body");
    const path = $("do-brief-path");
    const next = $("do-brief-next");
    const src = $("do-brief-src");
    if (!verb || !body) return;
    verb.textContent = t("do.briefVerb");
    const sol = state.solutions || {};
    const lang = state.lang === "en" ? "en" : "pl";
    if (sol.now_pl || sol.now_en) {
      body.textContent = sol[lang === "en" ? "now_en" : "now_pl"] || sol.now_pl || "";
      if (path) path.textContent = sol[lang === "en" ? "path_en" : "path_pl"] || sol.path_pl || "";
      if (next) next.textContent = sol[lang === "en" ? "hunt_next_en" : "hunt_next_pl"] || sol.hunt_next_pl || "";
      if (src) src.textContent = sol.source === "claude" ? t("do.solClaude") : t("do.solLab");
      return;
    }
    if (path) path.textContent = "—";
    if (next) next.textContent = "—";
    if (src) src.textContent = t("do.solLab");
    const top = pickBriefLane(buildLanes(s, rows));
    if (!top || !top.best) {
      body.textContent = t("do.briefNone");
      return;
    }
    body.textContent = fmt("do.briefWait", {
      lane: t("lane." + top.id),
      name: top.best.name || "—",
      w60: money(top.best.w60),
      w90: money(top.best.w90)
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

  function fmtSpotPx(n) {
    if (n == null || Number.isNaN(Number(n))) return "—";
    const v = Number(n);
    const d = v >= 100 ? 2 : v >= 1 ? 3 : v >= 0.01 ? 4 : 6;
    return "$" + v.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
  }

  function labFromSym(sym) {
    return String(sym || "").replace(/USDT$/, "") || "BTC";
  }

  function spotLab(sym) {
    const row = spot.watch.filter(function (p) { return p.sym === sym; })[0]
      || spot.catalog.filter(function (p) { return p.sym === sym; })[0];
    return (row && row.lab) || labFromSym(sym);
  }

  function spotRangeCfg() {
    return SPOT_RANGES.filter(function (r) { return r.id === spot.range; })[0] || SPOT_RANGES[1];
  }

  function saveSpot() {
    try {
      localStorage.setItem("copy-lab-spot", JSON.stringify({
        watch: spot.watch,
        sym: spot.sym,
        range: spot.range
      }));
    } catch (e) { /* ignore */ }
  }

  function loadSpotPrefs() {
    try {
      const raw = JSON.parse(localStorage.getItem("copy-lab-spot") || "null");
      if (!raw) return;
      if (Array.isArray(raw.watch) && raw.watch.length) {
        spot.watch = raw.watch.slice(0, 6).map(function (p) {
          const s = String(p.sym || "").toUpperCase();
          return { sym: s, lab: p.lab || labFromSym(s) };
        }).filter(function (p) { return /USDT$/.test(p.sym); });
      }
      if (raw.sym && /USDT$/.test(String(raw.sym))) spot.sym = String(raw.sym).toUpperCase();
      if (SPOT_RANGES.some(function (r) { return r.id === raw.range; })) spot.range = raw.range;
      if (spot.watch.length && !spot.watch.some(function (p) { return p.sym === spot.sym; })) {
        spot.sym = spot.watch[0].sym;
      }
    } catch (e) { /* ignore */ }
  }

  function paintSpotRange() {
    const bar = $("spot-range");
    if (!bar) return;
    if (!bar.querySelector("[data-range]")) {
      bar.innerHTML = SPOT_RANGES.map(function (r) {
        return "<button type='button' data-range='" + r.id + "'></button>";
      }).join("");
      bar.querySelectorAll("[data-range]").forEach(function (btn) {
        btn.onclick = function () { pickSpotRange(btn.getAttribute("data-range")); };
      });
    }
    bar.querySelectorAll("[data-range]").forEach(function (btn) {
      const id = btn.getAttribute("data-range");
      btn.textContent = t("spot.range." + id);
      btn.classList.toggle("on", id === spot.range);
    });
  }

  function paintSpotPick() {
    const sel = $("spot-pick");
    if (!sel) return;
    const want = (spot.catalog && spot.catalog.length) ? spot.catalog : SPOT_FALLBACK;
    if (sel.getAttribute("data-n") !== String(want.length)) {
      sel.innerHTML = "<option value=''>" + esc(t("spot.pickPh")) + "</option>" +
        want.map(function (c) {
          return "<option value='" + esc(c.sym) + "'>" + esc(c.lab) + "</option>";
        }).join("");
      sel.setAttribute("data-n", String(want.length));
      sel.onchange = function () {
        const v = sel.value;
        if (v) addSpot(v);
        sel.value = "";
      };
    } else if (sel.options.length) {
      sel.options[0].textContent = t("spot.pickPh");
    }
  }

  function paintSpot() {
    const box = $("spot-tick");
    if (!box) return;
    paintSpotRange();
    paintSpotPick();
    const key = spot.watch.map(function (c) { return c.sym; }).join(",");
    if (box.getAttribute("data-watch") !== key) {
      box.setAttribute("data-watch", key);
      box.innerHTML = spot.watch.map(function (c) {
        return "<button type='button' class='spot-card' data-sym='" + c.sym +
          "'><p class='kicker'>" + esc(c.lab) + "</p>" +
          "<p class='spot-px'>—</p>" +
          "<p class='spot-chg'>—</p></button>";
      }).join("");
      box.querySelectorAll("[data-sym]").forEach(function (btn) {
        btn.onclick = function () { pickSpot(btn.getAttribute("data-sym")); };
      });
    }
    spot.watch.forEach(function (c) {
      const btn = box.querySelector("[data-sym='" + c.sym + "']");
      if (!btn) return;
      btn.classList.toggle("on", spot.sym === c.sym);
      const pxEl = btn.querySelector(".spot-px");
      const chgEl = btn.querySelector(".spot-chg");
      const px = spot.px[c.sym];
      const chg = spot.chg[c.sym];
      const raw = chg == null || Number.isNaN(Number(chg)) ? null : Number(chg);
      const pct = raw == null ? "—" : (raw > 0 ? "+" : "") + raw.toFixed(2) + "%";
      if (pxEl) pxEl.textContent = fmtSpotPx(px);
      if (chgEl) {
        chgEl.textContent = fmt("spot.chg", { pct: pct });
        chgEl.classList.toggle("up", raw != null && raw > 0);
        chgEl.classList.toggle("down", raw != null && raw < 0);
      }
    });
    const st = $("spot-feed");
    if (st) {
      st.textContent = spot.mode === "ws" ? t("spot.live")
        : spot.mode === "rest" ? t("spot.poll")
        : t("spot.off");
    }
    const title = $("spot-chart-title");
    if (title) {
      title.textContent = fmt("spot.chart", {
        name: spotLab(spot.sym),
        range: t("spot.range." + spot.range)
      });
    }
  }

  function spotTimeLabel(ms) {
    const iso = new Date(ms).toISOString();
    if (spot.range === "y1") return iso.slice(0, 10);
    if (spot.range === "m1" || spot.range === "w1") return iso.slice(5, 10) + " " + iso.slice(11, 13) + "h";
    return iso.slice(11, 16);
  }

  function drawSpotChart() {
    if (!$("chart-spot") || !window.Chart) return;
    const labels = spot.ts.map(spotTimeLabel);
    if (spot.chart) {
      spot.chart.data.labels = labels;
      spot.chart.data.datasets[0].data = spot.vs.slice();
      spot.chart.update("none");
      return;
    }
    Chart.defaults.color = "#b4b4b0";
    Chart.defaults.borderColor = "#2a2a2e";
    Chart.defaults.font.family = "Instrument Sans, Segoe UI, sans-serif";
    spot.chart = new Chart($("chart-spot").getContext("2d"), {
      type: "line",
      data: {
        labels: labels,
        datasets: [{
          data: spot.vs.slice(),
          borderColor: "#d8ff4a",
          backgroundColor: "rgba(216,255,74,0.08)",
          fill: true,
          pointRadius: 0,
          borderWidth: 2,
          tension: 0.2
        }]
      },
      options: {
        animation: false,
        plugins: { legend: { display: false } },
        scales: {
          x: {
            ticks: { maxTicksLimit: 6, maxRotation: 0 },
            grid: { display: false }
          },
          y: {
            grid: { color: "rgba(255,255,255,0.06)" }
          }
        }
      }
    });
  }

  function pushSpotPoint(ms, px) {
    if (!px || Number.isNaN(px)) return;
    const cfg = spotRangeCfg();
    const bucket = Math.floor(ms / cfg.bucket) * cfg.bucket;
    const last = spot.ts[spot.ts.length - 1];
    if (last === bucket) {
      spot.vs[spot.vs.length - 1] = px;
    } else if (!last || bucket > last) {
      spot.ts.push(bucket);
      spot.vs.push(px);
      while (spot.ts.length > cfg.limit) {
        spot.ts.shift();
        spot.vs.shift();
      }
    }
    drawSpotChart();
  }

  async function fetchFirst(urls) {
    let last = null;
    for (let i = 0; i < urls.length; i++) {
      try {
        const r = await fetch(urls[i], { cache: "no-store" });
        if (r.ok) return await r.json();
        last = new Error("http " + r.status);
      } catch (e) {
        last = e;
      }
    }
    throw last || new Error("fetch failed");
  }

  async function loadKlines(sym) {
    const cfg = spotRangeCfg();
    const q = "/api/v3/klines?symbol=" + encodeURIComponent(sym) +
      "&interval=" + cfg.interval + "&limit=" + cfg.limit;
    try {
      const rows = await fetchFirst([
        "https://api.binance.com" + q,
        "https://data-api.binance.vision" + q
      ]);
      spot.ts = rows.map(function (r) { return Number(r[0]); });
      spot.vs = rows.map(function (r) { return Number(r[4]); });
      drawSpotChart();
    } catch (e) {
      spot.ts = [];
      spot.vs = [];
    }
  }

  async function loadSpotCatalog() {
    try {
      const rows = await fetchFirst([
        "https://api.binance.com/api/v3/ticker/24hr",
        "https://data-api.binance.vision/api/v3/ticker/24hr"
      ]);
      const usdt = (rows || []).filter(function (r) {
        const s = String(r.symbol || "");
        if (!/USDT$/.test(s) || s.indexOf("_") !== -1) return false;
        if (/(UP|DOWN|BULL|BEAR)USDT$/.test(s)) return false;
        return Number(r.quoteVolume) > 0;
      }).sort(function (a, b) {
        return Number(b.quoteVolume) - Number(a.quoteVolume);
      }).slice(0, 80);
      const seen = {};
      spot.catalog = usdt.map(function (r) {
        seen[r.symbol] = true;
        return { sym: r.symbol, lab: labFromSym(r.symbol) };
      });
      spot.watch.forEach(function (p) {
        if (!seen[p.sym]) spot.catalog.unshift({ sym: p.sym, lab: p.lab || labFromSym(p.sym) });
      });
    } catch (e) {
      spot.catalog = SPOT_FALLBACK.slice();
    }
    const sel = $("spot-pick");
    if (sel) sel.removeAttribute("data-n");
    paintSpotPick();
  }

  function applySpotTicker(sym, px, openOrChg, isPct) {
    if (!px) return;
    spot.px[sym] = px;
    if (isPct) spot.chg[sym] = openOrChg;
    else if (openOrChg) spot.chg[sym] = ((px - openOrChg) / openOrChg) * 100;
    paintSpot();
    if (sym === spot.sym) pushSpotPoint(Date.now(), px);
  }

  async function restBinance() {
    const symbols = encodeURIComponent(JSON.stringify(spot.watch.map(function (p) { return p.sym; })));
    const q = "/api/v3/ticker/24hr?symbols=" + symbols;
    try {
      const rows = await fetchFirst([
        "https://api.binance.com" + q,
        "https://data-api.binance.vision" + q
      ]);
      (rows || []).forEach(function (r) {
        applySpotTicker(r.symbol, Number(r.lastPrice), Number(r.priceChangePercent), true);
      });
      if (spot.mode !== "ws") spot.mode = "rest";
      paintSpot();
      return true;
    } catch (e) {
      return restGecko();
    }
  }

  async function restGecko() {
    const pairs = spot.watch.filter(function (p) { return SPOT_GECKO[p.sym]; });
    if (!pairs.length) return false;
    const ids = pairs.map(function (p) { return SPOT_GECKO[p.sym]; }).join(",");
    try {
      const d = await fetchFirst([
        "https://api.coingecko.com/api/v3/simple/price?ids=" + ids +
          "&vs_currencies=usd&include_24hr_change=true"
      ]);
      pairs.forEach(function (p) {
        const row = d[SPOT_GECKO[p.sym]] || {};
        if (row.usd) applySpotTicker(p.sym, Number(row.usd), Number(row.usd_24h_change), true);
      });
      if (spot.mode !== "ws") spot.mode = "rest";
      paintSpot();
      return true;
    } catch (e) {
      if (spot.mode !== "ws") {
        spot.mode = "";
        paintSpot();
      }
      return false;
    }
  }

  function startSpotPoll() {
    if (spot.poll) return;
    spot.poll = setInterval(function () {
      if (spot.mode === "ws") return;
      restBinance();
    }, 3000);
  }

  function onSpotMsg(raw) {
    let msg = raw;
    try { msg = JSON.parse(raw); } catch (e) { return; }
    const d = msg.data || msg;
    if (!d || !d.s) return;
    spot.mode = "ws";
    spot.retry = 0;
    if (spot.poll) {
      clearInterval(spot.poll);
      spot.poll = null;
    }
    applySpotTicker(d.s, Number(d.c), Number(d.o), false);
  }

  function openSpotWs() {
    if (!spot.started) return;
    if (spot.ws && (spot.ws.readyState === 0 || spot.ws.readyState === 1)) return;
    const streams = spot.watch.map(function (p) {
      return p.sym.toLowerCase() + "@miniTicker";
    }).join("/");
    const hosts = [
      "wss://stream.binance.com:9443/stream?streams=" + streams,
      "wss://data-stream.binance.vision/stream?streams=" + streams
    ];
    const url = hosts[spot.retry % hosts.length];
    let sock;
    try { sock = new WebSocket(url); } catch (e) {
      startSpotPoll();
      restBinance();
      return;
    }
    spot.ws = sock;
    const hang = setTimeout(function () {
      if (sock.readyState !== 1) {
        startSpotPoll();
        try { sock.close(); } catch (e) { /* ignore */ }
      }
    }, 4000);
    sock.onmessage = function (ev) { onSpotMsg(ev.data); };
    sock.onopen = function () {
      clearTimeout(hang);
      spot.retry = 0;
    };
    sock.onerror = function () { /* onclose retries */ };
    sock.onclose = function () {
      if (spot.ws === sock) spot.ws = null;
      if (!spot.started) return;
      if (spot.mode === "ws") spot.mode = "rest";
      paintSpot();
      startSpotPoll();
      const wait = Math.min(15000, 1200 * Math.pow(1.6, Math.min(spot.retry, 6)));
      spot.retry += 1;
      setTimeout(openSpotWs, wait);
    };
  }

  function restartSpotWs() {
    if (spot.ws) {
      try { spot.ws.onclose = null; spot.ws.close(); } catch (e) { /* ignore */ }
      spot.ws = null;
    }
    spot.retry = 0;
    if (spot.started) openSpotWs();
  }

  function pickSpot(sym) {
    if (!sym) return;
    if (spot.sym !== sym) {
      spot.sym = sym;
      saveSpot();
      paintSpot();
      loadKlines(sym);
    } else {
      paintSpot();
    }
  }

  function pickSpotRange(id) {
    if (!id || spot.range === id) return;
    spot.range = id;
    saveSpot();
    paintSpot();
    loadKlines(spot.sym);
  }

  function addSpot(sym) {
    const s = String(sym || "").toUpperCase();
    if (!/USDT$/.test(s)) return;
    const lab = labFromSym(s);
    if (!spot.watch.some(function (p) { return p.sym === s; })) {
      spot.watch.unshift({ sym: s, lab: lab });
      while (spot.watch.length > 6) {
        let i = spot.watch.length - 1;
        while (i > 0 && spot.watch[i].sym === s) i--;
        spot.watch.splice(i, 1);
      }
      restartSpotWs();
      restBinance();
    }
    pickSpot(s);
    saveSpot();
  }

  function stopSpot() {
    spot.started = false;
    if (spot.ws) {
      try { spot.ws.onclose = null; spot.ws.close(); } catch (e) { /* ignore */ }
      spot.ws = null;
    }
    if (spot.poll) {
      clearInterval(spot.poll);
      spot.poll = null;
    }
    if (spot.mode === "ws") spot.mode = "";
  }

  function startSpot() {
    if (spot.started) return;
    spot.started = true;
    loadSpotPrefs();
    paintSpot();
    loadSpotCatalog();
    loadKlines(spot.sym);
    restBinance().then(function () { openSpotWs(); });
    if (!spot.vis) {
      spot.vis = true;
      document.addEventListener("visibilitychange", function () {
        if (document.visibilityState !== "visible" || !spot.started) return;
        if (!spot.ws || spot.ws.readyState !== 1) openSpotWs();
      });
    }
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
    const watch = s.watch_not_enable || [];
    const listed = watch.length ? watch : [{ name: p.name, address: p.address }];
    const addrs = listed.map(function (w) {
      return "<p class='addr'>" + esc(w.name || "") + " · " + esc(w.address || "") +
        " · " + esc(t("cap.paused")) + "</p>";
    }).join("");
    const rows = [
      [t("cap.active"), t("cap.activeV")],
      [t("cap.fixed"), "$" + (caps.fixed_usd || 5)],
      [t("cap.ignore"), "$" + (caps.ignore_below_usd || 20)],
      [t("cap.spend"), "$" + (caps.total_spend_usd || 15)],
      [t("cap.sl"), "$" + (caps.balance_sl_usd || 31)],
      [t("cap.all"), t("cap.never")]
    ];
    return addrs + "<table class='caps'><tbody>" + rows.map(function (r) {
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

  function journalFromHunt(h) {
    if (h && h.journal && (h.journal.items || h.journal.checked)) return h.journal;
    const log = (h && h.log) || [];
    let queued = 0;
    const items = [];
    log.forEach(function (line) {
      const s = String(line);
      if (s.indexOf("simming ") === 0) {
        queued = parseInt(s.split(/\s+/)[1], 10) || 0;
        return;
      }
      if (s.indexOf(" 60=") === -1 || s.indexOf(" 90=") === -1) return;
      const parts = s.trim().split(/\s+/);
      if (parts.length < 6) return;
      function nv(p) { return parseFloat(String(p).split("=")[1]); }
      const days = nv(parts[2]);
      const w60 = nv(parts[3]);
      const w90 = nv(parts[4]);
      const conc = nv(parts[5]);
      if ([days, w60, w90, conc].some(function (n) { return Number.isNaN(n); })) return;
      let why = "partial";
      let tone = "wait";
      if (s.indexOf("Avoid") !== -1) { why = "avoid"; tone = "no"; }
      else if (conc > 0.45) { why = "one_event"; tone = "no"; }
      else if (w60 <= 0 || w90 <= 0) { why = "no_both"; tone = "no"; }
      else if (days < 90) { why = "short"; tone = "wait"; }
      items.push({ name: parts[0], cat: parts[1], tone: tone, why: why, w60: w60, w90: w90 });
    });
    const checked = (h && h.checked) || 0;
    return {
      checked: checked,
      queued: queued,
      drops: { pre_sim: Math.max(checked - queued, 0) },
      wait_n: items.filter(function (r) { return r.tone === "wait"; }).length,
      items: items.slice(-14),
      flip: null
    };
  }

  function renderJournal() {
    const head = $("journal-head");
    const kpis = $("journal-kpis");
    const tape = $("journal-tape");
    if (!head || !kpis || !tape) return;
    const j = journalFromHunt(state.hunt || {});
    const n = j.checked || 0;
    const q = j.queued || 0;
    const flip = j.flip;
    head.textContent = flip
      ? fmt("journal.headFlip", { n: n, name: flip.cat || "" })
      : fmt("journal.head", { n: n, q: q });
    const pre = (j.drops && j.drops.pre_sim != null) ? j.drops.pre_sim : Math.max(n - q, 0);
    const waitN = j.wait_n != null ? j.wait_n : ((j.items || []).filter(function (r) { return r.tone === "wait"; }).length);
    kpis.innerHTML = [
      [t("journal.checked"), n],
      [t("journal.queued"), q],
      [t("journal.pre"), pre],
      [t("journal.wait"), waitN]
    ].map(function (row) {
      return "<div><p class='kpi'>" + esc(row[1]) + "</p><p class='lbl'>" + esc(row[0]) + "</p></div>";
    }).join("");
    const rows = j.items || [];
    if (!rows.length) {
      tape.innerHTML = "<li>" + esc(t("journal.none")) + "</li>";
      return;
    }
    tape.innerHTML = rows.map(function (r) {
      const cls = r.tone === "wait" ? "wait" : "no";
      return "<li class='" + cls + "'><b>" + esc(r.name) + "</b> · " + esc(r.cat || "") +
        " · " + esc(t("journal.why." + r.why)) + " · 60/90 " + money(r.w60, 1) + " / " + money(r.w90, 1) + "</li>";
    }).join("");
  }

  async function loadHunt() {
    try {
      const h = await (await fetch("./data/hunt.json?t=" + Date.now())).json();
      state.hunt = h;
      let pulse = "";
      let lastKey = "hunt.last";
      try {
        const p = await (await fetch("./data/pulse.json?t=" + Date.now())).json();
        if (p.hunt === "running") {
          const since = p.updated_at ? String(p.updated_at).replace("T", " ").slice(11, 16) + " UTC" : "";
          pulse = since ? fmt("hunt.runningSince", { t: since }) : t("hunt.running");
          lastKey = "hunt.lastDone";
        }
      } catch (e) { /* optional */ }
      const when = h.updated_at ? String(h.updated_at).replace("T", " ").slice(0, 16) + " UTC" : "?";
      $("hunt-pulse").textContent = pulse + t(lastKey) + when;
      $("hunt-plain").textContent = fmt("hunt.line", { n: h.checked || 0 });
      try {
        state.solutions = await (await fetch("./data/solutions.json?t=" + Date.now())).json();
      } catch (e2) { state.solutions = null; }
    } catch (e) {
      $("hunt-pulse").textContent = t("hunt.missing");
    }
  }

  function paintHuntViews(s) {
    renderJournal();
    const rows = fieldRows(s, state.hunt);
    renderLanes(s, rows);
    renderBrief(s, rows);
    const shown = state.lane
      ? rows.filter(function (r) { return rowLane(r) === state.lane; })
      : rows;
    if ($("field-body")) $("field-body").innerHTML = shown.map(rowHtml).join("");
    renderPredict(s, state.hunt);
    renderCharts(s, shown);
    renderChartReads(s, shown);
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
    if (state.hunt) paintHuntViews(s);
    await loadHunt();
    paintHuntViews(s);
    paintSpot();
    if (viewFromHash() === "sim" || viewFromHash() === "do") {
      Object.keys(charts).forEach(function (id) {
        if (charts[id] && typeof charts[id].resize === "function") charts[id].resize();
      });
      if (spot.chart && typeof spot.chart.resize === "function") spot.chart.resize();
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
        showGate("", "gate.unknown");
        return;
      }
      unlockSession(user.email, role);
      applySessionUser(user.email, role);
      showApp();
      renderAll();
    });
    return true;
  }

  function bind() {
    if ($("btn-code")) $("btn-code").onclick = tryPageCode;
    if ($("page-email")) {
      $("page-email").addEventListener("keydown", function (ev) {
        if (ev.key === "Enter") tryPageCode();
      });
      $("page-email").addEventListener("input", function () {
        const role = roleOf(($("page-email").value || "").trim());
        if (role === "viewer") setLang("en");
      });
    }
    if ($("page-code")) {
      $("page-code").addEventListener("keydown", function (ev) {
        if (ev.key === "Enter") tryPageCode();
      });
    }
    if ($("btn-out")) $("btn-out").onclick = logout;
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
      const q = new URLSearchParams(location.search).get("lang");
      if (q === "en" || q === "pl") state.lang = q;
      else {
        const saved = localStorage.getItem("copy-lab-lang");
        if (saved === "en" || saved === "pl") state.lang = saved;
      }
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
    await bootFirebase();
    const host = location.hostname;
    if ((host === "127.0.0.1" || host === "localhost") &&
        new URLSearchParams(location.search).get("lab") === "1") {
      unlockSession("damianbiniarz@gmail.com", "owner");
      applySessionUser("damianbiniarz@gmail.com", "owner");
    }
    if (sessionStorage.getItem("copy-lab-ok") === "1" && (!sessionEmail() || !sessionRole())) {
      lockSession();
    }
    if (unlocked()) {
      applySessionUser(sessionEmail(), sessionRole());
      showApp();
      renderAll().catch(function (err) { showGate(String(err)); });
    } else {
      showGate("");
    }
    setInterval(function () {
      if (unlocked()) renderAll().catch(function () { /* keep last paint */ });
    }, 15000);
  }

  main().catch(function (err) {
    showGate(String(err));
  });
})();
