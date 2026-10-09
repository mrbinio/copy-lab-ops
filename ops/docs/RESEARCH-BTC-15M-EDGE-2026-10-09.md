# BTC 15m — gdzie jest przewaga? (badanie 9.10.2026)

Dane z bazy labu: 30.09–9.10, 1541 oficjalnych wyników, 452 tys. punktów Chainlink (spot i TWAP60), 137 tys. zrzutów arkusza (co ~25 s na stronę), 6005 transakcji portfeli Mitcha na BTC 15m. Skrypty: tymczasowe (scratchpad), logika opisana niżej.

## 1. Portfele Mitcha

- Same kupna trzymane do rozliczenia (2665 z oficjalnym wynikiem): **ROI −0,4%** (−127 USD na 36 079 USD).
- Z ich sprzedażami, na oknach z wynikiem: **+696 USD na 213 oknach**. ROI dla 9f672c31 i dc27 tylko 1,1% i 1,5%; 096b159 +267 USD na 12 oknach (mała próba). mihaXd −100 USD.
- Wzorzec (kupna, bez korekty na korelację w oknie): zarabiają na tanich biletach (<0,30) strony przegrywającej, gdy spot w ostatnich 30 s szedł w jej stronę, w 11.–13. minucie. Tracą po 0,50–0,70 i wbrew ruchowi z ostatnich 30 s (−79%).
- Handlują BTC 15m głównie **23:00–04:00 Stockholm**.

Wniosek: przewaga źródła jest mała (1–2%), więc kopia z jakimkolwiek poślizgiem łatwo ją traci.

## 2. Własny model „TWAP-lag”

P(strona wygrywa) z ruchu Browna: oczekiwany TWAP60 na końcu (znana część średniej + obecny spot), wariancja `σ²·((r−60)+60/3)` dla r ≥ 60 s, `σ²·(r/60)²·r/3` dla r < 60 s, σ z 15 min zwrotów spot. Wejście: model − VWAP $5 (50% głębokości) − opłata taker `0,07·p·(1−p)` > zapas. Jeden bilet $5 na okno i stronę, trzymany do rozliczenia. Podział w czasie: połowa A do strojenia, połowa B niewidziana.

| | Brier |
|---|---|
| model TWAP-lag | 0,1479 |
| model naiwny (obecny TWAP jako końcowy) | 0,1539 |
| **ask w arkuszu** | **0,1434** |

- 6 najlepszych reguł z A (+19 do +52 USD) na B: **wszystkie ujemne** (−77 do −143 USD, t do −3,3).
- Reguła ustalona z góry (zapas 0,05, 600–885 s): A −25,5 USD (n=120), B −9,4 USD (n=217).

Wniosek: przy rozdzielczości 25 s i opłacie taker rynek jest skalibrowany lepiej niż ten model. Brak przewagi. Nie uruchamiać.

Wcześniej w labie (nie powtarzać): complete-set (Up+Down < 1) → `INSUFFICIENT_DEPTH`, netto ujemne; early/late/mid-window/value → straty po opłatach.

## 3. Co zostaje do sprawdzenia (wymaga lepszych danych)

1. **Szybkość (lead-lag):** BTC na Binance rusza się przed Chainlinkiem i przed arkuszem. Reakcja < 1 s na ruch Binance przed aktualizacją arkusza. Zrzuty co 25 s tego nie pokażą — potrzebny zapis strumienia arkusza (delty) i transakcji Binance w ms.
2. **Maker zamiast taker:** opłata jest po stronie biorącego. Zlecenie z limitem po stronie arkusza nie płaci opłaty i zarabia spread, ale ryzykuje, że wypełni się tylko wtedy, gdy rynek idzie przeciw nam. Do oceny potrzebny strumień transakcji (kto w nas uderza i co dzieje się potem).

Oba wymagają tygodnia zapisu danych wysokiej rozdzielczości przed jakimkolwiek handlem PAPER.
