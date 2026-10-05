# Handoff — pętla zdarzeń, 5 października 2026

## Executive summary

Cena referencyjna i monitor łańcucha rozłączały się co około 45 sekund na `timed out during opening handshake`. Przez to `/healthz` zostawał 503, a kolejka 30 zadań łańcucha porzucała transakcje. Przyczyna: odbiór aktywności i odczyt listy portfeli robiły zapis bazy na pętli zdarzeń. Jedna pełna strona API zamrażała sockety na dłużej niż limit pinga.

## Co się zmieniło i dlaczego

Pobranie i zapis aktywności portfela idą w wątku. Lista portfeli zakłada tabelę raz, a kolejne odczyty już nie biorą blokady zapisu. Publikacja stanu kopiowania i czyszczenie starych notowań też schodzą z pętli. Pełna dwudziestka decyzji od razu bierze następną, bez czekania sekundy. Śledzenie transakcji na łańcuchu czeka na publiczną listę 2 sekundy, nie 60, więc jeden brak w księdze nie zajmuje slotu przez minutę. Obserwator i tak odpytuje co sekundę.

Hasło, port 8769, limity i `clob_live=false` zostają. LIVE zostaje wyłączone.

## Następna decyzja

Po restarcie sprawdzić, czy w logu jest `chain monitor connected` i czy `/healthz` wraca do 200. Jeśli handshake dalej pada przy wolnej pętli, to już nie ten zapis.
