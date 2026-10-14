# Dane wysokiej rozdzielczości — czy jest przewaga? (14.10.2026)

Dane z rejestratora (`data/hires/`, 9.10 wieczór – 14.10 rano): Binance BTCUSDT bookTicker, arkusz Polymarket BTC Up/Down 5m i 15m (zmiany najlepszej oferty kupna i sprzedaży), transakcje Polymarket (`last_trade_price`). Około 2,8 mln zmian arkusza i 2,3 mln transakcji. Skrypt: tymczasowy (scratchpad), logika opisana niżej. Każdy dzień liczony osobno; parametry wybierane na 10–11.10, oceniane na 12–14.10.

## 1. Czy Binance wyprzedza arkusz Polymarket?

Korelacja zmian w siatce 1 s (zmiana BTC na Binance w sekundzie t, zmiana środka arkusza Up w sekundzie t+L):

| | L = 0 | L = +1 s | L = +2 s | L ≤ −1 s |
|---|---|---|---|---|
| BTC 15m | 0,25–0,40 | 0,11–0,14 | 0,02–0,07 | ~0 |
| BTC 5m | 0,21–0,33 | 0,09–0,15 | 0,02–0,08 | ~0 |

Binance wyprzedza arkusz, ale tylko o ułamek sekundy do około 1 s. Po 2 s nie ma już nic.

### Reguła taker

Jeśli BTC na Binance ruszy w ciągu 1 s o więcej niż 3 (albo 5) punktów bazowych, kupujemy stronę, którą wskazuje ruch, po cenie ask. Po H sekundach sprzedajemy po bid. Opłata taker `0,07·p·(1−p)` liczona przy wejściu i przy wyjściu. Tylko arkusze ze środkiem 0,15–0,85. D to opóźnienie od ruchu Binance do naszego zlecenia.

Średni wynik na 1 USD stawki, BTC 5m, próg 3 bp, H = 10 s (liczba transakcji w nawiasie):

| Dzień | D = 0 | D = 0,5 s | D = 1 s |
|---|---|---|---|
| 10.10 (strojenie) | +63% (13) | +22% (9) | +19% (9) |
| 11.10 (strojenie) | +19% (24) | +22% (25) | +18% (22) |
| 12.10 (test) | +16% (87) | +11% (89) | +9% (88) |
| 13.10 (test) | +7% (99) | +4% (95), mediana −4% | −0,5% (96) |
| 14.10 (test, pół dnia) | +2% (55) | −11% (52) | −12% (52) |

BTC 15m wygląda podobnie, ale słabiej: przy D = 0,5 s wynik jest ujemny w 3 z 5 dni.

**Wniosek:**
- Wynik przy D = 0 to teoria. Nikt nie złoży zlecenia w tej samej chwili, w której zobaczy ruch Binance.
- Realne opóźnienie to: odbiór ruchu z Binance, wysłanie zlecenia na Polymarket i jego dopasowanie. To około 0,3–0,6 s.
- Przy 0,5–1 s przewaga maleje z dnia na dzień i w ostatnich dniach znika (13–14.10).
- Mediany są często ujemne, czyli średnią ciągnie kilka dużych wygranych.
- Próby są małe: 50–100 transakcji dziennie.
- Nie znamy wielkości ofert na najlepszej cenie, więc nawet dodatni wynik dotyczyłby tylko bardzo małych kwot.

**Przewaga nie jest odporna. Nie uruchamiać.**

## 2. Zlecenie oczekujące (maker) przy najlepszej cenie

Bierzemy każdą rzeczywistą transakcję przy cenach 0,10–0,90 i liczymy, ile zarobiłby maker po drugiej stronie. Opłata maker wynosi 0. Wynik to średnia zmiana środka arkusza po 5, 30 i 60 s względem ceny wykonania, na 1 USD.

| Dzień | po 5 s | po 30 s | po 60 s | transakcji |
|---|---|---|---|---|
| 09.10 | −0,0% | −1,9% | −3,9% | 90 tys. |
| 10.10 | −0,6% | −1,1% | −2,8% | 350 tys. |
| 11.10 | −0,3% | −0,7% | −0,9% | 350 tys. |
| 12.10 | −0,1% | −0,4% | −0,5% | 397 tys. |
| 13.10 | −0,4% | −0,2% | −0,5% | 406 tys. |
| 14.10 | −1,0% | −1,5% | −1,6% | 185 tys. |

Każdego dnia i dla każdego horyzontu wynik jest ujemny. Maker dostaje wykonanie głównie wtedy, gdy cena zaraz pójdzie przeciw niemu (negatywna selekcja). Brak opłaty i zarobiony spread tego nie pokrywają. Liczenie jest do tego optymistyczne, bo zakłada, że dostajemy każde wykonanie, choć w kolejce do tej samej ceny stoją przed nami inni.

**Przewaga nie istnieje. Nie uruchamiać.**

## Rekomendacja

Nie zmieniamy handlu. Żadna z dwóch idei nie daje przewagi, która przetrwałaby realne opóźnienie.

Jeśli wrócimy do tematu:
- zmierzyć nasze rzeczywiste opóźnienie zlecenia na Polymarket;
- powtórzyć test reguły taker z dokładnie tym opóźnieniem na kolejnych 2 tygodniach danych, z rozdzielczością 100 ms i wielkością ofert na najlepszej cenie.

Rejestrator działa dalej (limit 14 dni / 10 GB).
