# HANDOFF — Zegar Maca cofnięty o 2 s zablokował całe kopiowanie 2026-10-02

## Executive summary

Kopiowanie stało **całkowicie** przez ponad 50 minut — zero nowych pozycji między 14:56 a 15:48 — mimo że łańcuch widział transakcje w 0,1–0,4 s. Powodem nie był kod handlowy, tylko **zegar Maca spóźniony o 2,04 sekundy**. Każda świeża książka zleceń z Polymarketu miała znacznik czasu „z przyszłości" względem naszego zegara, więc kontrola świeżości ją odrzucała i cała kopia kończyła się błędem `stale/future book`. Po poprawce dwie pierwsze kopie poszły w **0,56 s** i **1,33 s** od wykrycia transakcji na łańcuchu. To najszybsze czasy, jakie ten projekt kiedykolwiek miał. Pieniądze realne nadal $0 — to nie zmienia się tą poprawką.

## Co się działo

`normalize_book` wymagało, żeby znacznik czasu książki mieścił się w oknie od `now - 0,25 s` do `now + 8 s`. Przy zegarze spóźnionym o 2 s świeża książka wyglądała na wysłaną 2 sekundy w przyszłość, więc wpadała poza dolną granicę `-0,25`. Pomiar na żywo: mediana `now - source` = **−2,018 s** na 8 próbkach, wszystkie 8 odrzucone. `sntp time.apple.com` potwierdził `+2,042984 +/- 0,004245` s. Nagłówki `Date` z trzech różnych serwerów HTTP dały +1,1 / +1,9 / +1,8 s.

Skutki, które wcześniej wyglądały na osobne usterki, a były tym samym:

- 42 błędy `stale/future book` w 10 minut i zero kopii,
- worker w stanie `DEGRADED` z `book_status: STALE`, przy 366 zapisanych obserwacjach książek w tym samym czasie,
- sztuczne czekanie ~1,8 s przed każdą próbą — bot czekał, aż lokalny zegar „dogoni" transakcję.

## Co zmieniłem

1. **Nowa klasa `VenueClock` w `lab/core.py`.** Zbiera różnicę między znacznikiem czasu giełdy a naszym momentem odbioru, bierze **medianę z ostatnich 15 próbek** i ogranicza wynik do ±30 s. Mediana, a nie średnia, bo jeden dziwny znacznik nie może przesunąć całej oceny.
2. **`normalize_book` liczy świeżość w czasie giełdy.** Warunek zmienił się z `-0,25 <= now - source <= max_age` na `-0,25 <= now + skew - source <= max_age`. Książka naprawdę stara nadal jest odrzucana, a znacznik absurdalnie przyszły (poza limitem 30 s) też.
3. **Worker i kopiarka mają własny `VenueClock`.** `Worker.books()` i `WalletCopy.book()` przekazują go do `normalize_book`. Osobne instancje, bo kopiarka pyta inny zestaw tokenów w innym tempie.
4. **Rozliczanie i przegląd pominięć zeszły z gorącej ścieżki.** Nowa pętla `WalletCopy.upkeep()` robi to obok, a nie wewnątrz `step()`, więc cykl kopiowania nie czeka na wywołania `/markets/`.

Limit ±30 s jest celowo niski. Gdyby zegar odjechał o minuty, lepiej żeby bot przestał handlować, niż żeby ufał zepsutemu pomiarowi.

## Liczby

| Pozycja | Przed | Po |
| --- | --- | --- |
| Kopie w ostatnich 50 min | 0 | 2 otwarte |
| Od wykrycia na łańcuchu do otwarcia kopii | brak (same błędy) | **0,56 s** i **1,33 s** |
| Wykrycie na łańcuchu | 0,06–0,32 s | 0,06–0,32 s (bez zmian) |
| Błędy `stale/future book` | 42 / 10 min | 0 od restartu |
| Stan workera | `DEGRADED`, `book_status: STALE` | `RECORDING`, referencja `FRESH` |
| Starsze `copy_delay` | 7,3 / 8,5 / 9,8 / 28,6 / 29,2 s | — |
| Zmierzone przesunięcie zegara | `book +2,04` / `reference −1,73` (błędnie) | `book +0,071` / `reference 0,0` |
| Testy | 188 | **196, wszystkie zielone** |
| Rozmiar raportu | 263 569 B (limit 700 000) | bez zmian |

