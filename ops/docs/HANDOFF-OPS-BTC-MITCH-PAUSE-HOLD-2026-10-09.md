# Mitch: pauza wróciła po restarcie — 9 października 2026

PAPER. LIVE off. −110,36 nie resetowane.

Watchdog zrestartował papier ~16:57 (heartbeat ~90 s, kolejka kopii 213). Nowy `mitch_stint.at` wyzerował `mitch_pauses`. Trzy czerwone portfele i mihaXd były `paused=false` — wbrew regule „minus = pauza, bez auto-retestu”.

## Co jest teraz

`refresh_pauses` pauzuje przy minusie **okresu, dnia albo od startu** (`all_net < 0`). Zmiana stintu **nie zdejmuje** istniejącej pauzy. mihaXd zostaje na pauzie mimo plusa od startu.

Wgrane do wydania `b009e2b8b429-1790926011187411000`: `mitch_copy.py`. Kickstart po teście `test_mitch_copy` 31 OK.

Po restarcie 17:57: 0x9f672c31, 0xdc27, checkr3, mihaXd znowu `paused`. 096b159 bez kopii, bez pauzy. healthz 200, worker RECORDING, LIVE false. Rezerwa 280,43.
