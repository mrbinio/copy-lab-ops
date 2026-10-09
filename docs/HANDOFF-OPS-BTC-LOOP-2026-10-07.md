# BTC Lab — pętla i health, 7 października 2026

## Werdykt

`/healthz` na porcie 8769 zwraca 200. Worker jest `RECORDING`, cena referencyjna `FRESH`, heartbeat ma kilka sekund. Mitch i kopiarka znowu robią krok (kolejka Mitcha 0, krok około 10 s; kopiarka krok około 30 s, paczka 20).

## Co było zepsute

Zapis dużej bazy i długi odczyt księgi szły tym samym wątkiem co kopiowanie, a monitor łańcucha logował każde porzucone zdarzenie. Pętla nie kończyła połączenia websocketu ceny. `/healthz` zostawał 503, a heartbeat stał w `STARTING` przez wiele minut.

## Co jest na żywym procesie

Pliki w wydaniu `b009e2b8b429-1790926011187411000`: zapis bazy osobno od długiego odczytu, arkusz 15m trzymany w pamięci dla ścieżki Mitcha, heartbeat co 10 s, porzucenia łańcucha logowane raz na 5 s. Usługa była restartowana, żeby ten kod wszedł. `clob_live` bez zmian, wyłączone.

## Czego ten restart nie domknął

Publiczny websocket wydruków rynku (`last_trade_price`) dalej urywa się na otwarciu połączenia. Nie ma z niego próbki ceny poniżej sekundy. Opublikowany arkusz w stanie workera miał około 110 s, więc linia arkusza jest `STALE`. Zielony health dotyczy ceny referencyjnej, nie świeżości arkusza i nie czasu kopii.

Nie było żywego wypełnienia Mitcha w tym restarcie. Nic nie zostało dopisane jako transakcja.
