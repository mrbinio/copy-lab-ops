"""Profit sweep for the Mitch live mirror (Damian, 17-19 Oct 2026).

Live profit above the desk line goes to Damian's Kraken USDC deposit address
on Polygon, in batches of at least 5 USD:
  pUSD -> USDC.e (Polymarket CollateralOfframp.unwrap)
       -> native USDC (Uniswap, 0.01% pool, at least 99.9% back)
       -> transfer to Kraken.

Safety:
- the destination is fixed in code; no config can change it;
- only live profit that was not swept yet can leave, so a deposit never does;
- only what this sweep unwrapped is swapped and sent (a fresh deposit of
  USDC.e or USDC in the wallet is left alone); a half-done sweep resumes
  from data/sweep_pending.json;
- automatic sweeps need data/sweep_ok.json with kraken_confirmed true,
  written after Damian's test transfer arrived on Kraken.
"""
import json
import logging
import time
from decimal import Decimal, ROUND_DOWN
from pathlib import Path

LOG = logging.getLogger(__name__)

KRAKEN = '0xcFf015f1C22bfFE66529d5F8967ADbeDf5E95396'   # Damian's Kraken USDC (Polygon) deposit
PUSD = '0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB'
USDCE = '0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174'
USDC = '0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359'
OFFRAMP = '0x2957922Eb93258b93368531d39fAcCA3B4dC5854'
ROUTER = '0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45'    # Uniswap SwapRouter02
POOL_FEE = 100                                           # 0.01%
MIN_SWEEP_USD = Decimal('5')


def _data(sig, types, args):
    from eth_abi import encode
    from eth_utils import keccak
    return '0x' + (keccak(text=sig)[:4] + encode(types, args)).hex()


def balance(rpc, token, who):
    return int(rpc('eth_call', [{'to': token, 'data': _data('balanceOf(address)', ['address'], [who])}, 'latest']), 16)


def allowance(rpc, token, owner, spender):
    return int(rpc('eth_call', [{'to': token, 'data': _data('allowance(address,address)', ['address', 'address'],
                                                              [owner, spender])}, 'latest']), 16)


def sweep_amount(pusd, line, unswept_profit, in_play):
    """USD to sweep now, or None. Only when nothing is in play, only above the
    line and never more than the live profit not swept yet."""
    if in_play > 0:
        return None
    amount = min(Decimal(str(pusd)) - Decimal(str(line)), Decimal(str(unswept_profit)))
    amount = amount.quantize(Decimal('0.01'), rounding=ROUND_DOWN)
    return amount if amount >= MIN_SWEEP_USD else None


class Pending:
    """What a sweep moved so far, so a crash or a failed step resumes."""

    def __init__(self, path):
        self.path = Path(path)

    def load(self):
        try:
            return json.loads(self.path.read_text())
        except (OSError, ValueError):
            return None

    def save(self, body):
        tmp = self.path.with_suffix('.tmp')
        tmp.write_text(json.dumps(body))
        tmp.replace(self.path)

    def clear(self):
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


