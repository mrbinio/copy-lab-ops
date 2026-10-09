# BTC Lab — szybka ścieżka Mitcha, Telegram, Data API v2 (9.10.2026)

PAPER. LIVE wyłączone **w kodzie** (`lab/live_gate.py`). Gałąź `ops/btc-fast-path-2026-10-09`, wdrożona do `releases/b009e2b8b429-1790926011187411000`. Kopia sprzed wdrożenia: `backups/release-before-fast-20261009-173909/` (`py/`, `web/`).

## Dlaczego Mitch nie kupował od 8.10

Polymarket rozlicza teraz przez giełdę `0xe111180000d2663c0091e4f400237545b87b996b`. Jej `OrderFilled` ma nowy temat `0xd543adfd…` (7 słów). `order_fill.py` znał tylko stary `0xd0a08e8c…`, więc paragon nigdy nie pasował. Kupno Mitcha wymagało paragonu albo printu, a print zawsze był starszy niż 1 s. Wynik: 0 `MITCH_BUY`, i to nie przez bramkę, tylko przez błąd.

Do tego bramka 1 s mierzyła wiek od chwili, w której **nasz** WSS zobaczył log, a nie od jego transakcji.

## Pomiary na żywo (BTC 15m, 9.10)

| Źródło | Względem dopasowania na CLOB |
|---|---|
| `last_trade_price` (kanał market CLOB) | ~0 s, to jest moment dopasowania |
| transakcja `matchOrders` w mempoolu | +70–100 ms |
| log na łańcuchu (TransferSingle) | +1,4 s mediana, p90 2,0 s |
| RTDS `activity/trades` | ~1 s po łańcuchu |
| publiczna lista Data API | mediana 8,7 s |

Pełna ścieżka na żywym rynku (90 s, 58 transakcji): od dopasowania do kopiarki mediana **0,12 s**, p90 0,66 s, odczytane 58/58.

## Nowa ścieżka

```
CLOB market WS last_trade_price (tx hash, czas w ms)   ← osobny wątek i pętla
  → eth_getTransactionByHash (blockmachine + drpc, co 40 ms, do 0,6 s)
  → match_decoder: matchOrders(bytes32, Order taker, Order[] makers, takerFill, makerFills[], takerFee, makerFees[])
  → portfel Mitcha? → wallet_activity (_source=clob_match) → MitchCopy.handle na puli MITCH
```

- Dekoder zgadza się z publiczną listą w 40/40 transakcjach Mitcha (udziały dokładnie, USDC + opłata).
- `CHAIN_SOURCES = ('clob_match', 'order_filled', 'market_trade')`. Wiek liczony od czasu dopasowania.
- Paragon (zapas) ma `_ts_basis`: `match` / `block` / `local_detect`. `local_detect` nie może kupić (`SOURCE_TIME_UNKNOWN`).
- Decyzja zapada w chwili, gdy przyjdzie book. Czekanie na zapis do bazy po decyzji nie robi z kupna spóźnionego.
- Wiersza `clob_match` / `order_filled` nie nadpisze publiczna lista ani `chain-fast`, a `_source` zostaje.
- Monitor łańcucha: portfele niekopiowane nie zajmują slotów; limit 30 → 120.

## Okres testu Mitcha

`mitch_stint = fast-match-v1` od wdrożenia. Pauza liczy tylko kopie otwarte w tym okresie. Księga od startu (−110,36) jest **nietknięta** i widoczna. Reguła bez zmian: minus dziś albo w okresie → pauza, bez auto-retestu. Uzasadnienie: straty pochodzą ze ścieżki 8–80 s, której już nie ma. Bez nowego okresu 4 z 5 portfeli nigdy nie przetestowałyby nowej ścieżki.

## Bezpieczeństwo

- `live_gate.LIVE_ORDERS_ALLOWED = False`. `CLOBClient` rzuca `LiveOrdersDisabled`. `clob_live=true` w configu jest ignorowane i logowane.
- SELL w `clob_order.py`: GTC → FOK (nic nie zostaje w arkuszu).
- **Klucz prywatny CLOB nadal leży w `config.json`** (log ostrzega przy każdym starcie). Damian powinien go stamtąd przenieść.

## Telegram

`deploy/telegram_bot.py`, launchd `com.btc-lab.telegram` (KeepAlive). Działa po utworzeniu `~/Library/Application Support/BTC Lab/telegram.json` z `{"token": "...", "chat_ids": []}`. Czyta `/api/state` z loopbacka. Wysyła: kupno/sprzedaż/zamknięcie Mitcha, zmiany pauzy, stojący heartbeat, brak pulpitu, podsumowanie o 21:00. Komendy: `/status /mitch /portfele /rezerwa /stop /wznow`. `/stop` = plik `data/PAUSE` (Mitch też go teraz respektuje). Bot nie składa zleceń.

## Data API v2

`lab/data_api.py`: wszystkie wywołania idą do `/v2/…`, a wiersze zostają w kształcie v1 (`token_id→asset`, `current_size→size`, `user_id→proxyWallet`, `volume→vol`, snake→camel). Obserwator idzie kursorem do 20 stron po 500 (było 4 strony offsetem → `INCOMPLETE_PAGE_LIMIT`). v1 zostanie wyłączone 24.10.2026.

## Strategie 5–15 min

Wszystkie zatrzymane (`early-v1` też), zakładka oznaczona ARCHIWUM. Każda straciła po opłatach, łącznie ok. −73 USD na 206 transakcjach. Kod i księgi zostają.

## Testy

Nowe: `test_fast_match.py` (prawdziwe fixture'y z łańcucha), `test_data_api.py`, `test_telegram_bot.py`. Zielone: mitch, chain, order_fill, wallet_copy, roster, lab, eth, strategy_control, retirement, opportunity_research.
Stare, niezwiązane z tymi zmianami: `test_skip_review.py` (3 failures również na kodzie bazowym); `test_lab.py` czasem wywraca się na sprzątaniu katalogu tymczasowego (flaky, również bazowo).

## Do zrobienia dalej

1. Obserwować pierwsze `MITCH_BUY` z `clob_match`: realny `total_ms`, fill vs jego cena, wynik w okresie.
2. Book przez WebSocket zamiast HTTP (~100–130 ms oszczędności).
3. Kwalifikator na tę samą szybką ścieżkę (dziś 90 s + publiczna lista).
4. Własny portfel i wykonanie LIVE: dopiero po dodatnim okresie PAPER na szybkiej ścieżce.
