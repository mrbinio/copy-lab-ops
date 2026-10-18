"""One-time wallet setup for the Mitch live mirror (Damian's consent, 17 Oct 2026).
native USDC -> USDC.e (Uniswap, 0.01% pool) -> pUSD (Polymarket onramp), then
approvals for the CLOB V2 exchange. No order is placed. Each step is simulated
first, then sent, then checked. The key is read from the owner-only file and
never printed. Usage: live_setup.py <key file> [--send]"""
import json, sys, time, urllib.error, urllib.request
from eth_abi import encode
from eth_account import Account
from eth_utils import keccak, to_checksum_address

# 17 Oct 2026: drpc answered 429 mid-setup (the lab uses it all day); a
# second public node takes over.
RPCS = ('https://polygon-bor-rpc.publicnode.com', 'https://polygon.drpc.org')
ME_EXPECTED = '0xEb1FA4A1AFA2138Bba3B106E4a56778236a3bF01'
USDC = '0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359'
USDCE = '0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174'
PUSD = '0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB'
ROUTER = '0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45'   # Uniswap SwapRouter02
ONRAMP = '0x93070a847efEf7F70739046A929D47a521F5B8ee'
EXCHANGE_V2 = '0xE111180000d2663C0091e4f400237545B87B996B'
CTF = '0x4D97DCd97eC945f40cF65F87097ACe5EA0476045'
CTF_ADAPTER = '0xAdA100Db00Ca00073811820692005400218FcE1f'   # redeems winnings to pUSD (V2)
ALLOW_PUSD = 200_000_000  # 200 pUSD (desk line 100, agreed 17 Oct), not unlimited


def rpc(method, params):
    last = None
    for attempt in range(6):
        url = RPCS[attempt % len(RPCS)]
        req = urllib.request.Request(url, data=json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params}).encode(),
                                     headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'})
        try:
            reply = json.load(urllib.request.urlopen(req, timeout=20))
            break
        except urllib.error.URLError as error:
            last = error
            time.sleep(2)
    else:
        raise RuntimeError('%s: no node answered (%s)' % (method, last))
    if 'error' in reply:
        raise RuntimeError('%s: %s' % (method, reply['error']))
    return reply['result']


def sel(sig):
    return keccak(text=sig)[:4]


def data(sig, types, args):
    return '0x' + (sel(sig) + encode(types, args)).hex()


def balance(token, who):
    return int(rpc('eth_call', [{'to': token, 'data': data('balanceOf(address)', ['address'], [who])}, 'latest']), 16)


def allowance(token, owner, spender):
    return int(rpc('eth_call', [{'to': token, 'data': data('allowance(address,address)', ['address', 'address'], [owner, spender])}, 'latest']), 16)


