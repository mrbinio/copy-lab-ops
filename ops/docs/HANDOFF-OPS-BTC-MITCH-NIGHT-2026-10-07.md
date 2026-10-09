# BTC Lab — wynik +88,26 wobec +399,29 — 7 października 2026

PAPER. Strategia, limity, wzór wielkości, reguła 10 centów i `clob_live` bez zmian. Nic nie zostało dopisane do księgi, żeby zbliżyć się do liczby Mitcha. Historia nie była odtwarzana.

## Werdykt

+88,26 USD to suma 14 rozliczonych pozycji PAPER, wszystkie zamknięte w dacie sztokholmskiej 2026-10-07. To cały zamknięty wynik od aktywacji kopiowania, nie osobne „ostatnia noc” zdefiniowane przez Mitcha.

Różnicy 311,03 USD nie da się rozpisać na jedną przyczynę. Nie mamy historii kopii Mitcha, jego przedziału czasu ani strefy czasowej. Poniżej jest nasza strona porównania.

## Okres i 28 wykonań

Aktywacja `mitch_copy_start`: 2026-10-06 19:35:51 czasu sztokholmskiego.

Pierwsze wykonanie: 2026-10-07 00:41:57, portfel `207e77c2`, `MITCH_BUY`, źródło 00:41:45, okno `btc-updown-15m-1791325800` (start 00:30).

Ostatnie wykonanie: 2026-10-07 02:08:48, portfel `mihaXd`, `MITCH_ADD`, źródło 02:08:01, okno `btc-updown-15m-1791331200` (start 02:00).

Rozliczenia tych pozycji: od około 01:00 do 02:27 tego samego ranka. Otwartych pozycji nie ma.

Wszystkie 28 wierszy (`14 MITCH_BUY` i `14 MITCH_ADD`) ma stempel źródła po aktywacji i odpowiadający wiersz w `wallet_activity`. To bieżące kopiowanie, nie test i nie zakup sprzed startu.

Wynik księgi, mikro do dolara: `207e77c2` +65,667397, `mihaXd` +25,297649, `365cf589` −2,703888. Suma 88,261158 USD, na ekranie +88,26. `096b159` i `checkr3` mają zero kopii i zero wyniku.

## Pięć portfeli, nowe transakcje BTC 15 min

Okres: stempel źródła od aktywacji do odczytu 2026-10-07 około 08:38 czasu sztokholmskiego. Liczone są tylko `TRADE` ze stroną `BUY` albo `SELL` i slugiem `btc-updown-15m-`. Redeem, rabat, 5 min i inne rynki są poza tym zestawieniem.

Takich transakcji jest 427. Każda ma decyzję. `096b159` i `checkr3`: zero.

| Portfel | Okno (Sztokholm) | Decyzje |
| --- | --- | --- |
| 207e77c2 | 06 paź 23:15 | 11 spóźnionych, 2 zbyt długie czekanie na arkusz |
| 207e77c2 | 23:30 | 1 spóźniony |
| 207e77c2 | 23:45 | 13 spóźnionych, 5 zbyt długie czekanie |
| 207e77c2 | 07 paź 00:00 | 20 spóźnionych, 2 zbyt długie czekanie |
| 207e77c2 | 00:30 | 1 kupno, 4 dokładki, 7 limit okna, 5 brak płynności, 2 cena gorsza o ponad 10¢ |
| 207e77c2 | 00:45 | 2 kupna, 2 dokładki, 11 spóźnionych, 9 brak płynności, 5 cena |
| 207e77c2 | 01:15 | 1 kupno, 1 dokładka, 35 spóźnionych, 1 limit, 1 czekanie |
| 207e77c2 | 01:30 | 1 kupno, 1 dokładka |
| 207e77c2 | 01:45 | 1 kupno, 2 dokładki, 2 limit, 4 brak ask, 2 nieświeży arkusz, 4 cena |
| 207e77c2 | 02:00 | 1 kupno, 1 dokładka, 45 spóźnionych, 1 limit, 1 brak płynności, 2 sprzedaże bez kopii |
| 365cf589 | 06 paź 23:15 | 2 spóźnione |
| 365cf589 | 23:45 | 15 spóźnionych |
| 365cf589 | 07 paź 00:00 | 3 spóźnione, 2 czekanie |
| 365cf589 | 01:15 | 9 spóźnionych |
| 365cf589 | 01:30 | 1 kupno |
| 365cf589 | 01:45 | 3 cena, 2 nieświeży arkusz |
| mihaXd | 06 paź 23:15 | 7 spóźnionych |
| mihaXd | 23:45 | 5 spóźnionych, 3 czekanie |
| mihaXd | 07 paź 00:00 | 13 spóźnionych |
| mihaXd | 00:30 | 1 kupno, 1 dokładka, 3 limit, 7 brak płynności, 2 cena |
| mihaXd | 00:45 | 1 kupno, 19 spóźnionych, 5 brak płynności, 6 cena |
| mihaXd | 01:15 | 1 kupno, 24 spóźnione, 7 brak płynności, 2 cena |
| mihaXd | 01:30 | 1 kupno |
| mihaXd | 01:45 | 1 kupno, 1 dokładka, 2 spóźnione, 2 limit, 4 brak ask, 4 nieświeży arkusz, 6 cena, 1 brak płynności |
| mihaXd | 02:00 | 1 kupno, 1 dokładka, 42 spóźnione, 1 limit, 5 brak płynności, 1 cena, 1 czekanie |

