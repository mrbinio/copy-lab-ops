# HANDOFF — Nowe portfele na dashboardzie 2026-10-03

## Executive summary

Atomforge i honey-spot już kopiowały na papierze, ale dashboard ich nie pokazywał. Lista kopii chowała portfel bez transakcji, a karty strategii też. Zero transakcji = niewidoczny. To nie był brak kopii. To była dziura w widoku.

Teraz obie karty są na przeglądzie od razu, z nazwami **Copy Atomforge · PAPER** i **Copy honey-spot · PAPER**, przy **0 transakcji** i **$0**. TOTAL się od tego nie zmienia.

## Co zmieniłem

1. Publikacja kont kopii obejmuje całą listę aktywnych, nie tylko stare ziarna albo te z ruchem.
2. Karty strategii nie filtrują już `copy-*` z zerem transakcji.
3. Zakładka Portfele pokazuje nazwę, nie sam adres.

## Changelog

- `lab/wallet_copy.py` — publikuj wszystkie aktywne konta; nazwy Atomforge / honey-spot.
- `lab/wallet_observer.py` — `wallet_label()`.
- `lab/core.py` — etykieta w `wallet_observer`.
- `lab/app.js` — wszystkie karty; nagłówek bez „trzech kont”.
- Test: extras widoczne przed pierwszym ruchem.

## Następna decyzja

Odśwież dashboard (twardy reload). Jeśli karta ma 0 transakcji przez kilka godzin, to źródło nie dało jeszcze sygnału 20–70c na 5m/15m — nie że kopia nie działa.
