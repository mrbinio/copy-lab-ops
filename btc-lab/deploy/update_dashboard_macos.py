#!/usr/bin/env python3
"""Update only BTC Lab web assets; preserve the running worker and configuration."""
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import urllib.request

EXPECTED = {"app.js":"d77722a3586a4b83d60a24538ad1c9b97c573e73d8a6d7bc4775be573e67d5d9","index.html":"35cae7d501818e6226bc45eacf62e230238492f41eca9af20518b64eb018ba53","style.css":"068821c8d0151b364bc9ee45c57063d920d32764f100d4940787b57f7ad4847c"}

def update(root, revision):
    if not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('Expected a pinned, full GitHub commit SHA')
    config = json.loads((root / 'config.json').read_text())
    release = Path(config['release']).resolve()
    if not release.is_relative_to((root / 'releases').resolve()):
        raise ValueError('Release is outside the BTC Lab installation')
    web = release / 'lab'
    originals = {name: (web / name).read_bytes() for name in EXPECTED}
    downloaded = {}
    for name, digest in EXPECTED.items():
        url = f'https://raw.githubusercontent.com/mrbinio/copy-lab-ops/{revision}/lab/{name}'
        req = urllib.request.Request(url, headers={'User-Agent': 'BTC-Lab-Dashboard-Updater/1.0'})
        with urllib.request.urlopen(req, timeout=30) as response:
            payload = response.read(2_000_001)
        if len(payload) > 2_000_000 or hashlib.sha256(payload).hexdigest() != digest:
            raise ValueError(f'Asset validation failed: {name}')
        downloaded[name] = payload
    # Download and verify everything before modifying the installed files.
    backup = Path(tempfile.mkdtemp(prefix='dashboard-', dir=str(root / 'releases')))
    for name, data in originals.items():
        (backup / name).write_bytes(data)
    def replace(name, data):
        fd, temporary = tempfile.mkstemp(prefix='.' + name, dir=str(web))
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(data)
            os.replace(temporary, web / name)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    try:
        # HTML last; all files remain valid for requests during the short swap.
        for name in ('style.css', 'app.js', 'index.html'):
            replace(name, downloaded[name])
    except Exception:
        for name, data in originals.items():
            replace(name, data)
        raise
    print('Dziennik z filtrem Mitch 3-7 zaktualizowany. Kolektor nie byl restartowany.')
    print(f'Odswiez dashboard: http://127.0.0.1:{config["port"]}/#activity')
    print(f'Kopia poprzedniego interfejsu: {backup}')

if __name__ == '__main__':
    try:
        if len(sys.argv) != 2:
            raise ValueError('Usage: update_dashboard_macos.py COMMIT_SHA')
        update(Path.home() / 'Library/Application Support/BTC Lab', sys.argv[1])
    except Exception as exc:
        print(f'Aktualizacja dashboardu nieudana: {type(exc).__name__}: {exc}', file=sys.stderr)
        sys.exit(1)
