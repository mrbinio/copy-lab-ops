#!/usr/bin/python3
"""Step the Mac clock back when Apple's time service jumps it.

Network time is already on. Twice on 2026-10-02 `timed` trusted a sample
about 2.3s off, stepped the clock, and only undid it on the next cycle,
half an hour later. A fresh order book looks like it came from the future
for that whole window. This measures time.apple.com twice and steps only
when both samples agree and the offset is large. A fuzzy or split reading
is left alone: stepping on one bad packet is the bug we are correcting.
"""
import os
import subprocess
import sys
import time
from pathlib import Path

HOST = 'time.apple.com'
STEP_SECONDS = 0.30
MAX_UNCERTAINTY = 0.05
MAX_DISAGREEMENT = 0.10
LOG = Path(os.environ.get(
    'CLOCK_GUARD_LOG',
    '/Users/damianbiniarz/Library/Application Support/BTC Lab/logs/clock-guard.log'))

def parse_sntp(text):
    """Find the offset line wherever it sits.

    Run as root, sntp can append a bind warning after the measurement.
    Taking the last line treated that warning as the reading and the
    guard crashed on its first launchd run.
    """
    for line in reversed([line.strip() for line in text.splitlines() if line.strip()]):
        parts = line.split()
        if len(parts) >= 4 and parts[1] == '+/-':
            return float(parts[0]), float(parts[2])
    shown = ' '.join(text.split())[:240]
    raise ValueError('unrecognized sntp output: %r' % shown)

def action_for(first, second):
    """first and second are (offset_seconds, uncertainty_seconds)."""
    if abs(first[0] - second[0]) > MAX_DISAGREEMENT:
        return 'hold'
    if max(first[1], second[1]) > MAX_UNCERTAINTY:
        return 'hold'
    if abs((first[0] + second[0]) / 2) < STEP_SECONDS:
        return 'ok'
    return 'step'

def measure():
    proc = subprocess.run(['/usr/bin/sntp', '-t', '2', HOST],
                          capture_output=True, text=True, timeout=15)
    text = (proc.stdout or '') + '\n' + (proc.stderr or '')
    if proc.returncode != 0 and not text.strip():
        raise RuntimeError('sntp exited %s with no output' % proc.returncode)
    return parse_sntp(text)

def step_clock():
    subprocess.run(['/usr/bin/sntp', '-S', HOST], check=True, timeout=20)

def record(line):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open('a') as handle:
        handle.write(time.strftime('%Y-%m-%d %H:%M:%S ') + line + '\n')

def main():
    try:
        first, second = measure(), measure()
    except (ValueError, RuntimeError, subprocess.TimeoutExpired, OSError) as error:
        record('hold ' + ' '.join(str(error).split())[:500])
        print('hold', error, file=sys.stderr)
        return 0
    decision = action_for(first, second)
    offset = (first[0] + second[0]) / 2
    if decision == 'step':
        if os.geteuid() != 0:
            record('need root to step %+.3fs' % offset)
            print('need root to step %+.3fs' % offset, file=sys.stderr)
            return 1
        step_clock()
    record('%s %+.3fs (samples %+.3f, %+.3f)' % (decision, offset, first[0], second[0]))
    print('%s %+.3fs' % (decision, offset))
    return 0

if __name__ == '__main__':
    sys.exit(main())
