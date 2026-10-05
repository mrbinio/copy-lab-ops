# HANDOFF — Uzgodnienie księgi i łącza po zaniku 2026-10-05

## Executive summary

Różnica **−98,43** i **−126,13** nie była błędem księgi. W tabeli brakowało **4 starych kont** spoza obecnej listy: **11 transakcji, −27,71 USD**. Po nocnej przerwie `4096b159` rozliczył jeszcze jedną kopię (**−2,13 USD**). Teraz cała księga to **−128,27 USD / 551 transakcji**. Aktywne kopie (tylko `4096b159`, honey-spot ma zero) to **+14,52 USD**.

Żywe zlecenia są wyłączone (`clob_live=false`). Publiczna historia adresu klucza w oknie przypadkowego włączenia jest pusta. Lista zleceń CLOB po zalogowaniu **nie została** odczytana, bo to wymaga podpisu.

Łącza padały, bo kopiarka co sekundę skanowała całą tabelę aktywności na tej samej pętli co WebSocket. Po zdjęciu tego skanu trzy pełne okna 15-minutowe (09:45–10:30) miały odbiór zdarzeń, jeden zestaw procesów i powrót po celowym zerwaniu ceny. `PRAGMA quick_check` bieżącej bazy: **ok**.

## Uzgodnienie

Źródło: `wallet_copy_positions` + `wallet_copy_ledger` + `wallet_copy_accounts`. Kwota netto to `wypłata − koszt zakupu − opłata wejścia − opłata wyjścia`. Gotówka konta = 500 USD + suma księgi. Sprawdzone dla każdego konta, które handlowało. Duplikatów `id` nie ma. Otwartych pozycji: **0**, więc niezrealizowane = **0** (nie „brak danych”).

| Konto | Stan | Netto USD | Transakcje |
| --- | --- | --- | --- |
| `4096b159` | paper_active | +14,518414 | 82 |
| honey-spot `dcfcf46e` | paper_test | 0,000000 | 0 |
| Atomforge `69de3680` | paused | −16,573060 | 87 |
| `365cf589` | paused | −37,980466 | 70 |
| `207e77c2` | paused | −36,738110 | 66 |
| `3e6eba30` | paused | −23,785680 | 235 |
| **Lista razem** |  | **−100,558902** | **540** |
| `9b9fa354` | stare, poza listą | −9,769020 | 2 |
| `cf2104ae` | stare, poza listą | −8,675462 | 6 |
| `f11764d4` | stare, poza listą | −4,865888 | 1 |
| `2608ad88` | stare, poza listą | −4,398769 | 2 |
| **Poza listą** |  | **−27,709139** | **11** |
| **Cała księga** |  | **−128,268041** | **551** |

Wcześniejsze −126,13 / 550 to ta sama księga **przed** ostatnim rozliczeniem `4096b159` (−2,134665). Historia nie była kasowana.

Koszt zakupu 2 335,34 USD, opłata wejścia 83,49 USD, opłata wyjścia 4,42 USD, wypłaty 2 294,98 USD. Różnica = **−128,27 USD**.

Stany są **rozłączne**: paper_active **1**, paper_test **1**, paused **4**, tylko obserwowany **0**. Wcześniejsze „2 / 6 / 4” nakładało „obserwowane” na aktywne i wstrzymane.

## Baza

Odzysk 5 października rano, około 08:28–08:44, z **uszkodzonego żywego** `lab.sqlite` (`sqlite3 .recover`), nie z backupu z 1 października. Uszkodzony plik 6,9 GB został wtedy skasowany, więc nie da się go już porównać bajt po bajcie. Zostają 2 backupy BTC i 2 ETH z 1 października. Nic więcej nie kasowałem.

`PRAGMA quick_check` na bieżącym pliku (około 10:35): **ok**. Luka 00:02–08:25 to wyłączony Mac, nie wycięte wiersze. Starych sygnałów nie wgrałem jako nowych zakupów.

## Łącza

