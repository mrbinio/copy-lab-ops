# Handoff — weryfikacja salda źródła, 5 października 2026

## Executive summary

Niepełna odpowiedź `balanceOf` nie jest już zerem. Proporcja sprzedaży wymaga jednego logu tego portfela, tokenu i ilości. Sprzedaż starsza niż `head - 5` liczy się z salda sprzed jej bloku, nie z bieżącego salda. Kolejka kopiowania czytała całą historię każdego portfela (1,7 s) i przez to decyzje wpadały po oknie 90 s. Po zmianie ten sam odczyt na żywej bazie trwa 0,7 ms. Otwartych kopii PAPER jest zero. Źródła handlują: w ostatniej godzinie w strumieniu jest 17 232 BUY i 3 SELL. Kopii nie ma, bo portfele z transakcjami są w obserwacji albo na pauzie, a jedyny portfel z włączonym kopiowaniem nie ma wiersza w strumieniu. LIVE zostaje wyłączone.

## Co się zmieniło i dlaczego

`token_balance_raw` brało `None` i `0x` jako saldo zero. Potwierdzone zero to pełne słowo 32 bajtów. Krótsza albo pusta odpowiedź jest błędem i nie zapisuje pozycji.

`proportion_for_transaction` przy braku zgodnego rozmiaru oddawało jedyny SELL z transakcji. Teraz potrzebny jest portfel, token i dokładna ilość. Dwa fille tej samej wielkości zostają bez potwierdzenia. Inna ilość bierze swój log i nie zużywa cudzego.

`historical_sell_proportion` czyta saldo na bloku sprzed sprzedaży i logi wcześniejsze w tym bloku. Saldo głowy łańcucha już zawiera starą sprzedaż, więc nie daje jej proporcji. Funkcja nie zapisuje transakcji w księdze.

Odczyt przed SELL nie stoi już w środku jednej kolejki. Sprzedaże startują razem, a portfele schodzą równolegle. Test: sygnał drugiego portfela rusza, zanim kończy się odczyt sprzedaży pierwszego.

Kolejka `pending_activity` szła po kluczu portfela i skanowała jego całą historię. Na Macu jeden taki odczyt trwał 1713 ms i zwracał 20 wierszy. Decyzje z ostatniej godziny miały medianę opóźnienia 94 s, przy progu 90 s. Zapytanie jest teraz przypięte do indeksu `wallet_activity_seen`. Ten sam odczyt na żywej bazie, bez zapisu, trwał 0,7 ms. Indeks już był. Nowego indeksu na bazie 6 GB nie zakładam.

Po pierwszym restarcie świeże sygnały i tak zostawały bez decyzji: 443 wiersze z dwóch minut, 421 bez wpisu. Publikacja stanu przy każdym kroku trzymała blokadę zapisu przez sortowanie 153 522 decyzji (ostatni powód portfela około 1 s, zbiorczy licznik 1,4 s). Inne zapisy, w tym odbiór aktywności, dostawały `database is locked`. Zapis kont jest teraz osobno i krótki. Ostatni powód trzyma pamięć procesu i odświeża się z bazy najwyżej co 30 s.

Limity 5 USD i 25 USD, hasło, port 8769 i `clob_live=false` zostają. Historia nie jest kasowana. Stare transakcje nie wracają jako nowe zakupy.

## Liczby

Odczyt około 21:48 czasu lokalnego, przed restartem tej poprawki. Działający proces to jeszcze `24de394`.

Otwarte kopie PAPER: 0. Żadna otwarta kopia nie czeka na potwierdzenie pozycji źródła. Osobna księga obserwacji ma 1 pozycję OPEN i 1 RESOLVED. To nie są kopie.

Pozycje źródła: 54 potwierdzone, 2069 nieznanych. Z nieznanych, po slugu z ostatnich 6 godzin: 1869 tokenów rynków już zakończonych, 68 tokenów rynków jeszcze trwających, 132 bez sluga (brak danych). Tokeny naszych otwartych kopii wśród nieznanych: 0. Tokeny otwartej obserwacji wśród nieznanych: 2.

Ostatnia godzina, tabela `wallet_activity`, nie dziennik PAPER: 17 995 wierszy, w tym 17 232 BUY i 3 SELL. Decyzja jest przy 6730. Bez decyzji: 11 265, bo wolna kolejka nie zdążyła przed oknem. Powody decyzji: `SOURCE_TOO_OLD` 4057, `COPY_PAUSED` 2584, `NOT_BUY_OR_SELL` 88, `ERROR` 1 (`MARKET_CLOSED`). Skopiowanych: 0.

Czas odczytu łańcucha, bez zapisu do księgi: numer bloku 358 ms, `balanceOf` 83 ms (portfel `…f11764d4`, blok 95013965, 120 udziałów), logi 231 ms. Jedna prawdziwa sprzedaż `…98478dbf`, 8,24 udziału, rynek `btc-updown-5m-1791225900`, saldo sprzed bloku 95014009, proporcja 0,99899, cały odczyt 508 ms. Bieżąca głowa była 95016316, więc ta sprzedaż jest starsza niż `head - 5`. Wiersza w księdze kopii nie ma: portfel jest obserwowany i nie ma otwartej pozycji PAPER. Odczyt salda potwierdzony. Kopia tej sprzedaży na rynku niepotwierdzona.

## Co sprawdziły testy, a co rynek

Testy: 14 `test_source_chain`, 40 `test_wallet_copy`. Brak wyniku, `0x` i `0x0` są błędem. `0x` i 64 zera to saldo zero. Dwa różne rozmiary w jednej transakcji dostają własne proporcje. Dwa takie same rozmiary nie dostają żadnej. Sprzedaż przy głowie 200 i saldzie 150 na bloku 195 wychodzi 0,25 z salda 100 na bloku 99, a 50/150 tym nie jest. Drugi portfel nie czeka na sen odczytu sprzedaży.

Rynek: saldo na bloku zgadza się z zapisaną pozycją. Proporcja jednej starej sprzedaży została odtworzona odczytem i nie weszła do księgi. Kolejka na żywej bazie spada z 1713 ms do 0,7 ms. Po restarcie proces ma tę poprawkę. Dopóki restart nie minie, decyzje nadal liczy stary kod.

## Następna decyzja

Kopiowanie zostaje papierowe. Jedyny portfel z zakupem włączonym, `…dcfcf46e`, ma świeży poll i pustą stronę API z 24 godzin. Portfele, które handlują, są w obserwacji albo na pauzie. Nie włączam ich stąd.