Dwie nowe pozycje po restarcie: `btc-updown-5m-1790948100` Down (0,56 s) i `btc-updown-5m-1790948400` Down (1,33 s), obie z portfela `0xeebde7a0`, obie wykryte przez `chain_fast`.

## Druga tura: pierwsza poprawka była niepełna

Po wgrożeniu sprawdziłem resztę kodu i znalazłem **sześć kolejnych miejsc**, które po przyjęciu książki znów sprawdzały świeżość lokalnym zegarem. `normalize_book` przepuszczał dane, a zaraz potem odrzucał je warunek niżej. To właśnie dlatego worker stał w `DEGRADED` nawet wtedy, gdy książki już przechodziły.

Naprawione przez jedną wspólną metodę `VenueClock.age(source, received)`, użytą we wszystkich kontrolach świeżości:

- `worker.py` — świeżość książki przy wyjściu, świeżość referencji do wyliczania cech, `books_fresh` przy próbkowaniu modelu, walidacja książki i referencji przy wejściu, status workera.
- `wallet_copy.py` — `DECISION_STALE_OR_EMPTY` i `ARRIVAL_INVALID`. Oba miały dolną granicę `0<=`, czyli były jeszcze wrażliwsze niż książki w workerze.

**Osobne zegary dla osobnych źródeł.** Worker ma teraz `book_clock` i `reference_clock`, bo książki zleceń i notowania to dwie różne giełdy z dwoma różnymi czasami. Jeden wspólny pomiar ukryłby dryf w którymkolwiek z nich.

### Błąd w moim własnym estymatorze, złapany na żywo

Po wgrożeniu zegar referencji pokazał **−1,731 s**. To nie był błąd zegara, tylko **normalne opóźnienie przesyłu notowań**. Każda próbka `source − received` to przesunięcie zegara **minus** opóźnienie transportu, a opóźnienie nigdy nie jest ujemne — więc mediana jest systematycznie zaniżona. Skutek byłby cichy i szkodliwy: korekta −1,73 s rozciągnęłaby próg starości referencji z 5 s na **6,7 s**, czyli bot handlowałby na starszych notowaniach, niż na to pozwala reguła.

Poprawka w estymatorze:

1. **Zamiast mediany bierzemy wysoką próbkę (90. percentyl).** Próbka o najmniejszym opóźnieniu jest najbliżej prawdy — tak samo działa NTP. Percentyl, a nie czyste maksimum, żeby jeden fałszywy znacznik z przyszłości nie przesunął całej oceny.
2. **Korekta nigdy nie jest ujemna.** Poprawiamy tylko w jedną stronę: „lokalny zegar się spóźnia". Dzięki temu **nie da się sprawić, żeby naprawdę stare dane wyglądały na świeże** — a to jedyny groźny kierunek. Zegar idący do przodu sprawia, że dane wyglądają starzej i bot wstrzymuje handel; to jest kierunek, w którym chcemy się mylić.

Po tej zmianie zegar referencji raportuje `0.0` przy 15 próbkach, czyli opóźnienie transportu nie jest już brane za błąd zegara.

## Automatyczna kontrola, żeby to się nie powtórzyło

Dryf zegara był niewidoczny — worker wyglądał na zdrowy, a od 50 minut nic nie kopiował. Teraz jest mierzony i wystawiany sam z siebie:

- **Worker publikuje `clock_skew` w swoim stanie przy każdym cyklu**, osobno dla książek i dla referencji, razem z liczbą próbek. Trafia to do stanu, który i tak czytasz.
- **Godzinny raport ma nowe pole `alerts`.** `clock_alerts()` zgłasza `CLOCK_SKEW` z gotową komendą naprawczą, gdy przesunięcie przekroczy **0,5 s**. Przy zdrowym zegarze lista jest pusta.

