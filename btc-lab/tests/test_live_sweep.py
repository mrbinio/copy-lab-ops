import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from lab import live_sweep as ls


class Chain:
    """Balances and allowances of one wallet; transactions move them."""

    def __init__(self, me, pusd, usdce=0, usdc=0):
        self.me = me
        self.bal = {ls.PUSD: pusd, ls.USDCE: usdce, ls.USDC: usdc}
        self.allow = {}
        self.sent = []
        self.fail = None
        self.to_kraken = 0

    def rpc(self, method, params):
        call = params[0]
        data = bytes.fromhex(call['data'][2:])
        if data[:4] == bytes.fromhex(ls._data('balanceOf(address)', ['address'], [self.me])[2:10]):
            return hex(self.bal[call['to']])
        owner_spender = data[4:]
        spender = '0x' + owner_spender[44:64].hex()
        return hex(self.allow.get((call['to'], spender.lower()), 0))

    def send(self, label, to, data):
        if self.fail == label:
            raise RuntimeError('failed: ' + label)
        self.sent.append(label)
        raw = bytes.fromhex(data[2:])
        from eth_abi import decode
        if label.startswith('approve'):
            spender, amount = decode(['address', 'uint256'], raw[4:])
            self.allow[(to, spender.lower())] = amount
        elif label.startswith('unwrap'):
            _, _, amount = decode(['address', 'address', 'uint256'], raw[4:])
            self.bal[ls.PUSD] -= amount
            self.bal[ls.USDCE] += amount
        elif label.startswith('swap'):
            (_, _, _, _, amount, minimum, _), = decode(['(address,address,uint24,address,uint256,uint256,uint160)'], raw[4:])
            self.bal[ls.USDCE] -= amount
            self.bal[ls.USDC] += amount * 9998 // 10000
        elif label.startswith('send'):
            dest, amount = decode(['address', 'uint256'], raw[4:])
            assert dest.lower() == ls.KRAKEN.lower()
            self.bal[ls.USDC] -= amount
            self.to_kraken += amount
        return '0x' + str(len(self.sent))


ME = '0x' + '11' * 20


class SweepTests(unittest.TestCase):
    def test_amount_rules(self):
        self.assertIsNone(ls.sweep_amount(110, 100, 50, Decimal('1')))       # something in play
        self.assertIsNone(ls.sweep_amount(104, 100, 50, 0))                  # under 5 USD
        self.assertEqual(ls.sweep_amount(130, 100, 50, 0), Decimal('30.00'))
        self.assertEqual(ls.sweep_amount(340, 100, 12.345, 0), Decimal('12.34'))   # a deposit never leaves

    def test_a_sweep_moves_only_its_own_money_to_kraken(self):
        with tempfile.TemporaryDirectory() as tmp:
            chain = Chain(ME, pusd=130_000_000, usdce=7_000_000, usdc=50_000_000)   # deposits waiting
            job = ls.run(chain.rpc, chain.send, ME, 20_000_000, ls.Pending(Path(tmp) / 'p.json'), log=lambda *_: None)
            self.assertEqual(job['stage'], 'done')
            self.assertEqual(chain.to_kraken, 20_000_000 * 9998 // 10000)
            self.assertEqual(chain.bal[ls.USDCE], 7_000_000)
            self.assertEqual(chain.bal[ls.USDC], 50_000_000)
            self.assertEqual(chain.bal[ls.PUSD], 110_000_000)

    def test_a_failed_step_resumes_without_unwrapping_twice(self):
        with tempfile.TemporaryDirectory() as tmp:
            pending = ls.Pending(Path(tmp) / 'p.json')
            chain = Chain(ME, pusd=130_000_000)
            chain.fail = 'send USDC -> Kraken'
            with self.assertRaises(RuntimeError):
                ls.run(chain.rpc, chain.send, ME, 20_000_000, pending, log=lambda *_: None)
            self.assertEqual(pending.load()['stage'], 'transfer')
            chain.fail = None
            ls.run(chain.rpc, chain.send, ME, 20_000_000, pending, log=lambda *_: None)
            self.assertEqual(chain.sent.count('unwrap pUSD -> USDC.e'), 1)
            self.assertEqual(chain.bal[ls.PUSD], 110_000_000)
            self.assertIsNone(pending.load())

    def test_automatic_sweeps_wait_for_the_confirmed_test(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'data').mkdir()
            live = type('L', (), {'root': root})()
            sweeper = ls.LiveSweeper(live)
            self.assertIsNone(sweeper.cycle({'mode': 'live', 'desk_line_usd': Decimal(100)}, {'pusd': 200}))
            (root / 'data' / 'sweep_ok.json').write_text(json.dumps({'kraken_confirmed': True}))
            self.assertTrue(sweeper.allowed())
            self.assertIsNone(sweeper.cycle({'mode': 'dry', 'desk_line_usd': Decimal(100)}, {'pusd': 200}))
            (root / 'logs').mkdir()
            (root / 'logs' / 'live-sweeps.jsonl').write_text(
                json.dumps({'stage': 'done', 'test': True, 'sent_micro': 2999406, 'amount_micro': 3000000}) + '\n')
            self.assertEqual(sweeper.swept_usd(), 0)                         # the test is not profit
            self.assertEqual(sweeper.unswept_profit([]), 0)


if __name__ == '__main__':
    unittest.main()
