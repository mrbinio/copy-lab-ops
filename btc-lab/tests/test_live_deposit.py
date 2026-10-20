import tempfile
import unittest
from pathlib import Path

from lab import live_deposit as ld
from lab import live_sweep as ls

ME = '0x' + '22' * 20


class Chain:
    def __init__(self, usdc=0, usdce=0, pusd=0):
        self.bal = {ls.USDC: usdc, ls.USDCE: usdce, ls.PUSD: pusd}
        self.allow = {}
        self.sent = []

    def rpc(self, method, params):
        call = params[0]
        data = bytes.fromhex(call['data'][2:])
        if len(data) == 36:
            return hex(self.bal[call['to']])
        return hex(self.allow.get((call['to'], '0x' + data[48:68].hex()), 0))

    def send(self, label, to, data):
        from eth_abi import decode
        raw = bytes.fromhex(data[2:])
        self.sent.append(label)
        if label.startswith('approve'):
            spender, amount = decode(['address', 'uint256'], raw[4:])
            self.allow[(to, spender.lower())] = amount
        elif label.startswith('swap'):
            (src, dst, _, who, amount, minimum, _), = decode(['(address,address,uint24,address,uint256,uint256,uint160)'], raw[4:])
            assert who.lower() == ME
            self.bal[ls.USDC] -= amount
            self.bal[ls.USDCE] += amount * 9998 // 10000
        elif label.startswith('wrap'):
            _, who, amount = decode(['address', 'address', 'uint256'], raw[4:])
            assert who.lower() == ME                      # the money stays in the wallet
            self.bal[ls.USDCE] -= amount
            self.bal[ls.PUSD] += amount
        return '0x1'


class DepositTests(unittest.TestCase):
    def test_usdce_from_kraken_goes_into_play(self):
        chain = Chain(usdce=80_000_000, pusd=168_000_000)
        added = ld.wrap_deposit(chain.rpc, chain.send, ME)
        self.assertEqual(added, 80_000_000)
        self.assertEqual(chain.bal[ls.PUSD], 248_000_000)
        self.assertIn('approve pUSD -> exchange', chain.sent)

    def test_native_usdc_is_swapped_first(self):
        chain = Chain(usdc=50_000_000)
        added = ld.wrap_deposit(chain.rpc, chain.send, ME)
        self.assertEqual(added, 50_000_000 * 9998 // 10000)
        self.assertEqual(chain.bal[ls.USDC], 0)

    def test_dust_is_left_alone(self):
        chain = Chain(usdce=500_000)
        self.assertEqual(ld.wrap_deposit(chain.rpc, chain.send, ME), 0)
        self.assertEqual(chain.sent, [])

    def test_table(self):
        self.assertEqual(ld.sized_limits(165), {'scale': '0.33', 'max_order_usd': '8', 'max_exposure_usd': '50',
                                                'day_loss_stop_usd': '33', 'desk_stop_usd': '17'})
        self.assertEqual(ld.sized_limits(400)['max_order_usd'], '12')            # 250 ceiling
        self.assertEqual(ld.sized_limits(165, first_day=True)['day_loss_stop_usd'], '17')

    def test_signer_pusd_moves_to_the_deposit_wallet(self):
        import json
        dw = '0x' + '33' * 20
        chain = Chain(usdce=20_000_000, pusd=4_000_000)
        sent = []

        def send_tx(to, data):
            from eth_abi import decode
            raw = bytes.fromhex(data[2:])
            if raw[:4] == bytes.fromhex(ls._data('transfer(address,uint256)', ['address', 'uint256'], [dw, 1])[2:10]):
                dest, amount = decode(['address', 'uint256'], raw[4:])
                sent.append((dest.lower(), amount))
                chain.bal[ls.PUSD] -= amount
                return '0x1'
            label = {ld.ONRAMP.lower(): 'wrap USDC.e -> pUSD'}.get(to.lower(), 'approve x')
            return chain.send(label, to, data)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'data').mkdir()
            (root / 'data' / 'mitch_live.json').write_text(json.dumps({'mode': 'live'}))
            live = type('L', (), {'root': root, '_rpc': staticmethod(chain.rpc), 'send_tx': staticmethod(send_tx),
                                  'address': staticmethod(lambda: ME), 'wallet': staticmethod(lambda: {}),
                                  'exposure_usd': staticmethod(lambda: 0), 'clock': staticmethod(lambda: 0),
                                  '_wallet': None})()
            row = ld.LiveDeposits(live).cycle({'mode': 'live'}, {'waiting_usdc': 20, 'bank_pusd': 4, 'deposit_wallet': dw})
            self.assertEqual(row['stage'], 'done')
            self.assertEqual(sent, [(dw, 24_000_000)])          # the deposit and the signer's pUSD, all in play
            self.assertEqual(chain.bal[ls.PUSD], 0)

    def test_nothing_while_a_sweep_is_half_done(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'data').mkdir()
            (root / 'data' / 'sweep_pending.json').write_text('{}')
            live = type('L', (), {'root': root})()
            self.assertIsNone(ld.LiveDeposits(live).cycle({'mode': 'live'}, {'waiting_usdc': 50}))
            self.assertIsNone(ld.LiveDeposits(live).cycle({'mode': 'dry'}, {'waiting_usdc': 50}))


if __name__ == '__main__':
    unittest.main()
