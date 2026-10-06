"""Mac clock versus NTP. Enabling sync in System Settings is not a reading."""
import subprocess
import time

HOST = 'time.apple.com'


def parse_sntp(text):
    for line in reversed([line.strip() for line in text.splitlines() if line.strip()]):
        parts = line.split()
        if len(parts) >= 4 and parts[1] == '+/-':
            return float(parts[0]), float(parts[2])
    raise ValueError('unrecognized sntp output')


def measure_once():
    proc = subprocess.run(
        ['/usr/bin/sntp', '-t', '2', HOST],
        capture_output=True, text=True, timeout=8,
    )
    text = (proc.stdout or '') + '\n' + (proc.stderr or '')
    if proc.returncode != 0 and not text.strip():
        raise RuntimeError('sntp exited %s' % proc.returncode)
    return parse_sntp(text)


def measure_clock():
    """Two samples. A split reading is unreliable and is not stepped from here."""
    first = measure_once()
    second = measure_once()
    disagree = abs(first[0] - second[0])
    uncertainty = max(first[1], second[1])
    offset = (first[0] + second[0]) / 2
    status = 'synced'
    if disagree > 0.10 or uncertainty > 0.05 or abs(offset) > 0.30:
        status = 'unreliable'
    return {
        'status': status,
        'offset_ms': round(offset * 1000, 1),
        'uncertainty_ms': round(uncertainty * 1000, 1),
        'disagreement_ms': round(disagree * 1000, 1),
        'source': HOST,
        'checked_at': time.time(),
        'step_note': 'Stepping the clock needs root. This reading does not change the clock.',
    }
