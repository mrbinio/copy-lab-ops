# HANDOFF — New free Polygon cable 2026-10-02

## Executive summary

Alchemy stays unpaid. The flaky free socket (`polygon.drpc.org`, drop every ~30 s) is replaced by `wss://rpc-polygon.blockmachine.io`. On this Mac it stayed up 90 seconds and pushed 2 891 TransferSingle logs. Live BTC Lab was restarted onto that cable. Damian is about to put $10 USDC onto Polymarket; real orders still fail until the deposit-wallet / funder address is wired.

## What changed

1. **Cable probe.** 14 public Polygon sockets. Winner: blockmachine (subscribe + logs + 90 s hold). drpc subscribed then died at 27 s. publicnode stayed up but sent 0 logs. llamarpc still fails DNS. The rest rejected the socket (400/402/403/404/429/521).
2. **Defaults.** `DEFAULT_CHAIN_WSS` is now blockmachine, then drpc. Live `config.json` `alchemy_wss` points at blockmachine (host only in this note).
3. **Not Alchemy.** No $50 invoice. No key from the dashboard screenshot.

## Numbers

- Probe hold: blockmachine 90.0 s, 2 891 logs, last log 0.8 s before stop.
- drpc in the same probe: 26.8 s then `no close frame`.
- Previous hour on drpc: 56 disconnects.
- Real CLOB: still $0. Last reject remains `maker address not allowed, please use the deposit wallet flow`.

## Next decision

1. Damian deposits $10 on polymarket.com with the same wallet (`…36a3bF01`). Then paste the deposit / proxy address so live orders can use signature type 3.
2. Watch `chain-fast` in `service.log` on the next seed 5m/15m buy. Target: see + paper copy under 1 s.
3. If blockmachine later rate-limits, fall back is still drpc. Do not switch Alchemy back unless that free cable dies.
