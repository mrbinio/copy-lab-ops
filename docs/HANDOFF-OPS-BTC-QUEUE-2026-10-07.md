# BTC Lab — kolejka i czas arkusza — 7 października 2026

PAPER. `clob_live` zostało false. Port 8769, historia, baza i hasło bez zmian. Reguły pauzy kwalifikatora i zasady Mitcha (pięć portfeli, BTC 15 min, wzór wielkości, 10 centów, limity okna) bez zmian. Starych 21 zakupów nie wpisano wstecz do żywej księgi.

Opus nie pisał tego kodu. Model jest dostępny jako podagent, ta poprawka powstała w tej sesji na zmierzonym opóźnieniu.

## Co zatrzymywało kopie

Dwa różne czasy były wcześniej zlewane w jedno „21 sekund sieci”.

Żądanie arkusza z Maca, poza procesem, do tego samego CLOB: 59–92 ms wcześniej, po restarcie 53 ms i 57 ms. Gamma dla bieżącego okna 15 min: 218 ms, potem 88 ms i 22 ms.

W procesie, pod obciążeniem, po rozdzieleniu puli: oczekiwanie na wolny wątek 0,3–1,0 ms, samo HTTP 64–88 ms, jedno podejście, bez ponowienia. `await asyncio.to_thread` nie jest już raportowane jako czas sieci. Osobno zapisujemy `book_pool_ms`, `book_http_ms`, `book_tries`. Czekanie na zapis SQLite (`db_wait_ms`) jest w ścieżce decyzji; w tym oknie Mitch nie miał nowej decyzji, więc ta próbka jest pusta.

21 zakupów Mitcha z klasy `queue` (w tym samym oknie decyzji jest 51 takich wierszy, ten sam kształt) doszło do bazy w około 0–9 s od sekundowego stempla API. Potem czekały 161–273 s i dostały `LATE_BUY_NOT_COPIED`. Nie było w nich czasu arkusza, bo decyzja zapadała zanim arkusz został pobrany. Kolejka brała najstarsze nieoznaczone wiersze, `LIMIT 10`. Świeży zakup stał za historią.

## Co jest zmienione

- Świeże zdarzenia Mitcha (stempel źródła z ostatnich 90 s) idą przed historią. Historia schodzi partiami, gdy nie blokuje świeżego toru. `backlog` to liczba oczekujących, nie `LIMIT`.
- Kopiowanie kwalifikatora bierze portfele w stanie kopiowania przed pauzą i obserwacją. Pauza i obserwacja schodzą dopiero, gdy tor kopiowania jest pusty.
- Arkusz i warunki rynku aktywnej kopii mają własną pulę, limit 2 s na próbę i jedno ponowienie. Odpowiedź 429 nie jest powtarzana. Historia, wyszukiwanie portfeli i lista publiczna zostają na osobnej puli.
- Łańcuch wstawia przyspieszony wiersz tylko dla pięciu portfeli Mitcha i portfeli, które rzeczywiście kopiują. Pauza i obserwacja zostają na wolniejszej liście publicznej.
- Dla tych pięciu portfeli paragon transakcji jest czytany pod `OrderFilled`: strona, token, ilość, zapłacony USDC. Cena to iloraz tych kwot, nie ask arkusza. Ten sam indeks logu jest jednym wykonaniem. Drugi indeks sumuje się. Zły portfel i zła ilość odpadają. Log `removed` nie jest wykonaniem; niepodjęty wiersz jest usuwany, a kopia już zapisana zostaje z adnotacją, bez odtwarzania. Lista publiczna nie nadpisuje ceny z paragonu. W tym oknie nie było jeszcze wiersza `_source=order_filled`. Gniazdo `last_trade_price` dalej zrywa handshake. To jest niespełnione jako dowód na żywo.
- Spóźniona sprzedaż nie wchodzi po historycznej cenie. Jest próba po bieżącym arkuszu (`LATE_SELL_RECOVERED`) albo pozycja zostaje otwarta do rozliczenia (`LATE_SELL_EXPOSED`). Testy to pokrywają. Na żywej księdze w tym oknie takiej sprzedaży nie było.
- Punkt odniesienia salda ma `as_of`. Zdarzenie ze stemplem równym lub wcześniejszym jest już w saldzie i nie jest doliczane drugi raz. Saldo pobrane po sprzedaży nie jest traktowane jak saldo sprzed niej.
- Nadzór zapisuje rosnącą kolejkę, czas arkusza powyżej 1 s, sygnały przeterminowane przez nas i brak decyzji przy napływie. To jest stan degraded, nie restart. Restart nie opróżnia przeciążonej puli. Brak `BTC_LAB_ALERT_URL` nie wyłącza tej kontroli. Po restarcie nadzór zgłosił `copy_backlog` i nie zrestartował procesu.