def main():
    key = open(sys.argv[1]).read().strip()
    acct = Account.from_key(key)
    del key
    me = acct.address
    assert me == ME_EXPECTED, 'key does not open the expected wallet'
    send = '--send' in sys.argv
    print('wallet', me, 'POL', int(rpc('eth_getBalance', [me, 'latest']), 16) / 1e18)
    usdc = balance(USDC, me)
    print('USDC', usdc / 1e6, 'USDC.e', balance(USDCE, me) / 1e6, 'pUSD', balance(PUSD, me) / 1e6)

    def tx(label, to, payload):
        nonce = int(rpc('eth_getTransactionCount', [me, 'pending']), 16)
        call = {'from': me, 'to': to, 'data': payload}
        # Simulation: reverts here if it would fail. 17 Oct 2026: the node that
        # answered had not seen the approve confirmed seconds earlier, so the
        # swap is retried a few times before it counts as a real revert.
        for attempt in range(5):
            try:
                gas = int(rpc('eth_estimateGas', [call]), 16)
                break
            except RuntimeError:
                if attempt == 4:
                    raise
                time.sleep(4)
        base = int(rpc('eth_gasPrice', []), 16)
        tip = max(30_000_000_000, base // 4)
        print('  %-28s simulated ok, gas %d, max fee %.0f gwei' % (label, gas, base * 2 / 1e9))
        if not send:
            return None
        signed = acct.sign_transaction({'to': to, 'data': payload, 'value': 0, 'gas': int(gas * 1.3), 'nonce': nonce,
                                        'chainId': 137, 'maxFeePerGas': base * 2, 'maxPriorityFeePerGas': tip, 'type': 2})
        h = rpc('eth_sendRawTransaction', ['0x' + signed.raw_transaction.hex().removeprefix('0x')])
        for _ in range(90):
            time.sleep(2)
            receipt = rpc('eth_getTransactionReceipt', [h])
            if receipt:
                ok = int(receipt['status'], 16) == 1
                print('  %-28s %s https://polygonscan.com/tx/%s' % (label, 'CONFIRMED' if ok else 'FAILED', h))
                if not ok:
                    raise SystemExit('stopped: %s failed' % label)
                time.sleep(6)   # let every node see the new state
                return h
        raise SystemExit('stopped: %s not mined in 3 min (%s)' % (label, h))

    # 1-2: native USDC -> USDC.e on the 0.01% pool, at least 99.9% back
    if usdc > 0:
        if allowance(USDC, me, ROUTER) < usdc:
            tx('approve USDC -> Uniswap', USDC, data('approve(address,uint256)', ['address', 'uint256'], [ROUTER, usdc]))
        if send or allowance(USDC, me, ROUTER) >= usdc:
            tx('swap USDC -> USDC.e', ROUTER, data('exactInputSingle((address,address,uint24,address,uint256,uint256,uint160))',
               ['(address,address,uint24,address,uint256,uint256,uint160)'],
               [(USDC, USDCE, 100, me, usdc, usdc * 999 // 1000, 0)]))
        else:
            print('  swap USDC -> USDC.e          simulated after the approve (needs it on chain first)')
    usdce = balance(USDCE, me)
    # 3-4: USDC.e -> pUSD through the official onramp
    if usdce > 0:
        if allowance(USDCE, me, ONRAMP) < usdce:
            tx('approve USDC.e -> onramp', USDCE, data('approve(address,uint256)', ['address', 'uint256'], [ONRAMP, usdce]))
        if send or allowance(USDCE, me, ONRAMP) >= usdce:
            tx('wrap USDC.e -> pUSD', ONRAMP, data('wrap(address,address,uint256)', ['address', 'address', 'uint256'], [USDCE, me, usdce]))
    # 5-6: the exchange may spend pUSD (capped) and move our outcome shares (to sell)
    if allowance(PUSD, me, EXCHANGE_V2) < ALLOW_PUSD // 2:
        tx('approve pUSD -> exchange', PUSD, data('approve(address,uint256)', ['address', 'uint256'], [EXCHANGE_V2, ALLOW_PUSD]))
    approved = int(rpc('eth_call', [{'to': CTF, 'data': data('isApprovedForAll(address,address)', ['address', 'address'], [me, EXCHANGE_V2])}, 'latest']), 16)
    if not approved:
        tx('approve shares -> exchange', CTF, data('setApprovalForAll(address,bool)', ['address', 'bool'], [EXCHANGE_V2, True]))
    approved = int(rpc('eth_call', [{'to': CTF, 'data': data('isApprovedForAll(address,address)', ['address', 'address'], [me, CTF_ADAPTER])}, 'latest']), 16)
    if not approved:
        tx('approve shares -> redeemer', CTF, data('setApprovalForAll(address,bool)', ['address', 'bool'], [CTF_ADAPTER, True]))
    print('after: POL', int(rpc('eth_getBalance', [me, 'latest']), 16) / 1e18, 'USDC', balance(USDC, me) / 1e6,
          'USDC.e', balance(USDCE, me) / 1e6, 'pUSD', balance(PUSD, me) / 1e6,
          'pUSD allowance', allowance(PUSD, me, EXCHANGE_V2) / 1e6)


if __name__ == '__main__':
    main()
