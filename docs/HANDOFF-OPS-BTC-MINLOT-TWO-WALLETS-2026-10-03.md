# HANDOFF — Strata $4 i dwa nowe portfele 2026-10-03

## Executive summary

Strata zawsze około **$4–5** to nie przypadek: każdy zakup wydawał cały bilet **$5**. Jak strona przegrywała, znikało prawie całe $5. 208 z 222 przegranych było w przedziale $4,50–$5,20. Najgorzej brały tanie losy: 40 kopii po 0–15 centów dało **−$157** i tylko 2 wygrane.

Od teraz bilet to **jedno minimum rynku** (5 udziałów), nie $5 za każdym razem. Przy 20 centach strata to około **$1**, przy 50 centach około **$2,70**, przy 70 centach około **$3,75**. Dodatkowo nie kopiujemy ceny źródłowej poniżej 20 centów ani powyżej 70 centów.

Dwa nowe portfele weszły na **papier**, nie na żywe pieniądze: `Atomforge` (`…69de3680`) i `honey-spot` (`…dcfcf46e`). Na zamkniętych pozycjach 5m/15m, bilet $2, ceny 20–80 centów, wyszły na plus (**+$83** / 183 i **+$34** / 213). Czwórka z tabeli „TRADES_OUR_MARKETS” przy takim samym teście była na minusie — ich nie wziąłem. Realne pieniądze nadal **$0**. `4096b159` zostaje włączony.

## Co zmieniłem

1. **Bilet = minimum rynku**, nie $5. Dlatego strata nie jest już zawsze czterodolarowa.
2. **Sitko ceny 20–70 centów.** Poniżej 20c: `COPY_PRICE_TOO_LOW`. Powyżej 70c: `COPY_PRICE_TOO_HIGH`. 0–15c zabrało $157; 75c+ zabrało $20 przy małym zysku.
3. **`Atomforge` i `honey-spot` na liście kopii.** Osobne konta papierowe, łańcuch je widzi. Trzech starych przegrywających dalej wstrzymanych.

Zegar −0,04 s. Worker zrestartowany.

## Liczby, które to uzasadniają

| Cena źródłowa | Kopie | Wynik |
| --- | --- | --- |
| 0–15c | 40 (2 wygrane) | **−$156,84** |
| 15–35c | 75 | +$26,48 |
| 35–55c | 146 | +$46,61 |
| 55–75c | 132 | −$3,07 |
| 75c+ | 52 | −$19,60 |

Nowe portfele (symulacja $2, 20–80c, zamknięte 5m/15m, sort TIMESTAMP — są i wygrane, i przegrane):

| Portfel | Wynik symulacji | Transakcje |
| --- | --- | --- |
| Atomforge `69de3680` | +$83 | 183 (117 wygranych) |
| honey-spot `dcfcf46e` | +$34 | 213 (116 wygranych) |
| x-MoneyForWhiskas i reszta tabeli | minus | odrzucone |

To nie jest obietnica. To ten sam test, który na `4096b159` też pokazuje plus, i który na trzech starych kopiach pokazywał minus.

## Changelog

- `lab/wallet_copy.py` — bilet = `min_shares * ask`; sitko 20–70c przed pobraniem książki.
- `lab/wallet_observer.py` — `PAPER_EXTRA` Atomforge + honey-spot; `get_active_wallets` zwraca ziarna + tę dwójkę.
- `lab/strategy_control.py` — `COPY_IDS` obejmuje nową dwójkę (włączone).
- `lab/app.js` — powody `COPY_PRICE_TOO_LOW` / `COPY_PRICE_TOO_HIGH`.
- Testy: sitko ceny, 5 udziałów przy 60c. 208 zielonych.
- Wgrane, `com.btc-lab.paper` zrestartowana.

## Następna decyzja

Żywej wpłaty nie ruszamy. Nowa dwójka ma iść na papierze kilka dni. Jak któraś zacznie zjadać konto tak jak `3e6eba30`, wyłączamy ją tym samym przyciskiem.
