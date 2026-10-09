# Handoff — zwarte kafelki portfeli, 5 października 2026

## Executive summary

Kafelki na Portfelach znowu są krótkie: duża kwota, status, liczba zamkniętych i czy portfel jest śledzony. Zielone są u góry. Strategie 5–15 min zostają na swojej zakładce. Reguł kopiowania nie ruszano.

## Co się zmieniło i dlaczego

Poprzedni układ kafelka był akapitem. Kwota ginęła w zdaniu „Od początku księgi kopiowania PAPER · …”, a status „Śledzenie nieświeże…” zawijał się w chipie. Damian kazał wrócić do czytelnego kafelka.

Każdy kafel pokazuje teraz:

- ostatnie 8 znaków portfela i krótki status: AKTYWNY PAPER, TEST PAPER, WSTRZYMANY, OBSERWOWANY
- kwotę wybranego okresu (Dzisiaj / Ostatnie 7 dni / Od początku) i liczbę zamkniętych
- „Śledzony · HH:MM”, gdy sprawdzenie ma mniej niż 5 minut; inaczej „Ostatnio · HH:MM”
- jedną linię powodu pauzy, tylko gdy pauza jest

Zero zamkniętych w wybranym okresie jest 0,00 USD. Brak danych zostaje napisem „brak danych”.

## Liczby

Podgląd z tymi samymi kwotami co księga: od początku 4096b159 +14,52 USD / 82 jest pierwszy. Dzisiaj: 69de3680 +1,42 USD, potem zera, na dole 4096b159 −2,13 USD. Skład −0,71 USD bez zmian: −0,69 + 2,11 − 2,13. Zakładka 5–15 min ma jedną strategię i zero kafelków `copy-`.

## Wdrożenie

Skopiowane do działającego wydania, bez restartu procesu: `app.js`, `index.html`, `style.css`, cache `20261005-compact`. Adres: http://127.0.0.1:8769/ i twarde odświeżenie. Zalogowanej strony 8769 nie otwierałem. Podgląd układu był na lokalnym fiksturze 8773, potem wyłączonym.

## Następna decyzja

Damian odświeża http://127.0.0.1:8769/. Jeśli kafelek nadal jest akapitem, przeglądarka trzyma starą wersję `app.js?v=20261005-tiles`.
