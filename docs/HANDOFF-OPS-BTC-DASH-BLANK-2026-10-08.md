# Pulpit 8769 — puste kafelki — 8 października 2026

PAPER. `clob_live` false. LIVE u Mitcha nie włączałem. Strat −202 nie resetowałem. Ekran na `http://127.0.0.1:8769` pokazuje liczby, nie „brak danych”.

## Co psuło ekran

1. **Skrypt padał przy starcie.** `translate()` woła `render()` → `renderMitch()`, a `let lastMitchSig` było dopiero niżej w pliku. Przeglądarka rzucała `Cannot access 'lastMitchSig' before initialization`. `refresh()` i `setInterval` nigdy nie startowały. HTML zostawał z domyślnym „brak danych” i paskiem AWARIA.

2. **Proxy Cursora** czasem wysyła absolutny URL (`http://127.0.0.1:8769/`) zamiast `/`. Stary test ścieżki nie uznawał tego za localhost i oddawał 401. Lokalny GET `/`, `/app.js`, `/style.css`, `/api/state` jest dozwolony także w tej formie. Po zalogowaniu jest ciasteczko sesji, żeby `fetch` na zdalnym hoście nie gubił Basic.

3. **Nakładka tłumacza** w Chrome/Cursorze skleja polski z innym językiem. `translate="no"`, `notranslate`, meta Google. Tłumacz strony trzeba wyłączyć na tej karcie — liczby i tak są poprawne.

## Weryfikacja 8 października 2026, 07:36 Europe/Stockholm

Twardy reload `app.js?v=20261008-dash-fix` na `http://127.0.0.1:8769/#wynik` i `#mitch`.

| Pole | Wartość |
|---|---|
| healthz | 200 |
| pid papieru | 45033 |
| mode | PAPER |
| live_enabled | false |
| kwalifikator dziś | **+30,16 USD** |
| 7 dni | −142,41 USD |
| od początku | −177,24 USD |
| Mitch dziś | **−202,45 USD** |
| Mitch od startu | −110,36 USD |
| Rezerwa zysku | **120,86 USD** (Mitch 33,88 · kwalifikator 86,98) · PAPER, nie LIVE |
| pauza Mitch | 365cf589, 207e77c2, checkr3, mihaXd |
| 096b159 | 0 kopii, bez pauzy |
| dziennik Mitch | 40 zamknięć |
| stan kopiowania | działa, ostatni sygnał 07:35 |
| skok ekranu | nie — scroll 400 zostaje po odświeżeniu |

## Audyt co 1 h

Pętla `AGENT_LOOP_TICK_dash_audit`, sleep 3600. Sprawdza lokalny 8769: healthz, `/api/state` bez 401, kafelki nie są puste, LIVE off. Pętla 2 h (`ops_audit`, pid 8461) zostaje osobno. Nie restartuję papieru tylko dlatego, że arkusz jest STALE.

## Changelog

- `btc-lab/lab/server.py` — `request_path` dla proxy, pętla 127.x, ciasteczko sesji po HTML/Basic.
- `lab/app.js` — `lastMitchSig` razem z `lastViewSig`; `render()` łapie wyjątek zamiast zabijać start.
- `lab/index.html` — cache `20261008-dash-fix`, `body` `notranslate`.
- Testy: `test_lab` 30, `test_eth` 6.

Git HEAD nadal bez commita, dopóki nie poprosisz. LIVE wyłączone.

## Audyt 8 października 2026, 08:38 Europe/Stockholm

Pid 45033, `/healthz` 200, GET `/` i `/api/state` 200 bez 401. Arkusz **FRESH**, referencja FRESH. Ekran `#wynik` i `#mitch` z liczbami, cache `dash-fix`. LIVE false.

Kwalifikator dziś **+15,76** (było +30,16 o 07:36) · 7 dni −156,81 · all −191,64. Kopiowanie działa, ostatni sygnał 08:36. Rezerwa **125,49** (Mitch 33,88 · kwalifikator 91,61). Mitch dziś −202,45 / all −110,36, 0 otwartych, 40 w dzienniku, pauza na czterech czerwonych. Scroll nie skacze. Papieru nie restartuję.

