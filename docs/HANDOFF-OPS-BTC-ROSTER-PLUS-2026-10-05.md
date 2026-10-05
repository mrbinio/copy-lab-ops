# Handoff — kopiuj plus, wyłącz minus, 5 października 2026

## Executive summary

Portfele siedziały w obserwacji i pauzie, bo awans patrzył na krótką, świeżą księgę obserwacji (`copy-observe-v2`, około 8 godzin), a pauza pamiętała jeden czerwony odcinek. Portfele z dodatnim rozliczonym wynikiem nie wchodziły do kopiowania. Odbiór transakcji działał. Decyzja brzmiała `COPY_PAUSED`.

## Co się zmieniło i dlaczego

Kopiowanie włącza się, gdy rozliczona księga jest na plusie. Wyłącza się, gdy cała rozliczona księga kopiowania zejdzie poniżej zera. Jeden czerwony odcinek nie gasi portfela, który w sumie jest dalej na plusie. Brakujący wynik nie jest zerem.

Na danych z Maca, przed restartem:

| Portfel | Było | Rozliczony wynik | Po regule |
| --- | --- | --- | --- |
| `…4096b159` | pauza | kopia +14,52 USD, 82 zamknięcia | kopiowanie |
| `…8a2e7537` | obserwacja | obserwacja +12,59 USD, 6 zamknięć, 6 okien | kopiowanie |
| `…218d69a9` | obserwacja | obserwacja +6,84 USD, 3 zamknięcia, 3 okna | kopiowanie |
| `…dcfcf46e` | kopiowanie | 0 zamknięć | wraca do obserwacji, slot bierze portfel na plusie |
| `…365cf589` | pauza | kopia −37,98 USD | zostaje wyłączony |
| `…207e77c2` | pauza | kopia −36,74 USD | zostaje wyłączony |
| `…3e6eba30` | pauza | kopia −23,79 USD | zostaje wyłączony |
| `…69de3680` | pauza | kopia −16,57 USD | zostaje wyłączony |

Reszta obserwowanych ma ujemną albo pustą księgę obserwacji. Nie dostają kopii, dopóki rozliczony wynik nie wejdzie na plus. Są na liście, bo handlują. Handel bez dodatniego wyniku nie otwiera kopii.

Hasło, port 8769, limity, historia i `clob_live=false` zostają. LIVE zostaje wyłączone. Stare straty nie są kasowane.

## Następna decyzja

Po restarcie te trzy portfele na plusie biorą nowe BUY. SELL i rozliczenie pauzy zostają włączone. Jeśli księga któregoś zejdzie poniżej zera, następny obieg wyłącza mu kolejne BUY.
