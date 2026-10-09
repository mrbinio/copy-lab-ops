# BTC Lab — tunel Cloudflare, dwa błędy 1033 — 7 października 2026

PAPER, port 8769, Access, hasło, baza i domena bez zmian. Nowego tunelu nie zakładano. Kopiarki nie restartowano przy tej naprawie.

## Przyczyna

Oba błędy 1033 powstały, gdy Mac spał, a interfejs sieciowy był wyłączony. Proces `cloudflared` nie zakończył się. Działa ten sam pid 54084 od 6 października 2026, 08:23:10. Ostatni kod wyjścia launchd to 11, sprzed tego procesu. Wdrożenia kopiarki tego pid nie ruszyły.

Log tunelu w obu chwilach mówi `sendmsg: network is down` na połączeniach QUIC do Cloudflare, a nie błąd uruchomienia. Znaczniki snu z `pmset` pokrywają się z tymi wpisami co do sekundy.

Ray `a46aa3cb3c6d97e1`, 07:52:27 czasu sztokholmskiego: Mac wszedł w sen o 07:29:41 (Maintenance Sleep, 1630 s) i obudził się o 07:56:51 (XHC1/UserActivity). 07:52:27 jest wewnątrz tego snu. Cztery połączenia tunelu wróciły o 07:57:12. Czas tej przerwy: od 07:29:41 do 07:57:12.

Ray `a46bb15a0cb64a47`, 10:56:28 (08:56:28 UTC): sen od 10:48:18 (861 s) do DarkWake o 11:02:39. Połączenia wróciły o 11:02:40. Kolejny sen 11:03:24–11:05:07, pełna rejestracja o 11:05:21. 10:56:28 jest wewnątrz pierwszego z tych dwóch snów.

To samo `network is down` powtarzało się przy każdym śnie tej nocy (02:49, 04:06, 05:55, 06:16, 07:00, 07:11, 07:14, 07:17, 07:29, 09:13, 10:16, 10:48, 11:03). `caffeinate -i` przywiązany do procesu kopiarki nie utrzymał maszyny: o 02:48:45 ten proces zmarł (`ClientDied`), a o 02:49:01 Mac wszedł w Idle Sleep. Restart kopiarki około 08:43 był w oknie czuwania 07:56–09:13 i nie pokrywa się z żadnym z dwóch Ray ID.

## Wpływ na kopiowanie

W czasie snu CPU stało. W obu przerwach `wallet_copy_events` BTC i `decisions` ETH mają zero wierszy w środku snu. Ostatnie zapisy są w sekundzie wejścia w sen, pierwsze po wybudzeniu w kilka sekund (BTC 07:57:08 i 11:02:41, ETH 07:56:54 i 11:02:39). Oba projekty PAPER wstały same. Nie przetwarzają zdarzeń, gdy Mac śpi.

O 11:02:43 istniejący nadzór kopiarki (`watchdog-attempts.json`) zrestartował PAPER, bo puls zamrożony przez sen wyglądał jak martwy proces. To nie był restart z powodu tunelu jako takiego, ale z powodu tego samego snu. Od tej poprawki nadzór nie restartuje kopiarki przez 180 s po `kern.waketime`. Plik jest czytany co minutę. Procesu kopiarki przy wgrywaniu nie restartowano.

Mitch w tych oknach nie miał nowych zdarzeń. Ostatnie przed drugim snem jest z 08:41:47. Brak wpisu w czasie snu nie jest osobną utratą sygnału Mitcha.

## Co jest włączone

- `com.btc-lab.stay-awake` — `caffeinate -s` pod launchd użytkownika, `KeepAlive`. Trzyma `PreventSystemSleep` niezależnie od sesji terminala i od procesu kopiarki. Pid 93473, asercja widoczna przez całe 15 minut obserwacji.
- `com.btc-lab.tunnel-watch` — co 60 s pyta `https://btc.damianbiniarz.com/healthz` bez podążania za przekierowaniem. Error 1033 albo brak odpowiedzi przy działającej trasie domyślnej to utracony tunel. Restart, dopiero po drugiej takiej próbie, dotyczy wyłącznie `system/com.cloudflare.cloudflared`. Najwyżej 3 razy na 30 minut i nie częściej niż co 10 minut. Przy `network is down` nie restartuje. Nie dotyka `com.btc-lab.paper`.
- Istniejące zadania zostają osobno: `com.cloudflare.cloudflared`, `com.btc-lab.paper`, `com.btc-lab.watchdog`, `com.btc-lab.clock`, `com.btc-lab.reports`. Nie ma drugiego restartu tunelu poza tym nadzorem i własnym `KeepAlive` daemona.

## Dowód po naprawie

Obserwacja 11:12:57–11:28:06 czasu sztokholmskiego, 16 prób co minutę.

- Za każdym razem HTTP 302 z Cloudflare Access, bez 1033.
- Pid tunelu 54084 bez zmiany. Ostatnia rejestracja QUIC 11:05:21, w czasie obserwacji nie było nowego `network is down`.
- Pid kopiarki 92205 bez zmiany.
- `PreventSystemSleep` = 1.
- Lokalny `http://127.0.0.1:8769/healthz` na końcu 200. W oknie 13 razy 200 i 3 odpowiedzi HTTP inne niż 200; proces się nie zmienił. BTC i ETH w stanie `RECORDING`.
- Wejście za logowaniem Access nie zostało sprawdzone. Nie ma tu poświadczeń. Samo 302 nie jest dowodem, że aplikacja za logowaniem odpowiedziała.

## Następna decyzja

Kolejka kopii nadal ma medianę około 25 s na 28 wykonaniach z rana. Tej pracy nie ruszano w tej naprawie, żeby nie restartować kopiarki w trakcie dowodu tunelu.