## Audyt 8 października 2026, 09:38 Europe/Stockholm

Pid 45033, GET `/` i `/api/state` 200. Ekran z liczbami, LIVE false. `/healthz` **503** — worker `DEGRADED`, referencja `MISSING_OR_STALE` (~34 s), arkusz **FRESH**, heartbeat żywy. Papieru nie restartuję.

Kwalifikator dziś **+4,29** (08:38 było +15,76) · 7 dni −168,27 · all −203,10. Kopiowanie działa, sygnał 09:36. Rezerwa **127,80**. Mitch −202,45 / −110,36, 40 w dzienniku, cztery pauzy. Kafelki niepuste, bez AWARIA.

## Audyt 8 października 2026, 10:38 Europe/Stockholm

Pid 45033, `/healthz` 200, GET `/` i `/api/state` 200. Ekran z liczbami, LIVE false. Arkusz STALE, referencja FRESH — papieru nie restartuję.

Kwalifikator dziś **+13,97** (09:38 było +4,29) · 7 dni −163,80 · all −193,43. Kopiowanie działa, sygnał 10:35. Rezerwa **137,11**. Mitch −202,45 / −110,36, 40 w dzienniku, cztery pauzy. Bez AWARIA.

## Audyt 8 października 2026, 11:38 Europe/Stockholm

Pid 45033, `/healthz` 200, GET `/` i `/api/state` 200. Ekran z liczbami, LIVE false. Arkusz STALE, referencja FRESH — papieru nie restartuję.

Kwalifikator dziś **−9,82** (10:38 było +13,97) · 7 dni −187,58 · all −217,21. Kopiowanie działa, sygnał 11:28. Rezerwa **139,08**. Mitch −202,45 / −110,36, 40 w dzienniku, cztery pauzy. Scroll bez skoku. Bez AWARIA.

## Audyt 8 października 2026, 12:38 Europe/Stockholm

Pid 45033, `/healthz` 200, GET `/` i `/api/state` 200. Ekran z liczbami, LIVE false. Arkusz STALE, referencja FRESH — papieru nie restartuję.

Kwalifikator dziś **−1,60** (11:38 było −9,82) · 7 dni −179,36 · all −208,99. Kopiowanie działa, sygnał 12:34. Rezerwa **144,85**. Mitch −202,45 / −110,36, 40 w dzienniku, cztery pauzy. Scroll bez skoku. Bez AWARIA.

## Audyt 8 października 2026, 13:38 Europe/Stockholm

Pid 45033, GET `/` i `/api/state` 200. Ekran z liczbami, LIVE false. `/healthz` **503** — worker `DEGRADED`, arkusz STALE, referencja `MISSING_OR_STALE` (~24 s), heartbeat 7 s. Papieru nie restartuję.

Kwalifikator dziś **−15,29** (12:38 było −1,60) · 7 dni −193,05 · all −222,68. Kopiowanie działa, sygnał 13:35. Rezerwa **155,37**. Mitch −202,45 / −110,36, 40 w dzienniku, cztery pauzy. Scroll bez skoku. Bez AWARIA.

## Audyt 8 października 2026, 14:38 Europe/Stockholm

Pid 45033, `/healthz` 200, GET `/` i `/api/state` 200. Ekran z liczbami, LIVE false. Arkusz STALE, referencja FRESH — papieru nie restartuję.

Kwalifikator dziś **−14,25** (13:38 było −15,29) · 7 dni −192,01 · all −221,64. Kopiowanie działa, sygnał 14:34. Rezerwa **163,45**. Mitch −202,45 / −110,36, 40 w dzienniku, cztery pauzy. Scroll bez skoku. Bez AWARIA.

## Audyt 8 października 2026, 15:38 Europe/Stockholm

