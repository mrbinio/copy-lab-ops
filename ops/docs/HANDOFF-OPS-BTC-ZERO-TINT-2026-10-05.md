# Handoff — kolor zera na kafelku, 5 października 2026

## Executive summary

Portfel w kopiowaniu z wynikiem zero był taki sam jak portfel, który tylko obserwujemy. Plus zostaje zielony, minus czerwony. Zero w kopiowaniu ma teraz delikatny niebieski nalot.

## Co się zmieniło i dlaczego

Kafel dostaje klasę `flat` tylko gdy stan to kopiowanie i znany wynik okresu jest dokładnie zero. Brak wyniku nie jest zerem i zostaje bez tego koloru. Podmienione są `lab/app.js` i `lab/style.css`. Procesu nie restartowano.

Hasło, port 8769, limity i `clob_live=false` zostają.

## Następna decyzja

Odświeżyć dashboard. `…8a2e7537` i `…218d69a9` przy zerze zamkniętych kopii powinny mieć ten nalot. Gdy wynik zejdzie na plus albo na minus, kolor przechodzi na zieleń albo czerwień.
