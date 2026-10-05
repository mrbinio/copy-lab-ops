# Handoff — paper-roster-v2, 5 października 2026

## Executive summary

Reguły kopiowania PAPER są teraz w wersji `paper-roster-v2`. Poprzednia definicja `paper-roster-v1` zostaje w kodzie i w stanie listy. Historia strat i baza zostają. Zlecenia na żywo są wyłączone.

## Co się zmieniło i dlaczego

Audyt pokazał, że samo zdjęcie 14 dni zostawiło blokadę 7 dni przy wejściu z obserwacji do testu, pauzę −15 USD / 7 dni albo 8 strat, oraz powrót za +8 USD i 10 transakcji liczony z całej księgi obserwacji.

- Wejście do testu nie ma już blokady kalendarzowej. Zostają 20 rozliczeń, 5 okien, dodatni wynik i limit 70% na jeden dzień.
- Nowe zakupy blokuje ujemny, znany wynik zamkniętych kopii otwartych w bieżącym okresie tej kopii. Brak wyniku nie jest zerem. Otwarte pozycje nie wchodzą do tej sumy. Sprzedaż i rozliczenie zostają.
- Powrót bierze tylko obserwacje otwarte po ostatniej pauzie. Wystarczy dodatni wynik po kosztach. Poniżej 10 takich zamknięć próba jest niepewna. Stare straty zostają w księdze.
- Dokupienie powiększa otwartą pozycję. Sprzedaż źródła zamyka taką samą część naszych udziałów. Brak rozmiaru źródła nie zamyka całości.
- Pasmo 20–70¢ zostaje limitem tej wersji. Zakup za 75¢ odpada przez ten limit. To nie jest teza, że taka cena jest z góry stratna. Zmiana pasma wymaga osobnego PAPER.

## Dziennik o 09:56

Ostatnie zamknięcie PAPER to 09:56:37, portfel …4096b159, SETTLED −2,13 USD, rynek `btc-updown-5m-1791185700`. Zakup został skopiowany o 09:35:45. Publiczna aktywność tego portfela nie ma nowszej transakcji. Portfel testowy …dcfcf46e nie ma wykrytej transakcji źródła. Reszta listy jest obserwowana albo wstrzymana, więc ich sygnały są `SOURCE_TOO_OLD` albo `COPY_PAUSED` i nie wchodzą do dziennika PAPER.

## Następna decyzja

Po restarcie lista przeliczy bieżący okres. Portfel …4096b159 ma od 08:50 zamknięcie −2,13 USD, więc nowe zakupy tego okresu zostaną wstrzymane. Wynik historyczny +14,52 USD zostaje. Sprzedaż otwartej pozycji nadal może przejść. Otwartych pozycji w chwili odczytu było zero.
