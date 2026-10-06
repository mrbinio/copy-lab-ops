# Handoff — screen refresh after the Mitch start

Date: 2026-10-06, evening. PAPER only. `clob_live` stays false. Port 8769. History, pauses and `wallet_copy_start` were not reset.

## Executive summary

The banner “ekran nie dostał odświeżenia” was the page treating a late collector heartbeat as a failed fetch. Under that, the collector really had stalled. Mitch’s first read of activity ran on the service loop and locked the database. The copy journal then rebuilt its status by re-reading every position once per wallet, so the publish ran longer than the watchdog allows and the watchdog restarted the service before the screen got a new snapshot.

Both are in the running revision `53fbd48e73476453218d277dccbb3022c1c627bd`. After that start the copy snapshot and the Mitch snapshot both moved again, and `/healthz` returned 200. A logged-in reload is what shows the new banner. This is not a profit result and it does not confirm a sub-second copy.

## What changed and why

- Mitch’s pending read uses the `first_seen` index and runs off the event loop, so a slow history scan cannot freeze heartbeats and sockets.
- The copy status loads positions once per publish, and the latest decision per wallet uses an index on `(wallet, ts)`.
- The banner says the screen failed only when the page itself has no fresh answer. A late collector check is a separate line.

## Numbers

- Running revision `53fbd48`. Previous stall revision was `da8fe61`.
- Health after the last start: 200. `clob_live` false. Port 8769.
- Copy snapshot status `RUNNING` and younger than a minute. Worker heartbeat moving. Status can still read `DEGRADED` while the reference feed is late; that is not a dead page.
- The watchdog is loaded again. It restarts only when the heartbeat or a publish is actually stale, and a process younger than three minutes is left alone.

## Next decision

Reload the dashboard. If the banner returns, the next place to look is a publish that again fails to finish, not another restart inside the same ten minutes.