Przyczyna timeoutów handshake i `healthz` 503: `INSERT` po całej `wallet_activity` (ponad 100 tys. wierszy) na wątku pętli asyncio. Pętla nie zdążała dokończyć WebSocketu, a obserwacja starsza niż 10 s była odrzucana jako nieświeża. Kontroli świeżości nie ruszałem. `healthz` dalej jest 503, gdy worker nie jest `RECORDING`.

Został odczyt tylko świeżych wierszy (90 s), poza pętlą. Ponowne łączenie czeka 1→2→4… do 30 s. Martwe gniazdo jest zamykane pingiem.

Trzy pełne okna, próbka co 30 s, te same PID 5702 / 5704 / 5706 / 5707 / 5708:

| Okno | RECORDING | health 200 | Nowe zdarzenia | Najstarszy heartbeat |
| --- | --- | --- | --- | --- |
| 09:45–10:00 | 30/30 | 30/30 | +46 | 7,9 s |
| 10:00–10:15 | 29/30 | 29/30 | +74 | 9,8 s |
| 10:15–10:30 | 28/30 | 28/30 | +56 | 9,3 s |

Cztery próbki na 103 były `DEGRADED` i miały `healthz` 503. To jest poprawne, nie maskowane. O 09:46:38 celowo zerwałem strumień ceny. Wrócił przed następną próbką, bez drugiego procesu i bez restartu usługi.

## LIVE

`clob_live=false`. Między 08:24 a 08:45 nie było `COPIED_BUY`, więc kod wysyłki w ogóle nie wszedł. Publiczne API aktywności dla adresu wyprowadzonego lokalnie z klucza (końcówka `36a3bF01`) w 06:20–06:50 UTC: **0 wierszy**. Nie podpisywałem niczego i nie czytałem zalogowanej listy zleceń CLOB. Tej listy **nie potwierdzam**. W konfiguracji nie ma osobnego adresu proxy.

## Opóźnienie

`source_ts` z REST to timestamp API, nie czas bloku. `first_seen` to lokalny zapis. `chain_fast` wpisuje w timestamp **lokalny czas wykrycia** (`_detected_at`). Różnicy `first_seen − source_ts` dla chain_fast **nie wolno** nazywać czasem od transakcji źródłowej.

Jedna nowa kopia PAPER w tym oknie (`4096b159`, REST, n=1). CLOB: podpis, wysłanie i potwierdzenie = brak pomiaru, tryb nieaktywny.

| Etap | ms |
| --- | --- |
| API → lokalny zapis | 4628 |
| kolejka po zapisie | 416 |
| książka | 144 |
| decyzja po książce | 0,1 |
| symulacja PAPER | 0,3 |
| od zapisu do decyzji | 1704 |

Między startem obsługi a książką zostaje około **1144 ms** na odczyt rynku. To nie jest osobne pole w tej próbce. chain_fast w tej jednej kopii nie występuje. Mediana i p95 przy n=1 są tą samą liczbą. Stare bilety bez pól ścieżki nie są w tym n.

## Roster `paper-roster-v1`

Progi **nie były** dopasowane do dzisiejszego wyniku. −15 USD / 7 dni to kilka strat min-lotu, nie jedna pechowa transakcja. Powrót wymaga +8 USD, 10 hipotetycznych transakcji i 14 dni, żeby jedna zielona sesja nie włączała portfela z powrotem. To eksperyment PAPER. Nie podnosi limitów ryzyka i nie dowodzi przewagi.

Od restartu o 09:36 wstrzymane portfele dostały **146** hipotetycznych ocen (123 z wypełnieniem czekającym na rozliczenie, 11 bez pełnego fillu, 12 niedostępnych). Prawdziwe straty zostają. Warunek powrotu zaczyna się liczyć od teraz, nie z nocy.

## Commit i Mac

Kod: `6c29ea9` na gałęzi `ops/btc-reconcile-2026-10-05`.
Na Macu te pliki są **skopią** w release `b009e2b8b429-1790926011187411000`. Napis `revision` w konfiguracji nadal jest starym skrótem release — nie restartowałem usługi tylko po to, żeby go zmienić. Hasło, baza i port **8769** bez zmian.

https://github.com/mrbinio/copy-lab-ops/commit/6c29ea9ffc51fb75740b30308f9fa0b0ad9ae8ca
