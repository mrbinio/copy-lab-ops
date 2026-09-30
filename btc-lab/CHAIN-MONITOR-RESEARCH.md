# Chain Monitor — On-chain Research Notes (2026-09-30)

## Prawdziwy format eventów Polymarket na Polygon

### Exchange Contracts (CTF + NegRisk)
- Event: `OrdersMatched(bytes32 indexed takerOrderHash, bytes32 indexed makerOrderHash, bytes32 indexed matchHash)`
- Topic: `0xbc9a2432e8aeb48327246cddd6e872ef452812b4243c04e6bfb786a2cd8faf0d`
- **4 topics, 0 data words**
- **NIE zawiera adresów, kwot ani token IDs** — tylko hashe zleceń
- Bezużyteczne do identyfikacji wallets

### CTF Token Contract (0x4D97DCd97eC945f40cF65F87097ACe5EA0476045)
- Event: `TransferSingle(address indexed operator, address indexed from, address indexed to, uint256 id, uint256 value)`
- Topic: `0xc3d58168c5ae7397731d063d5bbf3d657854427343f4c083240f7aacaa2d0f62`
- **4 topics (sig + 3 indexed addresses), 2 data words (token_id + value)**
- **707 eventów w 9 blokach (~20s)** — bardzo aktywny
- `operator` = exchange contract address (kto inicjuje)
- `from` = sprzedający (0x0 = mint)
- `to` = kupujący
- `token_id` = conditional token (duży uint256, mapowany na conditionId/slug przez Gamma API)
- `value` = ilość tokenów (w micro-units)

### Podejście do monitora
1. **Subskrybować TransferSingle z CTF Token contract** (nie z Exchange)
2. Filtrować `from` i `to` po monitorowanych wallet adresach
3. `token_id` rozwiązywać przez TokenResolver → slug/conditionId/side
4. BUY = wallet jest w `to`, SELL = wallet jest w `from`
5. Cena = trzeba obliczyć z USDC transfer w tej samej transakcji (lub z orderbooka)

### Cena transakcji
Exchange contract NIE emituje ceny. Opcje:
- Parsować USDC Transfer (ERC20) z tej samej transakcji — USDC/value = cena
- Pobrać cenę z orderbooka CLOB w momencie wykrycia
- Dane z Data API mają pole `price` — ale to właśnie to czego chcemy uniknąć

### Stary format OrderFilled (topic 0xd0a08e8...)
- **NIE jest emitowany** przez obecne kontrakty Polymarket
- Prawdopodobnie stary kontrakt lub inny fork
- Mój parser był oparty na tym nieistniejącym formacie — stąd wszystkie problemy

### Alchemy Free Tier
- `eth_getLogs`: max 10 bloków per request
- `eth_subscribe(logs)`: brak limitu bloków — streaming w real-time
- Darmowy plan wystarczy do monitorowania

### Wolumen
- ~707 TransferSingle / 9 bloków / ~20s = ~35 events/s
- Po filtrze 3 wallets: prawdopodobnie <1 event/min
- Darmowy tier Alchemy wystarczy