Pid 45033, `/healthz` 200, GET `/` i `/api/state` 200. Ekran z liczbami, LIVE false. Arkusz STALE, referencja FRESH — papieru nie restartuję.

Kwalifikator dziś **−27,65** (14:38 było −14,25) · 7 dni −185,01 · all −235,05. Kopiowanie działa, sygnał 15:34. Rezerwa **170,87**. Mitch −202,45 / −110,36, 40 w dzienniku, cztery pauzy. Scroll bez skoku. Bez AWARIA.

## Audyt 8 października 2026, 16:38 Europe/Stockholm

Pid 45033, `/healthz` 200, GET `/` i `/api/state` 200. Ekran z liczbami, LIVE false. Arkusz STALE, referencja FRESH — papieru nie restartuję.

Kwalifikator dziś **−19,77** (15:38 było −27,65) · 7 dni −180,95 · all −227,16. Kopiowanie działa, sygnał 16:34. Rezerwa **181,60**. Mitch −202,45 / −110,36, 40 w dzienniku, cztery pauzy. Scroll bez skoku. Bez AWARIA.

## Audyt 8 października 2026, 17:38 Europe/Stockholm

Pid 45033, `/healthz` 200, GET `/` i `/api/state` 200. Ekran z liczbami, LIVE false. Arkusz STALE, referencja FRESH — papieru nie restartuję.

Kwalifikator dziś **−6,65** (16:38 było −19,77) · 7 dni −161,81 · all −214,04. Kopiowanie działa, sygnał 17:34. Rezerwa **195,74**. Mitch −202,45 / −110,36, 40 w dzienniku, cztery pauzy. Scroll bez skoku. Bez AWARIA.

## Audyt 8 października 2026, 18:38 Europe/Stockholm

Pid 45033, `/healthz` 200, GET `/` i `/api/state` 200. Ekran z liczbami, LIVE false. Arkusz STALE, referencja FRESH — papieru nie restartuję.

Kwalifikator dziś **+2,56** (17:38 było −6,65) · 7 dni −152,60 · all −204,83. Flow: sygnały odrzucone przez filtry, ostatni 18:34. Rezerwa **204,52**. Mitch −202,45 / −110,36, 40 w dzienniku, cztery pauzy. Scroll bez skoku. Bez AWARIA.

## Audyt 8 października 2026, 19:38 Europe/Stockholm

Pid 45033, `/healthz` 200, GET `/` i `/api/state` 200. Ekran z liczbami, LIVE false. Arkusz **FRESH**, referencja FRESH.

Kwalifikator dziś **−6,05** (18:38 było +2,56) · 7 dni −161,22 · all −213,45. Kopiowanie działa, sygnał 19:32. Rezerwa **204,90**. Mitch −202,45 / −110,36, 40 w dzienniku, cztery pauzy. Scroll bez skoku. Bez AWARIA.

## Audyt 8 października 2026, 20:38 Europe/Stockholm

Pid 45033, `/healthz` 200, GET `/` i `/api/state` 200. Ekran z liczbami, LIVE false. Arkusz STALE, referencja FRESH — papieru nie restartuję.

Kwalifikator dziś **−9,30** (19:38 było −6,05) · 7 dni −164,46 · all −216,69. Flow: wszystkie zakupy wstrzymane, ostatni sygnał 19:56. Rezerwa **204,90**. Mitch −202,45 / −110,36, 40 w dzienniku, cztery pauzy. Scroll bez skoku. Bez AWARIA.

## Audyt 8 października 2026, 21:38 Europe/Stockholm

Pid 45033, `/healthz` 200, GET `/` i `/api/state` 200. Ekran z liczbami, LIVE false. Arkusz STALE, referencja FRESH — papieru nie restartuję.

Kwalifikator dziś **−9,30** (bez zmiany od 20:38) · 7 dni −164,46 · all −216,69. Kopiowanie działa, sygnał 21:25. Rezerwa **204,90**. Mitch −202,45 / −110,36, 40 w dzienniku, cztery pauzy. Scroll bez skoku. Bez AWARIA.