## Liczby po restarcie, nie z poprzedniej godziny

Poprzednia godzina (kolejka i zero wykonań) nie jest dowodem.

Przed tą poprawką opublikowana „kolejka” kwalifikatora wynosiła 20, bo taki był `LIMIT`. Rzeczywiste niewidziane z ostatnich 90 s: 313, najstarsze 84 s. Po restarcie publikowany `backlog` jest tą liczbą: około 110–244, z czego kopiujące portfele 23–30 (najstarsze około 65–70 s), reszta to pauza i obserwacja. Napływ około 220–230 / min, decyzje około 20–40 / min. Tor kopiowania nie czeka już za całą pauzą, ale sam nadal ma zaległość rzędu minuty.

Dwa nowe `COPIED_BUY` kwalifikatora po starcie, nie wymuszone:

- wykrycie 218 ms, arkusz HTTP 70 ms i 65 ms, kolejka lokalna 77,8 s
- wykrycie 2,7 s, arkusz HTTP 88 ms i 75 ms, kolejka lokalna 86,7 s

Cel poniżej 1 s od wykonania źródła jest niespełniony. Granica samego arkusza, u nas i poza nami, to około 50–90 ms. Granica, która została, to lokalna kolejka decyzji przy napływie około 4 zdarzeń na sekundę i obsługze około 0,5 na sekundę. Jednosekundowy stempel API nie jest tą kolejką.

Mitch w tym oknie: backlog 0, świeże 0, historia 0, żadnej nowej decyzji. Nie było kwalifikującego się sygnału do skopiowania. Nie dopisałem transakcji.

Pętla zdarzeń po starcie: opóźnienie snu 50 ms spadło do około 1 ms, z jedną próbką 188 ms. Opublikowany arkusz workera dla pulpitu dalej jest `STALE`. Kopia nie używa tego cache. To jest niespełnione dla świeżości pulpitu, osobno od czasu HTTP kopii.

## GitHub

Te rewizje są na `mrbinio/copy-lab-ops`, gałąź `ops/btc-reconcile-2026-10-05`. Potwierdzone odczytem z GitHuba, nie tylko lokalnym logiem:

- https://github.com/mrbinio/copy-lab-ops/commit/08c81e3e6742bfeaa1a41068b28f9ec9f3a2c8b3
- https://github.com/mrbinio/copy-lab-ops/commit/e30aaa1a0f3a42f3ddd9c454354866836bb57ab0
- https://github.com/mrbinio/copy-lab-ops/commit/2e0130f6a9ab00132b8656802c67b0462cda6fb2
- https://github.com/mrbinio/copy-lab-ops/tree/ops/btc-reconcile-2026-10-05

Gałąź po wypchnięciu `6daf3dd..2e0130f` wskazuje `2e0130f`. W `mrbinio/polymarket-copy-lab` tych rewizji nie ma, bo ta praca jest w copy-lab-ops.

## Niespełnione

- Czas od wykonania źródła do kopii PAPER poniżej 1 s. Została lokalna kolejka rzędu minuty przy napływie szybszym niż obsługa.
- Godzina obserwacji czterech okien 15 min bez zaległości. Tego okna nie ma.
- Żywe wypełnienie OrderFilled dla pięciu portfeli. Dekoder jest w kodzie i w testach. Na żywo w tym starcie nie było pasującego paragonu.
- Świeży arkusz na pulpicie workera (`book_status` STALE).
- Nowa kopia Mitcha z pełnymi czasami. Nie było nowego sygnału.
