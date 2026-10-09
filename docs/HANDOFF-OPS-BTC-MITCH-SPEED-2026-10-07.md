# Mitch: czas, arkusz, Miha 5m, rezerwa zysku — 7 października 2026

PAPER. `clob_live` zostaje false. Limitów okna Mitcha ($20 / $5 mihaXd, 10 centów, tylko BTC 15 min) nie ruszałem. LIVE nie włączałem. Strat nie resetowałem.

## Werdykt Mitche'a o Miha 5m

Zgadza się z kodem i zostaje jawny. Kopiarka Mitcha nigdy nie brała 5m (filtr `btc-updown-15m-`). Teraz 5m dostaje osobny powód `MITCH_SKIP_5M` i notatkę na zakładce. 15m mihaXd zostaje: limit $5, ten sam wzór wielkości. Nie dodałem drugiej strategii.

Replay Mitche'a (jego liczby, nie nasze): 30 dni 5m przy 2c ponad jego ceną −502 / −1192; sam stracił −3168; szczęśliwy Down +1494 nie zmieściłby się w capie $5–20. Nawet kopia po jego cenie bez opłat przegrywa. Nie ma krawędzi do gonienia.

## Czas poniżej 1 s

To nadal nie jest potwierdzone nowym wypełnieniem po restarcie. Zmieniłem ścieżkę, która ten czas psuła:

- Paragon `OrderFilled` dla pięciu portfeli, jeśli jest, kończy obsługę od razu. Nie czeka 2 s na publiczną listę.
- Ten sam paragon nadpisuje wcześniejszy cytat `chain_fast`. Wcześniej `INSERT OR IGNORE` zostawiał cytat arkusza.
- `chain_fast` nie czeka już 3 s i nie dostaje od razu `AWAITING_SOURCE_PRICE`. Grzeje arkusz i czeka na prawdziwą cenę. Po 90 s bez ceny zapisuje oczekiwanie.
- Pętla Mitcha budzi się co 50 ms albo na nowym wierszu aktywności, nie co 200 ms.

Kolejka Mitcha po restarcie: 0, świeże 0. Nie było nowego sygnału 15m do skopiowania, więc nie ma nowej próbki poniżej 1 s. Stare 28 wypełnień z nocy (mediana kolejki ~25 s) nie są tym kodem.

## Bid i ask

Zakładka Mitch ma panel „Arkusz — bid i ask”. Pokazuje ostatni odczyt CLOB przy decyzji: czy jest ask, czy jest bid, głębokość i czy kopia w ogóle wejdzie. Brak bidu albo asku jest powodem (`NO_ASK` / brak bid przy sprzedaży), nie zgadywaniem. Po tym restarcie nie było jeszcze decyzji, więc panel mówi, że odczytu nie ma. To nie jest ukryty bid.

## Rezerwa 40% zysku

Od nowych zamknięć na plus: 40% `pnl` zostaje na koncie jako `reserved` i nie idzie w kolejny BUY. SELL i rozliczenie działają. Stare plusy (+88,26 od startu Mitcha) nie są cofane. Po restarcie: zarezerwowane 0 na wszystkich pięciu, tradable = gotówka (096b159 500, 365cf589 497,30, 207e77c2 569,49, checkr3 500, mihaXd 525,30).

## Szybsza reakcja na stratę (kwalifikator)

Do pierwszego zamkniętego albo oficjalnego wyniku okresu: najwyżej **dwie** otwarte pozycje. Po plusie zostaje stary cap pięciu i $25. Minus pauzuje BUY tak jak wcześniej (w tym `RESOLVED` z poprzedniego audytu). Mitch nie dostał pauzy strat — 15m zostaje jego regułą.

## Połączenie

Tunel: plik `tunnel-watch-status.json` o 22:56, HTTP 302, krawędź jest, origin za Access niepotwierdzony. Nadzór nie rusza kopiarki. Lokalny `/healthz` 200, worker `RECORDING`, referencja `FRESH`, arkusz workera `STALE` (osobny problem pulpitu, kopia nie używa tego cache). `chain_status` w stanie bazy jeszcze nie było minutę po starcie, bo pętla nadzoru czeka na długie `iteration`. Dopisane publikowanie z heartbeat — wejdzie przy następnym starcie procesu, bez drugiego restartu teraz.

## Rewizja i testy

Git `e001caf`. Działający release `b009e2b8b429-1790926011187411000`, pid 8018, wersja 0.6.7. Testy: `test_mitch_copy` 22, `test_wallet_copy` 49, `test_chain_monitor` 24, `test_wallet_roster` 25, `test_copy_totals` 10.

Audyt co 2 h: połączenie, `/healthz`, worker, kolejka Mitcha, pauza, błędy kodu. Nie restartuję kopiarki tylko dlatego, że tunel albo arkusz pulpitu jest STALE.

## Audyt 8 października 2026, 00:58 Europe/Stockholm

