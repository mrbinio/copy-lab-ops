# Handoff — pozycja źródła i kwalifikacja v2, 5 października 2026

## Executive summary

Pierwszy wykryty BUY nie otwiera już znanej pozycji od zera. Proporcja sprzedaży jest znana dopiero po odczycie stanu z konkretnym czasem. Wyniki `copy-observe-v1` zostają w księdze i nadal się rozliczają, ale nie awansują portfela, dopóki `copy-observe-v2` nie ma własnych wyników. Zlecenia na żywo są wyłączone.

## Co się zmieniło i dlaczego

Założenie zera przy pierwszym BUY dawało sprzedaż 50% tam, gdzie wcześniejszy stan 100 udziałów oznacza 25%. Bez takiego odczytu wynik jest nieznany. Luka w kolejności zdarzeń też zostawia proporcję nieznaną. Rozliczenie oficjalne pozycji PAPER nie zależy od tej flagi.

`observation_settled` brało obie wersje obserwacji do awansu i powrotu. Logika wykonania się zmieniła, więc kwalifikacja liczy tylko bieżącą wersję. `started_at` się nie przesuwa i stare sygnały nie wracają jako nowe zakupy.

## Następna decyzja

Potwierdzona pozycja źródła pojawi się dopiero po wiarygodnym odczycie z czasem. Sam ruch na taśmie jej nie tworzy.
