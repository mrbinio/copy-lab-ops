#!/bin/bash
# One-time install of the clock guard. Needs the admin password once.
set -euo pipefail
if [[ "$(id -u)" -ne 0 ]]; then
  echo "Uruchom: sudo bash \"$0\""
  exit 1
fi
PLIST_SRC="/Users/damianbiniarz/Projects/copy-lab-ops/btc-lab/deploy/com.btc-lab.clock.plist"
install -m 644 "$PLIST_SRC" /Library/LaunchDaemons/com.btc-lab.clock.plist
chown root:wheel /Library/LaunchDaemons/com.btc-lab.clock.plist
launchctl bootout system/com.btc-lab.clock 2>/dev/null || true
launchctl bootstrap system /Library/LaunchDaemons/com.btc-lab.clock.plist
launchctl enable system/com.btc-lab.clock
launchctl kickstart -k system/com.btc-lab.clock
echo "clock guard is running"
