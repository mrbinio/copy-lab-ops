# Mitch: stop strat, łańcuch poniżej 1 s — 8 października 2026

PAPER. `clob_live` zostaje false. LIVE u Mitcha nie włączałem. Strat −202 nie resetowałem. Limitów okna ($20 / $5 mihaXd, 10 centów, tylko BTC 15 min) nie ruszałem.

Jego +322 to jego księga. Nasza kopia 8–80 s po jego cenie, z listy publicznej, po gorszym asku, robiła odwrotność tej krawędzi. Rezerwa 40% liczyła się, ale przy $430–500 gotówki okno $20 nadal strzelało.

## Co jest teraz

1. **Nowy BUY tylko z łańcucha i poniżej 1 s.** Źródło musi być `order_filled` (paragon) albo `market_trade` (print dopasowany do transferu). Lista publiczna i cytat arkusza (`chain_fast`, `chain_accelerated`, `source_second`) dostają `MITCH_NEED_CHAIN` i nie kupują. Wiek > 1,0 s to `LATE_BUY_NOT_COPIED`. `chain_fast` grzeje arkusz najwyżej 1 s, potem skip. Czekanie na arkusz przy BUY też 1 s.

2. **Cena z łańcucha.** Paragon `OrderFilled` bez dodatkowego `eth_getBlockByNumber`. Dla pięciu portfeli Mitcha retry paragonu co 50 ms, deadline 0,85 s. Publiczna lista nie jest już ceną zakupu.

3. **Pauza na minusie, bez automatycznego powrotu.** Ujemny zamknięty wynik dziś albo od startu wstrzymuje BUY/ADD. SELL i rozliczenie zostają. Pauza nie schodzi sama po plusie. Przy starcie procesu pauzują portfele, które już są na minusie (365cf589, 207e77c2, checkr3, mihaXd). 096b159 zostaje — zero kopii.

4. **Rezerwa 40%** zostaje na nowych plusach. To pauza i bramka 1 s zatrzymują recykling okien $20, nie sama rezerwa.

5. **Dziennik na zakładce Mitch.** Tabela transakcji jest zawsze widoczna. Ekran nie przebudowuje DOM co 2 s, gdy liczby się nie zmieniły.

## Rewizja

Git nadal `e001caf`. Do działającego wydania `b009e2b8b429-1790926011187411000` wgrane: `mitch_copy.py`, `wallet_chain_monitor.py`, `order_fill.py`, `lab/app.js`, `lab/index.html`, `lab/style.css` (cache `20261008-mitch-stop`). Papier pid 26516, `/healthz` 200, worker `RECORDING`, `clob_live` false.

Księga po wdrożeniu, 8 października ~07:06 Sztokholm: dziś **−202,446345**, od startu **−110,363881**, 0 otwartych. Pauza: 365cf589, 207e77c2, checkr3, mihaXd. 096b159 bez pauzy (0 kopii). Dziennik: 40 zamknięć na zakładce. Od restartu 0 nowych `MITCH_BUY` / `MITCH_ADD`.

Testy: `test_mitch_copy` 27, `test_chain_monitor` 24, `test_order_fill` 4.

Cel poniżej 1 s jest regułą wejścia: spóźniony sygnał nie wchodzi w księgę. Nowe `MITCH_BUY` pojawi się tylko przy paragonie albo dopasowanym princie wewnątrz sekundy. Stare −202 zostaje w historii.

Zalogowanej karty 8769 nie otworzyłem (401 bez hasła). Pliki w wydaniu mają tabelę `#mitch-trades` i cache `20261008-mitch-stop`. Twardy refresh na http://127.0.0.1:8769/#mitch.

LIVE wyłączone.

## Pulpit 8 października 2026, 07:15 Europe/Stockholm

Ekran „brak danych” i skok do góry: proces stał (heartbeat > 45 s), `/api/state` nie wracał, a `render()` co 2 s przebudowywał cały DOM. Poprawka: pomijam przebudowę gdy liczby się nie zmieniły, trzymam scroll, `overflow-anchor: none`, `translate="no"` (nakładka tłumacza), snapshot nie blokuje się na `wallet_activity`. Widoczny portfel **Rezerwa zysku** (40% nowych plusów, PAPER, nie LIVE). Cache `20261008-dash-bank`.

## Audyt 8 października 2026, 07:07 Europe/Stockholm

Pid 26516, `/healthz` 200. Pauza trzyma cztery czerwone portfele. Od wdrożenia 0 nowych zakupów. Arkusz pulpitu STALE — procesu nie ruszam. LIVE wyłączone.