def run(rpc, send, me, amount_micro, pending, log=print):
    """Do (or resume) one sweep. send(label, to, data) signs, sends and waits
    for the receipt, raising on failure. Returns the finished sweep."""
    job = pending.load() or {'started': time.time(), 'amount_micro': int(amount_micro), 'stage': 'unwrap'}
    if job['stage'] == 'unwrap':
        amount = job['amount_micro']
        if balance(rpc, PUSD, me) < amount:
            raise RuntimeError('pUSD below the sweep amount')
        if allowance(rpc, PUSD, me, OFFRAMP) < amount:
            send('approve pUSD -> offramp', PUSD, _data('approve(address,uint256)', ['address', 'uint256'], [OFFRAMP, amount]))
        before = balance(rpc, USDCE, me)
        job['unwrap_tx'] = send('unwrap pUSD -> USDC.e', OFFRAMP, _data(
            'unwrap(address,address,uint256)', ['address', 'address', 'uint256'], [USDCE, me, amount]))
        job['usdce_micro'] = balance(rpc, USDCE, me) - before
        if job['usdce_micro'] <= 0:
            raise RuntimeError('unwrap gave no USDC.e')
        job['stage'] = 'swap'
        pending.save(job)
    if job['stage'] == 'swap':
        amount = min(job['usdce_micro'], balance(rpc, USDCE, me))
        if allowance(rpc, USDCE, me, ROUTER) < amount:
            send('approve USDC.e -> Uniswap', USDCE, _data('approve(address,uint256)', ['address', 'uint256'], [ROUTER, amount]))
        before = balance(rpc, USDC, me)
        job['swap_tx'] = send('swap USDC.e -> USDC', ROUTER, _data(
            'exactInputSingle((address,address,uint24,address,uint256,uint256,uint160))',
            ['(address,address,uint24,address,uint256,uint256,uint160)'],
            [(USDCE, USDC, POOL_FEE, me, amount, amount * 999 // 1000, 0)]))
        job['usdc_micro'] = balance(rpc, USDC, me) - before
        if job['usdc_micro'] <= 0:
            raise RuntimeError('swap gave no USDC')
        job['stage'] = 'transfer'
        pending.save(job)
    if job['stage'] == 'transfer':
        amount = min(job['usdc_micro'], balance(rpc, USDC, me))
        job['transfer_tx'] = send('send USDC -> Kraken', USDC, _data(
            'transfer(address,uint256)', ['address', 'uint256'], [KRAKEN, amount]))
        job['sent_micro'] = amount
        job['stage'] = 'done'
        job['finished'] = time.time()
        pending.clear()
    log('sweep done: %.2f USDC to Kraken (%s)' % (job['sent_micro'] / 1e6, job['transfer_tx']))
    return job


class LiveSweeper:
    """Called once a minute by the worker with the live mirror."""

    def __init__(self, live):
        self.live = live
        self.root = Path(live.root)
        self.pending = Pending(self.root / 'data' / 'sweep_pending.json')
        self.journal = self.root / 'logs' / 'live-sweeps.jsonl'

    def allowed(self):
        try:
            return json.loads((self.root / 'data' / 'sweep_ok.json').read_text()).get('kraken_confirmed') is True
        except (OSError, ValueError):
            return False

    def done(self):
        rows = []
        try:
            for line in self.journal.read_text().splitlines():
                row = json.loads(line)
                if row.get('stage') == 'done':
                    rows.append(row)
        except (OSError, ValueError):
            pass
        return rows

    def swept_usd(self):
        return sum((Decimal(int(r.get('sent_micro') or 0)) / Decimal(1_000_000) for r in self.done()), Decimal(0))

    def unswept_profit(self, rows):
        """Realized profit of real (filled) live buys minus what already left.
        The amount that left counts at its pUSD value, before the swap cost."""
        profit = sum((Decimal(r.get('pnl_usd') or '0') for r in rows
                      if r.get('closed') and r.get('status') == 'FILLED'), Decimal(0))
        out = sum((Decimal(int(r.get('amount_micro') or 0)) / Decimal(1_000_000) for r in self.done()), Decimal(0))
        return profit - out

    def cycle(self, settings, wallet):
        if settings.get('mode') != 'live' or not self.allowed():
            return None
        line = settings.get('desk_line_usd')
        if line is None or not wallet or wallet.get('pusd') is None:
            return None
        rows = self.live._rows()
        job = self.pending.load()
        if job is None:
            amount = sweep_amount(wallet['pusd'], line, self.unswept_profit(rows), self.live.exposure_usd(rows))
            if amount is None:
                return None
            amount_micro = int(amount * 1_000_000)
        else:
            amount_micro = job['amount_micro']
        try:
            job = run(self.live._rpc, lambda label, to, data: self.live.send_tx(to, data),
                      self.live.address(), amount_micro, self.pending, log=LOG.info)
        except Exception as error:
            LOG.warning('sweep: %s', str(error)[:300])
            self._journal({'at': time.time(), 'stage': 'error', 'amount_micro': amount_micro, 'error': str(error)[:300]})
            return None
        self._journal(dict(job, at=time.time()))
        return job

    def _journal(self, row):
        self.journal.parent.mkdir(parents=True, exist_ok=True)
        with open(self.journal, 'a') as f:
            f.write(json.dumps(row) + '\n')
