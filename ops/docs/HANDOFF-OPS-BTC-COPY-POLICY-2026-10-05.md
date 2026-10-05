# HANDOFF — Copy policy, pause, and separate books, 2026-10-05

## Executive summary

A pause rejected the whole source signal before BUY and SELL were split, so an open PAPER position could not be sold. The live buy also used the current ask plus 2 cents and did not check it against the source trade. Independent hold-to-settlement tickets were the evidence for promotion and restore, and the dashboard had started adding them into one total.

Buys now have to stay within 10 cents of the source trade’s own price. A pause blocks the next buy and still allows a source SELL and official settlement. A new observation book, `copy-observe-v1`, uses that same policy from an explicit start time. Independent tickets stay on the screen as a separate study. They are not a PAPER profit and they do not promote or restore a wallet.

## What changed and why

The Mac copy of `wallet_copy.py` matched the branch. The pause check and the ask+2¢ limit were still there. The 20–70¢ band and the 90-second signal age stay. A missing source price is `SOURCE_PRICE_MISSING` and does not borrow the current book. If the book moves outside ±10¢ before the fill, the buy is `SOURCE_PRICE_MOVED`.

The observation history does not replay signals from before its start, and it does not reprice them on today’s book. Qualification thresholds are unchanged. Until the new book has its own settled trades, an observed wallet’s policy result is “brak danych”, not zero and not the independent-ticket net.

The strategy total, the copy PAPER accounts, the policy observation, and the independent tickets are shown separately. They are not added together.

## Settlement check

At 14:43, before this deploy: 20 observed wallets. COPY_PAUSED fills still open on those wallets: 2,442. Settled with a fee: 191, across 8 wallets. Ended and not yet checked: 2,379, all with `checked` still 0. Global COPY_PAUSED pending 2,752, settled 480. The next seats were observed wallets, not a frozen set of eight. One of those next markets was already closed with one winner, so that row is program backlog, not a market waiting for an official result. Pending rows had no recent failed check, which means unresolved markets are not holding the seats.

## Changelog

- `btc-lab/lab/copy_policy.py` — shared buy and sell decision, ±10¢, no reuse of the same book snapshot.
- `btc-lab/lab/wallet_copy.py` — pause applies to BUY only; arrival book is checked before the fill.
- `btc-lab/lab/wallet_observation.py` — versioned observation from an explicit start.
- `btc-lab/lab/wallet_roster.py` — promote and restore read that book, not independent tickets.
- `btc-lab/lab/wallet_watch.py`, `lab/app.js`, `lab/index.html` — separate books, color follows the headline number.
- Tests for the pause, the 10-cent edges, a missing price, a moved book, shared fills, and restore.

## Next decision

Refresh the dashboard. The policy observation starts empty at this deploy. Do not unpause a wallet to manufacture trades. Live orders stay off.
