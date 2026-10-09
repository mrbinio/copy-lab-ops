# Audyt strat kopiarki — 7 października 2026, Europe/Stockholm

## Werdykt

Pauza działa tak, jak jest napisana: w tej samej transakcji co zamknięcie, które sprowadza wynik okresu poniżej zera, i od tej sekundy nie ma nowych BUY ani dokupień. Nie ogranicza straty do jednego centa. Pozycje otwarte wcześniej rozliczają się po pauzie, a powrót z pauzy po małym plusie obserwacji otwiera kolejny okres.

Total na żywej księdze o 22:15 czasu Sztokholmu to **−45,885974 USD** (289 zamknięć). Zgadza się z opublikowaną tablicą `paper-board-v1`. Liczba **+9,09 USD** to ta sama księga o **16:19:10**, nie inna suma. Otwarte pozycje (8) są poza tym totalem.

## Skąd cztery duże straty

Wszystkie cztery to portfele kwalifikatora, nie Mitcha. Podział: wynik zapisany w chwili pauzy, późniejsze rozliczenie pozycji, które były wtedy otwarte, oraz strata po kolejnej aktywacji.

| Portfel | Dziś 22:15 | O 16:19 | Pełne pętle plus → strata → powrót | Suma strat tych pętli | Plusy obserwacji przed nimi |
|---|---:|---:|---:|---:|---:|
| …99e456ea | −43,639195 | −30,28 | 5 (szósta pauza od 17:45 bez powrotu) | −15,46 | +16,75 |
| …8a2e7537 | −18,4926 | −12,07 | 2 (trzecia pauza od 19:55 bez powrotu) | −7,69 | +3,36 |
| …218d69a9 | −14,860925 | −14,86 | 1 (druga pauza od 09:01 bez powrotu) | −4,50 | +2,66 |
| …7ef0e468 | −11,59679 | −11,60 | 0 | — | — |

−30,28 i −12,07 urosły po 16:19 o ostatni cykl: …99e456ea −3,91 przy pauzie i −9,45 z pozycji otwartych w chwili pauzy; …8a2e7537 −1,76 i −4,66. …218d69a9 i …7ef0e468 nie zmieniły się od popołudnia.

…7ef0e468: jedna aktywacja 12:36, pauza 13:23:14 na −3,27206. W chwili pauzy otwarte były 2 pozycje za 8,32 USD. Rozliczyły się na −4,77 (13:34) i −3,56 (13:54). Dziś = −3,27 + −8,32.

Po każdej pauzie, aż do następnego powrotu albo do teraz, nie ma `COPIED_BUY` i nie ma pozycji z `opened` w tym oknie.

## Dziura przed pauzą

`settle()` oznaczał pozycję jako `RESOLVED` z oficjalną wypłatą i czekał 300 sekund, zanim `close()` zapisał wynik i wywołał pauzę. W tym oknie wynik okresu nadal nie widział straty, więc kolejny zakup przechodził.

Przykład …7ef0e468: oficjalny wynik o 13:15:08, zakup o 13:16:55 (107 sekund później, później −3,56), pauza dopiero o 13:23:14. Takie zakupy po `official_seen_at` i przed zamknięciem: …99e456ea 1, …218d69a9 3, …8a2e7537 11, …7ef0e468 1.

Poprawka: znana wypłata `RESOLVED` wchodzi do księgi pauzy od razu (wypłata minus koszt i opłata wejścia, bez opłaty wyjścia — ten sam wzór co późniejsze zamknięcie). Zapis `RESOLVED` i pauza są w jednym `BEGIN IMMEDIATE`. SELL i rozliczenie gotówki zostają. Próg pauzy, `min_pause_days = 0` i powrót po jednym plusie obserwacji są bez zmian.

## Total i zielone PAUSED

Zamknięcia 7 października: 289, brakujące `pnl_micro`: 0, wzór `wypłata − opłata wyjścia − koszt − opłata wejścia` zgadza się na wszystkich. Jedna sprzedaż częściowa. Dodatnie kafelki 74,032074 (9 portfeli), ujemne −119,918048 (10), suma −45,885974. Zaokrąglenie kafelków do centów może różnić się o 1 cent od zaokrąglonej sumy; o 16:19 było +83,62 i −74,54 wobec totalu +9,09.

Osiem otwartych pozycji jest poza dniem: cztery na …9b9fa354 (powrót z pauzy 22:05:13, w nowym okresie zero zamknięć) i cztery na …f11764d4.

Zielony kafelek to wynik dnia, nie wynik okresu pauzy:

| Portfel | Wynik dnia | Wynik okresu, który wstrzymał zakupy | Pauza od |
|---|---:|---:|---|
| …b6cb9e2e | +14,54 | −3,76016 | 08:29 |
| …e9adc964 | +7,03 | −1,16772 | 17:54 |
| …ea096f11 | +3,60 | −1,210965 | 14:08 |
| …a0776eae | +1,06 | −0,95166 | 17:22 |
| …1fc022d2 | +0,08 | −4,723565 | 20:18 |

Tablica niesie teraz `pause_period_net_usd`, a kafelek pokazuje oba wyniki.

## Co weszło na Maca

Git nadal `e001caf`. Do działającej rewizji `b009e2b8b429-1790926011187411000` wgrane: `wallet_roster.py`, `wallet_copy.py`, `copy_totals.py`, `lab/app.js`. `com.btc-lab.paper` zrestartowana raz, pid 6459. Testy: `test_wallet_roster` 25, `test_copy_totals` 10, `test_wallet_copy` 47.

LIVE wyłączone. Strat nie resetowano. Progów nie ruszano.

## Następna decyzja

Pętla „mały plus obserwacji → aktywacja → większa strata → pauza → kolejny plus” jest regułą `min_pause_days = 0` i jednego dodatniego handlu obserwacji. …99e456ea zrobił jej pięć w jeden dzień. Zmiana tego progu albo blokady kalendarzowej czeka na osobną decyzję.
