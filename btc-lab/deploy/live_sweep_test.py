"""First, test transfer of the profit sweep: a few pUSD -> USDC.e -> USDC -> Kraken
(Damian runs it himself, 19 Oct 2026). Without --send it only shows the plan.
After the money shows up on Kraken, Claude writes data/sweep_ok.json and the
lab may sweep by itself in live mode.
Usage: python3 tools/live_sweep_test.py secrets/polygon.key [--send] [amount, default 3]"""
import glob
import json
import os
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
release = sorted(glob.glob(os.path.join(ROOT, 'releases', '*', 'btc-lab')), key=os.path.getmtime)[-1]
sys.path.insert(0, release)
from lab import live_sweep as ls  # noqa: E402
from eth_account import Account  # noqa: E402

ME_EXPECTED = '0xEb1FA4A1AFA2138Bba3B106E4a56778236a3bF01'
RPCS = ('https://polygon-bor-rpc.publicnode.com', 'https://polygon.drpc.org')


def rpc(method, params):
    last = None
    for attempt in range(3):
        for url in RPCS:
            try:
                req = urllib.request.Request(url, data=json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params}).encode(),
                                             headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'})
                reply = json.load(urllib.request.urlopen(req, timeout=20))
                if 'error' in reply:
                    raise RuntimeError('%s: %s' % (method, reply['error']))
                return reply['result']
            except Exception as error:
                last = error
        time.sleep(2)
    raise RuntimeError(str(last)[:300])


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    send_on = '--send' in sys.argv
    amount = float(args[1]) if len(args) > 1 else 3.0
    acct = Account.from_key(open(args[0]).read().strip())
    me = acct.address
    assert me == ME_EXPECTED, 'key does not open the expected wallet'
    print('wallet', me, '-> Kraken', ls.KRAKEN)
    print('pUSD %.2f  USDC.e %.2f  USDC %.2f' % (ls.balance(rpc, ls.PUSD, me) / 1e6, ls.balance(rpc, ls.USDCE, me) / 1e6,
                                                ls.balance(rpc, ls.USDC, me) / 1e6))
    print('plan: %.2f pUSD -> USDC.e -> USDC -> Kraken (about %.2f arrives)' % (amount, amount * 0.9998))
    if not send_on:
        print('nothing sent; add --send to do it')
        return

    def send(label, to, data):
        nonce = int(rpc('eth_getTransactionCount', [me, 'pending']), 16)
        gas = int(rpc('eth_estimateGas', [{'from': me, 'to': to, 'data': data}]), 16)   # reverts here if it would fail
        base = int(rpc('eth_gasPrice', []), 16)
        signed = acct.sign_transaction({'to': to, 'data': data, 'value': 0, 'gas': int(gas * 1.3), 'nonce': nonce, 'chainId': 137,
                                        'maxFeePerGas': base * 2, 'maxPriorityFeePerGas': max(30_000_000_000, base // 4), 'type': 2})
        raw = signed.raw_transaction.hex()
        h = rpc('eth_sendRawTransaction', [raw if raw.startswith('0x') else '0x' + raw])
        for _ in range(60):
            time.sleep(3)
            receipt = rpc('eth_getTransactionReceipt', [h])
            if receipt:
                ok = int(receipt['status'], 16) == 1
                print('  %-28s %s https://polygonscan.com/tx/%s' % (label, 'CONFIRMED' if ok else 'FAILED', h))
                if not ok:
                    raise SystemExit('stopped: %s failed (run again, it resumes)' % label)
                return h
        raise SystemExit('stopped: %s not mined in 3 min (run again, it resumes)' % label)

    pending = ls.Pending(os.path.join(ROOT, 'data', 'sweep_pending.json'))
    job = ls.run(rpc, send, me, int(amount * 1_000_000), pending)
    with open(os.path.join(ROOT, 'logs', 'live-sweeps.jsonl'), 'a') as f:
        f.write(json.dumps(dict(job, at=time.time(), test=True)) + '\n')
    print('done. Check Kraken: %.2f USDC should arrive in a few minutes.' % (job['sent_micro'] / 1e6))


if __name__ == '__main__':
    main()