To działa 24/7, niezależnie od tego, czy Cursor jest otwarty.

## Co się okazało wieczorem: to nie jest dryf, to skok

Damian włączył synchronizację sieciową i dostał „Network Time is already on". Przełącznik był włączony cały czas. `timed` sam cofnął zegar o 2,34 s o 19:29, zanim Damian wpisał hasło. O 19:42 pomiar był **+0,012 s**.

Mój wcześniejszy opis „0,8 s dryfu na godzinę" był zły. Kryształ jest w porządku. Log `timed` z dzisiaj pokazuje dwa skoki w tył o około 2,3 s (14:53 i 18:59) i powrót do prawdy przy następnym cyklu, czyli po około pół godzinie. Między skokami korekty są poniżej 0,15 s. O 18:59 próbka z `17.253.38.43` rozjechała się z własną prognozą `timed` o 2,32 s, usługa wyrzuciła model i przestawiła zegar. Równolegle `17.253.38.35` regularnie zwraca pustą odpowiedź (znacznik zerowy, opóźnienie rzędu setek milionów sekund).

Skutek dla kopiowania: przez te pół godziny książki znowu wyglądają na przyszłe. `VenueClock` to wytrzymuje, dopóki skok jest rzędu sekund, nie minut.

## Strażnik zegara

`deploy/clock_guard.py` co 3 minuty mierzy `time.apple.com` dwa razy. Przestawia zegar tylko wtedy, gdy obie próbki zgadzają się co do 0,1 s, niepewność jest poniżej 0,05 s, a przesunięcie przekracza 0,3 s. Rozjechany albo rozmyty odczyt zostawia w spokoju — przestawianie na jednej złej próbce jest dokładnie błędem, który popełnia `timed`. Instalacja wymaga jednego `sudo`, bo przestawienie zegara na macOS może zrobić tylko root. Skrypt jest już w `Application Support/BTC Lab/clock_guard.py`; usługa wstanie po:

```
sudo bash /Users/damianbiniarz/Projects/copy-lab-ops/btc-lab/deploy/install-clock-guard.sh
```

## Rzecz, którą musisz zrobić Ty, nie ja

**Zegar w tej chwili jest dobry: +0,012 s.** Synchronizacja sieciowa była włączona, zanim Damian to sprawdzał, i samo jej włączenie nic nie zmienia. Zostaje jedno polecenie, które stawia strażnika na stałe — bez niego następny skok o 2,3 s znowu poleży pół godziny:

```
sudo bash /Users/damianbiniarz/Projects/copy-lab-ops/btc-lab/deploy/install-clock-guard.sh
```

Drugi skutek tego przesunięcia: wcześniejsze liczby, które podawałem dla ścieżki REST i dla `copy_delay`, porównywały czas giełdy z naszym spóźnionym zegarem, więc były **zaniżone o około 2 sekundy**. Realne opóźnienia były o te 2 s gorsze, niż raportowałem. Nowe liczby z łańcucha (0,56 s, 1,33 s) tego nie dotyczą — one mierzą czas wyłącznie naszym własnym zegarem, od momentu odbioru zdarzenia do złożenia kopii, więc przesunięcie się skraca.

## Changelog

