#!/bin/bash
# Run locally in Terminal as the Mac's normal user. No sudo and no remote access.
set -euo pipefail
umask 077
if [ "$(uname -s)" != Darwin ]; then
  echo 'Ten instalator uruchom na prywatnym Macu.'; exit 1
fi
if [ "$(id -u)" = 0 ]; then
  echo 'Uruchom bez sudo, ze swojego zwyklego konta.'; exit 1
fi
lab_python=''
for candidate in /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 /usr/local/bin/python3 /opt/homebrew/bin/python3; do
  if [ -x "$candidate" ] && "$candidate" -c 'import sys; raise SystemExit(not ((3,11)<=sys.version_info[:2]<(3,15)))' 2>/dev/null; then
    lab_python="$candidate"; break
  fi
done
if [ -z "$lab_python" ]; then
  echo 'Potrzebny Python 3.11–3.14. Zainstaluj aktualny Python 3.13 z python.org.'
  echo 'Po instalacji uruchom Install Certificates.command z folderu Python w Applications.'
  echo 'Nastepnie uruchom ponownie ten instalator BTC Lab.'
  open 'https://www.python.org/downloads/macos/'
  exit 2
fi
lab_stage="$(mktemp -d -t btc-lab-install)"
trap 'rm -rf "$lab_stage"' EXIT
echo 'Pobieram projekt z Twojego repozytorium GitHub...'
if [ "$#" -eq 1 ] && [[ "$1" =~ ^[0-9a-f]{40}$ ]]; then
  lab_revision="$1"
elif [ "$#" -eq 0 ]; then
curl --fail --silent --show-error --location --connect-timeout 15 --max-time 60 \
  'https://api.github.com/repos/mrbinio/copy-lab-ops/git/refs/heads/main' -o "$lab_stage/ref.json"
lab_revision="$("$lab_python" -c 'import json,sys,re; s=json.load(open(sys.argv[1]))["object"]["sha"]; assert re.fullmatch("[0-9a-f]{40}",s); print(s)' "$lab_stage/ref.json")"
else
  echo 'Nieprawidlowy identyfikator wersji.'; exit 2
fi
curl --fail --silent --show-error --location --connect-timeout 15 --max-time 120 \
  "https://codeload.github.com/mrbinio/copy-lab-ops/zip/$lab_revision" -o "$lab_stage/source.zip"
/usr/bin/ditto -x -k "$lab_stage/source.zip" "$lab_stage/source"
"$lab_python" "$lab_stage/source/copy-lab-ops-$lab_revision/btc-lab/deploy/setup_macos.py" \
  "$lab_stage/source/copy-lab-ops-$lab_revision" "$lab_revision"

