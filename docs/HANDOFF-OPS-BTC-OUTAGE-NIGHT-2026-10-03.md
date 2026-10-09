# HANDOFF — Zanik prądu, noc i wczoraj, portfele 2026-10-03

## Executive summary

Lab **sam wstał** po zaniku prądu i internetu. Nic nie trzeba było wgrywać od nowa. Realne pieniądze nadal **$0**. Papierowe kopiowanie jest na **−$92,52** od startu. Wczoraj, 2 października, dzień był zły: kopie otwarte tego dnia dały **−$66,52**. Noc (20:00–08:00) odrobiła **+$29,92**. Dzisiejsze rozliczenia, które zamykają właśnie tamtą noc, stoją na **+$59,90**. Jeden portfel jest na plusie przez cały czas: `4096b159` **+$29,62**. Trzy, które kopiujemy najwięcej, są na minusie.

Zanik trwał od **07:34 do 10:00**. Przez te dwie i pół godziny nie powstała żadna nowa kopia. Trzy pozycje otwarte tuż przed zanikiem wiszą w stanie `RESOLVED` bez wypłaty — lab wrócił, ale ich jeszcze nie domknął. Godzinny raport ostatni raz wyszedł o **06:40**; trzy kolejne godziny wypadły.

Szukanie nowych portfeli **jest napisane i jest wyłączone**. Ostatni skan był 1 października o 14:56. Z tamtego skanu lab trzyma 28 adresów z publicznej tabeli Polymarketu, ale tylko jeden z nich (`3e6eba30`) jest regularnie kopiowany — i ten jeden jest na **−$28,26**.

## Co się stało z prądem

Strażnik zegara zapisał ostatni zdrowy pomiar o **07:34:57** (`−0,001 s`) i następny dopiero o **10:00:08** (`+0,010 s`). Przerwa 8711 sekund. Ostatnia kopia przed zanikiem: **07:34:11**, portfel `3e6eba30`. Pierwsza po powrocie: **09:59:59**, portfel `365cf589`.

Usługa papierowa nie restartowała się w tym oknie — nie ma w logu linii „Starting paper". Proces albo wisiał bez sieci, albo Mac spał. O 09:37 pojawiają się pierwsze timeouty do Polymarketu (prąd wrócił, internet jeszcze nie). O 09:59 łańcuch złapał `drpc`, o 10:01 wrócił na `blockmachine`. Worker o 10:02 jest w `RECORDING`, referencja `FRESH`, zegar `book 0,0 / reference 0,0`, `sntp +0,008 s`. Strażnik zegara od wczoraj wieczora zrobił **237** cykli i poza zanikiem nie miał przerwy dłuższej niż 3 minuty.

Trzy kopie z 07:23, 07:27 i 07:34 (`3e6eba30`, rynki 5m i 15m) są `RESOLVED` bez kwoty. Rynek już się skończył, a lab nie zdążył ich rozliczyć, zanim padł prąd. To nie są straty — to niewypełnione rozliczenie. Trzeba sprawdzić za godzinę, czy pętla `upkeep` je domknęła.

Godzinny raport: ostatni udany o 06:40 (`{"ok": true}`). 07:00, 08:00 i 09:00 nie wyszły. O 10:02 praca raportu znowu leciała.

## Portfele — kto dał, kto zabrał

Kwoty są papierowe. Kopiujemy cztery adresy na poważnie (trzy ziarna i jeden z discovery) plus cztery drobne, które prawie nic nie zrobiły.

### Od startu, zamknięte

| Portfel | Skąd | Wynik | Trafione / zamknięte |
| --- | --- | --- | --- |
| `4096b159` | ziarno | **+$29,62** | 29/46 |
| `3e6eba30` | discovery | **−$28,26** | 117/227 |
| `365cf589` | ziarno | **−$32,98** | 31/69 |
| `207e77c2` | ziarno | **−$33,18** | 29/64 |
| `9b9fa354` | discovery | −$9,77 | 0/2 |
| `cf2104ae` | discovery | −$8,68 | 1/6 |
| `f11764d4` | discovery | −$4,87 | 0/1 |
| `2608ad88` | discovery | −$4,40 | 1/2 |
| **Razem** |  | **−$92,52** |  |

`4096b159` jest jedynym portfelem na plusie i jedynym, którego nie należy ruszać. Dwa pozostałe ziarna i discovery `3e6eba30` zjadły cały ten plus i jeszcze $60.

### Wczoraj, 2 października (kopie otwarte 00:00–24:00)

**−$66,52** na 202 kopiach.

- `365cf589` **−$40,42** (11/25)
- `207e77c2` **−$19,33** (9/18)
- `3e6eba30` **−$15,61** (67/139)
- `4096b159` **+$8,85** (14/20)

Dzień zabrał pieniądze. `365cf589` sam jeden zabrał czterdzieści dolarów.

### Noc, 2.10 20:00 – 3.10 08:00 (kopie otwarte)

**+$29,92** na 248 kopiach.

