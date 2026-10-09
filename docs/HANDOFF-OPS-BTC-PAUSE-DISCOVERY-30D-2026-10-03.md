# HANDOFF — Trzy portfele wstrzymane, sito 30 dni, szukanie z powrotem 2026-10-03

## Executive summary

Realne pieniądze nadal **$0**. Papierowe kopiowanie zostaje na minusie, ale od 10:18 nowe zakłady idą tylko z **`4096b159`**, jedynego portfela na plusie (**+$30,92**). Trzech przegrywających (`365cf589` −$37,98, `207e77c2` −$33,18, `3e6eba30` −$37,78) ma wyłączone nowe wejścia; otwarte pozycje się rozliczają. 27 martwych adresów zeszło z listy. Szukanie kandydatów znowu chodzi co godzinę, **nikogo nie wpisuje do kopii**. Sito żywej wpłaty i papierowego awansu jest **30 dni na naszych rynkach 5m/15m**, nie 60+90. Zegar **+0,003 s**, strażnik żyje.

## Co zmieniłem

1. **Wstrzymane nowe kopie** `365cf589`, `207e77c2`, `3e6eba30`. `4096b159` zostaje. To jest w `DEFAULT_PAUSED` i zapisane na żywej bazie. Pierwsze decyzje po restarcie: `COPY_PAUSED` na `3e6eba30`.
2. **Tabela `active_wallets` ma tylko cztery ziarna.** 27 wierszy `discovery` skasowane. Kopiarka i tak czytała tylko ziarna; teraz tabela nie kłamie.
3. **Szukanie z powrotem w workerze.** Co godzinę czyta 30-dniową tablicę CRYPTO, potem dla ósemki z największym miesiącem sprawdza, ile ich transakcji z 30 dni to BTC/ETH 5m/15m. Kandydat z udziałem poniżej 25% albo poniżej 10 takich transakcji dostaje `WRONG_MARKETS`. Nikt nie jest automatycznie kopiowany — `promote()` jest puste.
4. **Sito 30 dni zamiast 60+90.** Publiczny miesiąc to tylko pierwsze sito. Na nasze rynki i na żywą wpłatę trzeba 30 dni *naszego* papieru na 5m/15m. 60+90 było za ciasne i odrzucało wszystkich, zanim ktokolwiek wszedł do labu.
5. **Zegar w stanie kopii.** `wallet_copy_execution.clock_skew` jest publikowany przy każdym cyklu. Strażnik: 242 cykle, ostatni `ok +0,004 s`.

Pierwszy skan po włączeniu, 10:17: 20 nazw z miesiąca, 8 zbadanych, **4 handlują naszymi rynkami**, 4 handlują czym innym. Ci czterej zostają na liście i **nie są kopiowani**.

## Liczby

| Pozycja | Wartość |
| --- | --- |
| Realne wydane | $0 |
| `4096b159` (jedyny włączony) | +$30,92 / 47 transakcji |
| `365cf589` wstrzymany | −$37,98 |
| `207e77c2` wstrzymany | −$33,18 |
| `3e6eba30` wstrzymany | −$37,78, powód `COPY_PAUSED` |
| Discovery | `SCAN_OK`, 30 dni, `copy_enabled=False`, 4× `TRADES_OUR_MARKETS` |
| Zegar | +0,003 s; worker `book 0,0` / `reference 0,0` |
| Testy | 206, wszystkie zielone |

Czterech, którzy naprawdę grają 5m/15m (nie kopiowani): `8a2e7537` (1456 naszych transakcji, udział 100%), `9b9fa354` (1284, 88%). Dwoje kolejnych jest w tej czwórce na skanie. Publiczny miesiąc `89647072` to +$555k i **zero** transakcji na naszych rynkach — dokładnie dlatego sito 30 dni na 5m/15m, a nie sama tabela.

## Changelog

- `lab/strategy_control.py` — trzy przegrywające kopie w `DEFAULT_PAUSED`.
- `lab/wallet_discovery.py` — skan 30-dniowy, sonda 5m/15m, puste `promote()`, `prune_discovery_rows()`.
- `lab/wallet_observer.py` — ziarna zawsze `source=seed`.
- `lab/worker.py` — `WalletDiscovery.run()` znowu wystartowany na BTC.
- `lab/wallet_copy.py` — `clock_skew` w publikowanym stanie.
- `lab/app.js` — tekst i wiersze kandydatów: miesiąc, nasze transakcje, udział, status.
- `tests/test_strategy_control.py`, `test_wallet_visibility.py`, `test_wallet_copy.py`.
- Wgrane do `releases/b009e2b8b429-…`, pauzy zapisane na żywej bazie, `com.btc-lab.paper` zrestartowana, pid 92283.

## Następna decyzja

Czwórka `TRADES_OUR_MARKETS` może iść na **papierową obserwację** (osobne konto, bez żywych zleceń) dopiero gdy powiesz. Nie wciągam ich sam. Żywa wpłata nadal czeka na 30 dni plusowego papieru `4096b159` na tych rynkach, nie na tabelę Polymarketu.
