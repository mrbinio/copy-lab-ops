"""Exit if either process exits; container restart policy restarts the pair."""
import os
import signal
import subprocess
import sys
import time

def main():
    processes=[subprocess.Popen([sys.executable,'-m','lab.worker'],env={**os.environ,'LAB_ASSET':asset}) for asset in ('BTC','ETH')]
    processes.append(subprocess.Popen([sys.executable,'-m','lab.server']))
    stopping=False
    def stop(*args):
        nonlocal stopping
        stopping=True
    signal.signal(signal.SIGTERM,stop)
    signal.signal(signal.SIGINT,stop)
    try:
        while not stopping and all(p.poll() is None for p in processes): time.sleep(1)
    finally:
        for p in processes:
            if p.poll() is None: p.terminate()
        for p in processes:
            try: p.wait(timeout=10)
            except subprocess.TimeoutExpired: p.kill(); p.wait()
    return 0 if stopping else 1

if __name__=='__main__': sys.exit(main())

