#!/bin/bash
# Keep the Mac's clock tight enough for sub-second copy decisions.
#
# macOS timed syncs rarely: it let the clock run 2.34s slow before stepping it
# back on 2026-10-02, and the kernel's own frequency correction (-31 ppm) is far
# short of this laptop's real ~0.7 s/hour drift. The lab compensates for skew,
# but a 2s sawtooth still leaves every freshness judgement briefly wrong while
# VenueClock re-samples. Syncing every 5 minutes bounds the error near 0.06s.
#
# Setting the clock needs root, so this is the one piece that needs sudo:
#   sudo bash btc-lab/deploy/install-timesync.sh
set -euo pipefail
label=com.btc-lab.timesync
target="/Library/LaunchDaemons/$label.plist"
source_plist="$(cd "$(dirname "$0")" && pwd)/timesync.plist"

if [ "$(uname -s)" != Darwin ]; then
  echo 'Ten instalator uruchom na prywatnym Macu.'; exit 1
fi
if [ "$(id -u)" != 0 ]; then
  echo "Ustawienie zegara wymaga uprawnien administratora. Uruchom:"
  echo "  sudo bash $0"
  exit 1
fi
if [ ! -f "$source_plist" ]; then
  echo "Brak pliku $source_plist"; exit 1
fi

install -m 0644 -o root -g wheel "$source_plist" "$target"
launchctl bootout "system/$label" 2>/dev/null || true
launchctl bootstrap system "$target"

echo "Zainstalowane: $target"
echo "Synchronizacja czasu co 5 minut. Sprawdzenie:"
echo "  launchctl print system/$label | grep -E 'state|runs'"
echo "  sntp time.apple.com"
echo "Odinstalowanie:"
echo "  sudo launchctl bootout system/$label && sudo rm $target"