- `4096b159` **+$25,56** (14/23)
- `3e6eba30` **+$7,37** (73/133)
- `365cf589` **+$2,26** (22/48)
- `207e77c2` **−$5,28** (18/41)

Noc była dobra, prawie cała zasługa `4096b159`.

### Dzisiejsze rozliczenia (zamknięte od 00:00)

**+$59,90** na 180 rozliczeniach. To w dużej części zamykanie nocnych pozycji, nie nowa sesja dzienna.

- `365cf589` **+$32,51** (18/36)
- `4096b159` **+$18,06** (11/20)
- `3e6eba30` **+$5,43** (49/88)
- `207e77c2` **+$3,89** (16/36)

Tu widać, dlaczego nie wolno patrzeć tylko na „otwarte dzisiaj": `3e6eba30` na kopiach otwartych dziś rano jest na **−$17,76`, a na rozliczeniach na **+$5,43**, bo poranne zamknięcia to wczorajsza noc.

## Prędkość

Wczoraj mediana opóźnienia kopii **1,07 s**, 97 z 202 poniżej sekundy. Noc: mediana **0,89 s**, 153 z 248 poniżej sekundy. Dziś do 10:02: mediana **0,89 s**, 112 z 180 poniżej sekundy. Ścieżka z łańcucha trzyma się. Po powrocie z zaniku pierwsze trzy kopie poszły wolniej (5,5 / 3,1 / 15,4 s) — to rozgrzewka po braku sieci, nie nowy problem.

## Strategie papierowe (nie kopia)

Od startu: `early-v1` **+$1,87**, `mid-window-v2` **−$6,89**, `late-v1` **−$18,51**, `mid-window-v1` **−$18,75**. Wczoraj te strategie otworzyły mało i źle: `mid-window-v1` **−$12,17** na 3 wejściach, `early-v1` **−$3,26** na 13. Value-surface: **−$4,75**, 0 z 5, status `PAUSED_OR_RECONCILIATION_BLOCK`.

## Szukanie nowych portfeli

Kod jest: `lab/wallet_discovery.py` co godzinę czyta publiczną tabelę CRYPTO Polymarketu (top 50 tydzień i miesiąc) i zostawia przecięcie tych, którzy na obu listach mają dodatni wynik i obrót tygodniowy powyżej 1000. W `worker.py` linia 504 to jest **wyłączone** komentarzem „too many unverified wallets. Seed wallets only."

Ostatni skan: **1 października 14:56**, status `SCAN_OK`, 28 kandydatów. Wtedy lab wpisał ich do `active_wallets` jako `discovery`. Od tego czasu nikt ich nie odświeża. 23 z 31 aktywnych adresów nie ma ani jednej udanej kopii — obserwator je widzi za późno (`SOURCE_TOO_OLD` tysiącami). Jeden discovery, którego naprawdę kopiujemy, `3e6eba30`, jest na minusie. Publiczna tabela „zysków" i nasz wynik z kopiowania to dwie różne rzeczy; sam plik eksperymentu to mówi.

Nie włączam tego z powrotem w tym raporcie. Gdyby szukać dalej, skan powinien tylko pokazywać kandydatów, a nie wpisywać ich do kopiowania. Wejście na listę kopii zostaje za sitem 60d+90d, dywersyfikacją i CopyGrade. Starej „Top 8" nie odzyskujemy.

## Liczby

| Pozycja | Wartość |
| --- | --- |
| Realne wydane | $0 |
| Kopia zamknięta od startu | −$92,52 |
| Wczoraj otwarte kopie | −$66,52 / 202 |
| Noc otwarte kopie | +$29,92 / 248 |
| Dziś rozliczone | +$59,90 / 180 |
| Jedyny portfel na plusie | `4096b159` +$29,62 |
| Zanik | 07:34–10:00, 2 h 25 min |
| Raport | ostatni 06:40, trzy godziny wypadły |
| Discovery | wyłączone, skan sprzed 43 h, 28 martwych kandydatów |
| Zegar teraz | +0,008 s |
| Worker | `RECORDING`, 10:02 |

## Changelog

Nic nie wgrywałem. To przegląd po zaniku, nie zmiana kodu.

## Następna decyzja

1. **Poczekaj godzinę i sprawdź trzy pozycje `RESOLVED`.** Jeśli nadal nie mają kwoty, trzeba je rozliczyć ręcznie albo poprawić `upkeep`.
2. **Nie włączaj discovery z powrotem w obecnym kształcie.** 28 adresów z tabeli i jeden kopiowany na minusie to nie jest sito.
3. **Pieniądze realne zostają na boku**, tak jak uzgodniliśmy. Wczorajszy dzień (−$66,52) i jeden dodatni portfel na cztery kopiowane to nie jest stabilizacja.
4. Jeśli chcesz szukać nowych, następny krok to skan tylko do odczytu plus osobna decyzja, kogo w ogóle wpuścić do papieru — nie auto-wpis na listę kopii.