- `lab/core.py` — nowa klasa `VenueClock`: `observe()`, `skew()` (90. percentyl z 15 próbek, obcięty do `[0, 30]` s), `age(source, received)`.
- `lab/worker.py` — `normalize_book(raw, token, now, max_age=8, venue_clock=None)` liczy wiek w czasie giełdy; osobne `book_clock` i `reference_clock`; `accept_reference()` próbkuje zegar notowań; sześć kontrol świeżości przestawione na `age()` (wyjście, cechy, `books_fresh`, walidacja wejścia, status); nowa metoda `clock_skew()` publikowana we wszystkich trzech zapisach stanu workera.
- `lab/wallet_copy.py` — `book_clock` zamiast `venue_clock`; `DECISION_STALE_OR_EMPTY` i `ARRIVAL_INVALID` liczą wiek w czasie giełdy; nowa pętla `upkeep()` przejmuje rozliczanie i przegląd pominięć, `run()` ją uruchamia i sprząta w `finally`.
- `deploy/publish_report_macos.py` — nowe `clock_alerts()` i próg `CLOCK_WARN=0.5`; `clock_skew` dołożone do wycinka stanu workera; nowe pole `alerts` w raporcie.
- `tests/test_lab.py` — `test_fresh_book_accepted_when_local_clock_trails_the_venue`, `test_venue_age_compensates_a_late_local_clock`, `test_transport_delay_never_shrinks_the_measured_age`, `test_one_bogus_future_stamp_does_not_move_the_estimate`, `test_absurd_future_book_still_rejected`, `test_clock_skew_is_published_so_drift_is_visible`.
- `tests/test_reporting.py` — `test_clock_drift_is_raised_as_an_alert`, `test_healthy_clock_raises_no_alert`.
- `tests/test_wallet_copy.py` — `test_settlement_runs_beside_copy_not_inside_it`.
- Wgrane do `releases/b009e2b8b429-1790926011187411000/btc-lab/` oraz `reporting/publish_report_macos.py`; `com.btc-lab.paper` zrestartowana.
- `deploy/clock_guard.py`, `deploy/com.btc-lab.clock.plist`, `deploy/install-clock-guard.sh` — strażnik co 3 minuty, krok tylko przy dwóch zgodnych próbkach i przesunięciu ponad 0,3 s. Skrypt skopiowany do Application Support. Usługa launchd wstaje po jednym `sudo` Damiana.
- `tests/test_clock_guard.py` — parse, krok, zdrowy zegar, rozjechana i rozmyta próbka, ostrzeżenie dopisane za pomiarem.
- Pierwsze uruchomienie roota (19:47) padło: `sntp` jako root dopisuje ostrzeżenie za linią z pomiarem, a parser brał ostatnią linię. Parser szuka teraz linii z `+/-`. Następny cykl roota, 19:50:56, wyszedł z kodem 0 i zapisał `ok +0.013s`.

## Znane ryzyko, którego celowo nie ruszałem

`wallet_copy.py` linia 269 sprawdza wiek transakcji obserwowanego portfela warunkiem `0<=now-row['source_ts']<=90`. Dla ścieżki z łańcucha `source_ts` pochodzi z naszego zegara, więc jest spójny. Dla ścieżki REST to znacznik z Data API, czyli czas obcy — przy spóźnionym zegarze dolna granica `0<=` mogła odrzucać świeże transakcje jako `SOURCE_TOO_OLD`. Nie zmieniałem tego razem z resztą, bo to modyfikuje regułę dopuszczania transakcji do kopiowania, a nie samą kontrolę świeżości danych rynkowych. Do decyzji osobno.

## Następna decyzja

Zostają trzy rzeczy, w tej kolejności ważności:

1. **Wpłać $10 na polymarket.com** z adresu EOA `…36a3bF01`. Dopóki tego nie ma, realne zlecenia odbijają się o „maker address not allowed, please use the deposit wallet flow" i cała prędkość jest tylko na papierze. Po wpłacie trzeba podpiąć adres funderu i `signature_type=3`.
2. **Rynki godzinowe** `bitcoin-up-or-down-…-<h>am-et` — 898 z 3069 transakcji obserwowanych portfeli w 3 godziny leci w rynki, których kopiarka w ogóle nie obsługuje.
3. **Papierowy wynik kopiowania to −$98,10 zamknięte.** Prędkość jest naprawiona, ale sam dobór portfeli nadal traci. Zanim cokolwiek pójdzie na żywo, te portfele muszą przejść sito 60d+90d.