28 wykonań trzymało pozycję do rozliczenia. Nie ma `MITCH_SELL`. Dwie sprzedaże źródła `207e77c2` w oknie 02:00 dostały `LATE_SELL_RECONCILED`. Jedna, 1,21 USD o 02:12:51, jest innym tokenem niż nasza pozycja. Druga, 234,32 USD po cenie 0,509 o 02:09:55, jest tym samym tokenem. Doszła o 02:09:58, decyzja o 02:14:23, bez zapisanego pomiaru czasu. Pozycja została otwarta i rozliczyła się o 02:27 z wynikiem +30,48 USD. Tej sprzedaży nie skopiowaliśmy. To nie jest wyliczenie brakujących 311 USD.

## Zero kopii 096b159 i checkr3

`096b159`: ostatni zapisany ruch 2026-10-06 06:38, ostatnie kupno BTC 15 min 02:28 tego ranka, obie chwile przed aktywacją. Publiczna lista aktywności od aktywacji zwraca zero wierszy. Brak kopii to brak nowych transakcji źródła, nie błąd klasyfikacji ani wykonania.

`checkr3`: 169 spóźnionych zakupów ma stempel źródła przed aktywacją. Po aktywacji publiczna lista ma 23 wiersze: rabaty i `REDEEM`, zero transakcji `TRADE` BTC 15 min. U nas to samo. Brak kopii to brak kwalifikującego się nowego kupna.

`NOT_BTC_15M` (837 w całym dzienniku projektu) obejmuje też wiersze, które nie są transakcją kupna albo sprzedaży. Próbka slugów `btc-updown-15m-` oznaczonych tym powodem to `REDEEM` prawdziwych rynków 15 min, w tym stare okna rozliczane po aktywacji. Reszta próbki to `btc-updown-5m` i `bitcoin-up-or-down`. Zakres strategii zostaje przy transakcjach BTC 15 min. Tych redeemów nie traktuję jako pominiętych kopii.

## 782 spóźnione zakupy

Okres: cały dziennik od aktywacji do odczytu około 08:44.

- 505 ma stempel źródła przed 2026-10-06 19:35:51. To historia, nie nowy sygnał.
- 277 ma stempel po aktywacji, od 2026-10-06 23:27:42 do 2026-10-07 02:10:36. Program odrzucił je, bo wiek przekroczył 90 s (`LATE_BUY_NOT_COPIED`, klasa kolejki tam, gdzie była zapisana).
- 0 bez znacznika czasu.

Żadna z tych liczb nie jest utraconym zyskiem.

## Opóźnienie i limity okien

Ekran brał pomiar z ostatnich 40 wierszy dziennika. O 08:37 te wiersze to odrzucenia bez czasu, więc próbki spadały do zera, choć 28 wykonań ma zapisany blok czasu. Teraz próbki są liczone z `MITCH_BUY`, `MITCH_ADD`, `MITCH_SELL` i `LATE_SELL_RECOVERED`. Brakującego czasu nie dopisuję.

Po restarcie, z zapisanych pól: wykrycie 28 próbek, mediana 2944 ms; kolejka 28, mediana 24613 ms, żadna poniżej 1 s; księga 28, mediana 62 ms. Pełny czas od źródła do końca jest potwierdzony tylko dla 2 wykonań ze stemplem drobniejszym niż sekunda (mediana 21326 ms). Pozostałe 26 mają sekundowy stempel API, więc `total_ms` zostaje puste.

Suma wydatków od startu to nie wykorzystanie jednego okna. `207e77c2` wydał 97,50 USD w sześciu oknach, każde osobno od 9,05 do 19,67 przy limicie 20. `mihaXd` wydał 23,02 USD w sześciu oknach, każde od 1,85 do 4,96 przy limicie 5. `365cf589` jedno okno 2,70 przy limicie 20. Zero okien ponad własny limit. Ekran pokazuje wydatki od startu osobno od bieżącego okna.

## Co zostało zmienione

- Publikacja opóźnienia czyta wykonania, nie ogon dziennika.
- Publikacja rozdziela spóźnione zakupy na historię sprzed aktywacji i sygnały po aktywacji.
- Każdy wiersz `mitch_windows` jest porównywany z limitem tego portfela. Suma okien nie jest pokazywana jako użycie jednego limitu.
- Test: nowsze odrzucenie bez czasu nie zeruje próbki wykonania; dwa okna po 15 USD przy limicie 20 nie są przekroczeniem.

Wgrane do wydania `b009e2b8b429-1790926011187411000`. Usługa papierowa zrestartowana raz. `/healthz` 200, worker `RECORDING`, publikacja ma 28 próbek. Stary błąd `database is locked` ma ponad 13 godzin i nie jest tym restartem.

## Niespełnione

Cel poniżej 1 s od źródła do PAPER jest niespełniony: mediana kolejki tych 28 wykonań to 25 s. Nie było nowej sześćdziesięciominutowej obserwacji czterech okien. Nie było żywego paragonu `OrderFilled`. Arkusz workera na ekranie pozostaje osobnym, nieświeżym odczytem; kopie biorą własny arkusz.

## Następna decyzja

Do porównania z +399,29 potrzebna jest lista kopii Mitcha, początek, koniec i strefa czasowa. Bez tego nasza strona zostaje przy +88,26 za opisany wyżej ranek.
