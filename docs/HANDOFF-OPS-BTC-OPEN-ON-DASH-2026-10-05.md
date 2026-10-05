# Handoff — otwarte kopie na dashboardzie, 5 października 2026

## Executive summary

Kopiowanie już szło. Cztery pozycje PAPER były otwarte, a ekran pokazywał tylko zamknięte transakcje. Liczba „Dzisiaj” zostaje przy −0,71 USD, bo te kopie jeszcze nie mają oficjalnego wyniku. Rynek, który się skończył, na Polymarket nadal nie jest zamknięty, więc rozliczenie czeka.

## Co się zmieniło i dlaczego

Skład wyniku z dzisiaj wypisuje otwarte kopie pod zamkniętymi. Nie wchodzą do sumy. Kafelki portfeli, które teraz kopiujemy, są na górze i mają linię „Otwarta kopia”. Dziennik ma te wiersze ze statusem OTWARTA. Brak wyniku nie jest zerem.

Na godzinę wdrożenia otwarte były: `…218d69a9` Up, `…8a2e7537` Up, oraz starsze okno `…8a2e7537` Down i `…218d69a9` Up. `…4096b159` jest w kopiowaniu i nie miał wtedy otwartej pozycji.

Hasło, port 8769, limity, historia i `clob_live=false` zostają. Procesu nie restartowano. Podmieniony jest tylko skrypt strony.

## Następna decyzja

Odświeżyć dashboard. Gdy Polymarket oznaczy okno jako zamknięte, te pozycje wejdą do liczby „Dzisiaj”.
