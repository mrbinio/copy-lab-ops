# Handoff — saldo źródła na bloku, 5 października 2026

## Executive summary

Księga źródła dostaje stan z łańcucha: saldo tokenu na końcu bloku `head - 5`, potem transfery z późniejszych bloków w kolejności logu. Pierwszy wykryty handel nie otwiera pozycji od zera. Na Macu jest 6 potwierdzonych pozycji i 1415 nieznanych. Jedna pozycja została sprawdzona drugim odczytem: 254,89 udziału na bloku 95013958 plus zakup 60 na bloku 95013960 daje 314,89. Sprzedaży po takim odczycie jeszcze nie było. Zlecenia na żywo są wyłączone.

## Co się zmieniło i dlaczego

`anchor_source_position` było wołane tylko z testów. Proces nic nie czytał, więc po poprzednim wdrożeniu wszystkie pozycje zostały nieznane.

Odczyt idzie przez HTTPS z adresu `ALCHEMY_WSS` (host `rpc-polygon.blockmachine.io`). `eth_call` woła `balanceOf` kontraktu warunkowych tokenów na konkretnym bloku. `eth_getLogs` bierze transfery tego tokenu od następnego bloku do głowy łańcucha. Godzina odebrania odpowiedzi nie wyznacza, które transakcje saldo już zawiera. Kolejność to blok i numer logu. Ten sam transfer ma jeden klucz i nie dolicza się drugi raz po restarcie. Brak odpowiedzi zostawia pozycję nieznaną. Jeden nieuporządkowany sygnał nie kasuje już zapisanego salda.

Odczyt stoi w `upkeep`, obok pętli kopiowania, więc nie zatrzymuje odbioru sygnałów. Sprzedaż przy już potwierdzonej pozycji odświeża ten token przed wyliczeniem proporcji. Nie otwiera to zlecenia. Historyczne wiersze nie wracają jako nowe zakupy. Limity 5 USD i 25 USD oraz pauza zakupów zostają.

## Liczby

Po restarcie rewizji `24de3946c6c70d1bc73b8c75f7cc523962235e8b`, jeden proces na porcie 8769, `clob_live` false:

- 6 potwierdzonych pozycji, 1415 nieznanych
- potwierdzenie ma 3 z 25 portfeli w księdze; reszta czeka, aż znowu handluje
- przykład: portfel `…218d69a9`, token `…97887701`, blok 95013958, saldo 254,89, potem BUY 60 na bloku 95013960, log 801, transakcja `…0e920bde`; zapisane udziały 314,89
- drugi przykład bez późniejszego transferu: portfel `…f11764d4`, token `…43576684`, blok 95013965, 120 udziałów, zgodne z `eth_call`
- w ostatnich minutach nie było `COPIED_BUY` ani `COPIED_SELL`; sprzedaży źródła po nowym odczycie też nie było

## Co sprawdziły testy, a co rynek

Testy: transfer wchodzący w trakcie odczytu salda dolicza się raz; dwa zdarzenia z tej samej sekundy idą po numerze logu i sprzedaż 60 z 240 to 25%; dwa fille w jednej transakcji wchodzą oba; duplikat i drugi odczyt nie zmieniają udziałów i nie otwierają kopii; brak odpowiedzi zostawia pozycję nieznaną; transfer z bloku salda nie jest dodawany drugi raz.

Rynek: saldo na bloku i jeden późniejszy zakup zgadzają się z paragonem transakcji. Proporcji sprzedaży na żywo nie ma, bo takiej sprzedaży po odczycie nie było.

## Następna decyzja

Nieznane zostają tokeny bez świeżego handlu. Kolejny cykl bierze kilka takich tokenów. Proporcja sprzedaży pojawi się przy pierwszej sprzedaży po zapisanym bloku. Kopiowanie zostaje papierowe.
