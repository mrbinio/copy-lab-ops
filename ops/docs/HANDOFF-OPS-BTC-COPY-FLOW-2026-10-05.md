# Handoff — stan kopiowania na ekranie, 5 października 2026

## Executive summary

Program odbiera transakcje. Nie kopiuje nowych zakupów, bo jedyny portfel z włączonym kopiowaniem nie ma żadnej transakcji źródła, a portfele, które handlują, są wstrzymane albo tylko obserwowane. Ekran mówi to wprost. Zlecenia na żywo są wyłączone.

## Co się zmieniło i dlaczego

Bilet diagnostyczny wstrzymanego portfela był liczony na ścieżce decyzji. Świeży sygnał przekraczał 90 sekund, zanim kopiarka do niego doszła. Taki bilet zostaje przy pojedynczej decyzji w teście i schodzi z pętli, która obsługuje kolejkę. Filtr 90 sekund zostaje.

27 obserwacji było otwartych po końcu rynku i nie miało wyniku, więc żaden portfel nie mógł przejść kwalifikacji. Rozliczenie oficjalne jest takie samo jak w księdze PAPER, z tym samym czekaniem 300 sekund. Brak oficjalnego wyniku nie staje się zerem.

## Następna decyzja

Kwalifikacja nadal wymaga 20 rozliczonych obserwacji jednego portfela. Samo rozliczenie obecnych pozycji tego progu nie spełnia.
