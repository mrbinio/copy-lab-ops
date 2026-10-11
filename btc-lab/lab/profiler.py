"""On-demand sampling profiler. It never trades.

Touch data/PROFILE and each lab process samples the Python stacks of all
its threads every 10 ms for 20 s, then writes logs/profile-<role>-<pid>.txt
with the busiest functions and stacks. 11 Oct 2026: the qualifier process
ran at ~195% CPU and the Mac fan was loud; this names the cause.
"""
import collections
import os
import sys
import threading
import time
from pathlib import Path

SECONDS = 20
EVERY = 0.01


def _sample(out_path):
    me = threading.get_ident()
    leaf = collections.Counter()
    owned = collections.Counter()
    stacks = collections.Counter()
    samples = 0
    end = time.time() + SECONDS
    while time.time() < end:
        for ident, frame in sys._current_frames().items():
            if ident == me:
                continue
            chain = []
            f = frame
            while f is not None and len(chain) < 12:
                code = f.f_code
                chain.append('%s:%d %s' % (Path(code.co_filename).name, f.f_lineno, code.co_name))
                f = f.f_back
            if not chain:
                continue
            idle = chain[0].split(' ')[-1] in ('wait', 'select', 'poll', '_worker', 'sleep', 'acquire', 'readinto',
                                              'recv_into', 'read', 'accept', 'get', 'control', 'run_forever')
            if idle:
                continue
            leaf[chain[0]] += 1
            for name in set(c.split(':')[0] + ' ' + c.split(' ')[-1] for c in chain):
                owned[name] += 1
            stacks[' <- '.join(chain[:6])] += 1
        samples += 1
        time.sleep(EVERY)
    lines = ['samples %d over %d s, pid %d' % (samples, SECONDS, os.getpid()), '', 'busiest leaf lines:']
    lines += ['%6d  %s' % (n, k) for k, n in leaf.most_common(25)]
    lines += ['', 'functions on the stack (inclusive):']
    lines += ['%6d  %s' % (n, k) for k, n in owned.most_common(30)]
    lines += ['', 'top stacks:']
    lines += ['%6d  %s' % (n, k) for k, n in stacks.most_common(15)]
    tmp = Path(str(out_path) + '.tmp')
    tmp.write_text('\n'.join(lines))
    os.replace(tmp, out_path)


def start(data_dir, logs_dir, role):
    """Watch for data/PROFILE in a daemon thread."""
    flag = Path(data_dir) / 'PROFILE'

    def loop():
        done_for = None
        while True:
            try:
                stamp = flag.stat().st_mtime if flag.exists() else None
                if stamp and stamp != done_for:
                    done_for = stamp
                    _sample(Path(logs_dir) / ('profile-%s-%d.txt' % (role, os.getpid())))
            except Exception:
                pass
            time.sleep(2)
    threading.Thread(target=loop, name='lab-profiler', daemon=True).start()