Papier pid 8018, last exit 0, `/healthz` 200. Worker `RECORDING` 0.6.7, referencja `FRESH`, arkusz pulpitu teraz `FRESH`. Łańcuch połączony (`rpc-polygon.blockmachine.io`, last_block 95137825, 635 porzuceń, 175 timeoutów). Tunel HTTP 302, krawędź jest, origin za Access niepotwierdzony.

Kolejka Mitcha 0. Od restartu 12 nowych `MITCH_BUY`/`ADD` (00:04–00:57). Kolejka 3,6–46,6 s, **0 poniżej 1 s**. Cel nie jest spełniony. `MITCH_SKIP_5M` = 3, wszystkie na 207e77c2, okno 5m — 15m nie ruszone. Dziś Mitch zamknięte −37,84 USD, od startu +54,24, 1 otwarta.

Kwalifikator: 31 w pauzie, 9 kopiuje, 0 `COPIED_BUY` po `since` pauzy. Kolejka kopii 234. `wallet_copy_error` puste. `mitch_copy_error` to stary `database is locked` sprzed 29 h, nie z tej nocy.

Nic nie restartowałem. LIVE wyłączone. Następny audyt około 02:58.

## Audyt 8 października 2026, 02:58 Europe/Stockholm

Papier stał na pid 8018 od 22:56. `/healthz` 200, worker `RECORDING`, referencja `FRESH`, arkusz pulpitu znowu `STALE`. Tunel HTTP 302, krawędź jest.

Łańcuch w stanie bazy był martwy: `last_block` 95137825 i te same liczniki co o 00:58. Kopie Mitcha szły z listy publicznej (`source_second`), kolejka 8–79 s, były `BOOK_WAIT_TOO_LONG` i `LATE_BUY_NOT_COPIED`. Kolejka Mitcha 44, z tego 4 świeże (najstarsze 56 s). Od 00:58 doszło 25 wypełnień, **0 poniżej 1 s**. `MITCH_SKIP_5M` 80. Dziś Mitch −150,90 USD, od startu −58,82, 7 otwartych. Kwalifikator: 34 w pauzie, 6 kopiuje, 0 zakupów po pauzie. `mitch_copy_error` to nadal stary lock sprzed 31 h.

Restart raz, nie z powodu STALE, tylko żeby ożywić łańcuch i wczytać publikację `chain_status` z heartbeat. Nowy pid 13506, `/healthz` 200, worker `RECORDING`, arkusz `FRESH`, łańcuch `last_block` 95143988 (ruszony). LIVE wyłączone. Następny audyt około 04:58.

## Audyt 8 października 2026, 04:58 Europe/Stockholm

Pid 13506 bez zmian, last exit 0, `/healthz` 200. Worker `RECORDING`, referencja `FRESH`, arkusz pulpitu znowu `STALE` — nie restartuję. Tunel HTTP 302, krawędź jest.

Łańcuch żywy: `last_block` 95144840 (było 95143988), 64058 zdarzeń od restartu, 231 zmostkowanych. Kolejka Mitcha 0. Od 03:00 czternaście `MITCH_BUY`/`ADD`, z tego 3 `source_subsecond` (razem 14,7–17,1 s) i 11 z listy publicznej. **0 poniżej 1 s.** Żadnego `order_filled`. `MITCH_SKIP_5M` 103. Dziś Mitch −183,67 USD, od startu −91,59, 0 otwartych.

Kwalifikator: 36 w pauzie, 7 kopiuje, 0 zakupów po pauzie. Kolejka kopii 343. `wallet_copy_error` puste. Stary `database is locked` ma 33 h.

Nic nie restartowałem. LIVE wyłączone. Następny audyt około 06:58.

## Audyt 8 października 2026, 07:07 Europe/Stockholm

Pid 26516, last exit 0, `/healthz` 200. Worker `RECORDING` 0.6.7, referencja `FRESH`, arkusz pulpitu `STALE` — nie restartuję. `clob_live` false. Zegar synced. Tunel HTTP 302, krawędź jest, origin za Access niepotwierdzony.

Łańcuch żywy: `last_block` 95153892, `CHAIN_FAST`. Kolejka Mitcha 0. Dziennik 40, `max_buy_age` 1 s. Dziś −202,45, od startu −110,36, 0 otwartych. Pauza BUY na 365cf589, 207e77c2, checkr3, mihaXd. 096b159 bez pauzy. Od wdrożenia stopu 0 `MITCH_BUY`/`ADD` — nie ma nowej próbki poniżej 1 s, bo spóźniony sygnał nie wchodzi.

Kwalifikator: 37 w pauzie, 7 kopiuje, 0 `COPIED_BUY` po `since` pauzy. `wallet_copy_error` puste. `mitch_copy_error` to stary `database is locked` sprzed 35 h.

Nic nie restartowałem z tego audytu. LIVE wyłączone. Następny audyt około 09:07.
