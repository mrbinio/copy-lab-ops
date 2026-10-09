# HANDOFF — BTC Lab disk + cheaper chain 2026-10-02

## Executive summary

Damian did not need to send any Alchemy address. The paid Alchemy socket is replaced by a free public Polygon socket (`wss://polygon.drpc.org`). Chain watch stays on so we can still see a seed buy in a fraction of a second. About 38 GB of leftover installer backups are gone. The live 6.9 GB database was not vacuumed. Real copy still spends $0 because Polymarket rejects the current wallet (deposit-wallet flow).

## What changed

1. **No URL from Damian.** Previous note asked him for a cheaper socket. He does not have one. Lab now defaults to `wss://polygon.drpc.org` when `ALCHEMY_WSS` is empty, and live `config.json` `alchemy_wss` points there. PublicNode timed out; drpc subscribed and delivered a log in 1.6 s.
2. **Disk.** Six old BTC copies and six old ETH copies plus leftover `-wal`/`-shm`/`.partial` files were deleted. Kept two newest BTC and two newest ETH. Data volume went from ~2.3 GB free (99%) to ~37 GB free (83%).
3. **Why backups piled up.** Installer `cleanup()` skipped any backup that still had a journal. Interrupted copies left 0-byte WAL files, so nothing ever aged out. Cleanup now drops stale journals and then keeps two good backups per asset.
4. **Live database.** Not crushed. Worker 0.6.6 deletes old book/price notes in batches of 4000 every 10 minutes (keeps 48 hours). File size stays ~6.9 GB until a later vacuum, but it stops growing. Vacuum only after a planned stop, when free space stays above 7 GB.

## Numbers

- Backups removed: 66 files, 37.94 GB.
- Backups kept: 2× BTC (~7.1 GB each) + 2× ETH (~1.8 GB each) = 17 GB.
- Live data: still 8.9 GB (`lab.sqlite` 6.9 GB + ETH 1.9 GB).
- Free on Data volume after cleanup: 37 GB.
- First prune after restart: 4000 old notes.
- Real order: still $0. Last reject before restart: `maker address not allowed, please use the deposit wallet flow`.
- Mitch timing from last night still applies to the path: see chain in ~0.2 s, send our order in ~0.6 s. That path does not need Alchemy. It needs any working Polygon log socket. drpc is that socket.

## Next decision

1. Leave the free socket on. Cancel or ignore the Alchemy invoice when the usage window ends.
2. Do not vacuum tonight unless Damian asks. Free space is enough.
3. Real buys still need the Polymarket deposit-wallet flow. Paper copy stays on.
