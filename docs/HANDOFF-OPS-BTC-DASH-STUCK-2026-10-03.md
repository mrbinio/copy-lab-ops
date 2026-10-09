# HANDOFF — Dashboard nie pokazywał nowych portfeli 2026-10-03

## Executive summary

Atomforge i honey-spot **są w silniku** (6 kont kopii). Na stronie ich nie było, bo `/api/state` liczy się **8,3 s**, a przeglądarka zrywała po **7 s**. Odświeżenie padało i zostawał stary widok. Publiczny GitHub Pages nadal ma stary skrypt, który chowa kopię bez transakcji.

## Co zmieniłem

1. Serwer trzyma jeden świeży stan (2 s). Kolejne odczyty nie ustawiają się w kolejkę 8-sekundowych zapytań.
2. Strona czeka 20 s i ładuje `app.js?v=20261003-wallets`, żeby nie brać starego pliku z pamięci.
3. Karty kopii są razem na dole, w tym **Copy Atomforge · PAPER** i **Copy honey-spot · PAPER** przy $0.

## Liczby

| Źródło | Atomforge / honey-spot |
| --- | --- |
| Baza / kopia | tak, 0 transakcji, $0 |
| `/api/state` przed poprawką | często timeout 7 s |
| github.io | stary filtr: zero transakcji = brak karty |

## Changelog

- `lab/server.py` — `dashboard_state()` z blokadą i cache 2 s.
- `lab/app.js` — timeout 20 s; kopie zgrupowane.
- `lab/index.html` — wersja plików, żeby zrzucić cache.

## Następna decyzja

Otwórz **lokalny** dashboard (`127.0.0.1:8769`) i zrób twarde odświeżenie. github.io sam się nie zmieni, dopóki nie wypchniemy strony.
