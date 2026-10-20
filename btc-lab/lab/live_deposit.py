"""Deposits for the Mitch live mirror go into play by themselves (Damian, 19 Oct
2026: he is not always at the laptop to run tools/live_setup.py).

When USDC.e or native USDC lands in the wallet (from Kraken), the lab:
  native USDC -> USDC.e (Uniswap, 0.01% pool, at least 99.9% back)
  USDC.e -> pUSD (Polymarket CollateralOnramp.wrap)
then re-sizes the live limits by the agreed table (250 USD ceiling) and notes
it for Telegram. The money never leaves the wallet. Nothing runs while a
profit sweep is half done (its USDC.e/USDC must go to Kraken, not back in).
"""
import json
import logging
import time
from pathlib import Path

from .live_sweep import USDC, USDCE, PUSD, ROUTER, POOL_FEE, _data, allowance, balance

LOG = logging.getLogger(__name__)

ONRAMP = '0x93070a847efEf7F70739046A929D47a521F5B8ee'
EXCHANGE = '0xE111180000d2663C0091e4f400237545B87B996B'
MIN_DEPOSIT_MICRO = 1_000_000
EXCHANGE_ALLOWANCE = 300_000_000
DESK_CEILING = 250.0   # Damian's top amount, 19 Oct 2026


def sized_limits(desk, first_day=False):
    """The agreed table (19 Oct 2026): 165 USD -> 1/3 of PAPER, 8/50/33, desk stop 17;
    250 USD -> 1/2, 12/75/50, desk stop 25. Proportional in between, never above 250."""
    desk = min(float(desk), DESK_CEILING)
    r = lambda x: int(x + 0.5)
    return {'scale': '%.2f' % min(desk / 500, 0.5), 'max_order_usd': str(r(desk * 0.048)),
            'max_exposure_usd': str(r(desk * 0.3)),
            'day_loss_stop_usd': str(r(desk * 0.1) if first_day else r(desk * 0.2)),
            'desk_stop_usd': str(r(desk * 0.1))}


def wrap_deposit(rpc, send, me):
    """Put waiting USDC / USDC.e into play as pUSD. Returns pUSD added (micro) or 0."""
    usdc = balance(rpc, USDC, me)
    if usdc >= MIN_DEPOSIT_MICRO:
        if allowance(rpc, USDC, me, ROUTER) < usdc:
            send('approve USDC -> Uniswap', USDC, _data('approve(address,uint256)', ['address', 'uint256'], [ROUTER, usdc]))
        send('swap USDC -> USDC.e', ROUTER, _data(
            'exactInputSingle((address,address,uint24,address,uint256,uint256,uint160))',
            ['(address,address,uint24,address,uint256,uint256,uint160)'],
            [(USDC, USDCE, POOL_FEE, me, usdc, usdc * 999 // 1000, 0)]))
    usdce = balance(rpc, USDCE, me)
    if usdce < MIN_DEPOSIT_MICRO:
        return 0
    if allowance(rpc, USDCE, me, ONRAMP) < usdce:
        send('approve USDC.e -> onramp', USDCE, _data('approve(address,uint256)', ['address', 'uint256'], [ONRAMP, usdce]))
    before = balance(rpc, PUSD, me)
    send('wrap USDC.e -> pUSD', ONRAMP, _data('wrap(address,address,uint256)', ['address', 'address', 'uint256'], [USDCE, me, usdce]))
    added = balance(rpc, PUSD, me) - before
    if allowance(rpc, PUSD, me, EXCHANGE) < EXCHANGE_ALLOWANCE // 2:
        send('approve pUSD -> exchange', PUSD, _data('approve(address,uint256)', ['address', 'uint256'], [EXCHANGE, EXCHANGE_ALLOWANCE]))
    return added


class LiveDeposits:
    """Called once a minute by the worker, after the sweep, in live mode."""

    def __init__(self, live):
        self.live = live
        self.root = Path(live.root)
        self.journal = self.root / 'logs' / 'live-deposits.jsonl'
        self.config = self.root / 'data' / 'mitch_live.json'

    def cycle(self, settings, wallet):
        if settings.get('mode') != 'live' or not wallet:
            return None
        dw = wallet.get('deposit_wallet')
        waiting = float(wallet.get('waiting_usdc') or 0) >= MIN_DEPOSIT_MICRO / 1e6
        bank = bool(dw) and float(wallet.get('bank_pusd') or 0) >= MIN_DEPOSIT_MICRO / 1e6
        if not waiting and not bank:
            return None
        if (self.root / 'data' / 'sweep_pending.json').exists():
            return None   # a half-done sweep owns the USDC.e / USDC / pUSD in the wallet
        row = {'at': time.time()}
        send = lambda label, to, data: self.live.send_tx(to, data)
        try:
            added = wrap_deposit(self.live._rpc, send, self.live.address()) if waiting else 0
            if dw:
                # 20 Oct 2026: trading pUSD lives in the Deposit Wallet; move the
                # signer's pUSD there (the signer pays the gas in POL).
                me = self.live.address()
                moved = balance(self.live._rpc, PUSD, me)
                if moved >= MIN_DEPOSIT_MICRO:
                    send('move pUSD -> deposit wallet', PUSD,
                         _data('transfer(address,uint256)', ['address', 'uint256'], [dw, moved]))
                    added = max(added, moved)
                row['moved_micro'] = moved
            row.update(stage='done', added_micro=added)
            self.live._wallet = None            # read the new balance now
            fresh = self.live.wallet() or {}
            if added > 0 and fresh.get('pusd') is not None:
                row['limits'] = self.resize(float(fresh['pusd']) + float(self.live.exposure_usd()))
        except Exception as error:
            LOG.warning('deposit: %s', str(error)[:300])
            row.update(stage='error', error=str(error)[:300])
        self._journal(row)
        return row

    def resize(self, desk):
        config = json.loads(self.config.read_text())
        today = time.strftime('%Y-%m-%d', time.localtime(self.live.clock()))
        new = sized_limits(desk, first_day=config.get('first_day') == today)
        old = {k: config.get(k) for k in new}
        config.update(new, sized_at=time.time(), sized_for_usd=round(min(desk, DESK_CEILING), 2))
        tmp = self.config.with_suffix('.tmp')
        tmp.write_text(json.dumps(config))
        tmp.replace(self.config)
        LOG.warning('live limits re-sized for %.2f USD: %s -> %s', desk, old, new)
        return {'desk': round(min(desk, DESK_CEILING), 2), 'old': old, 'new': new}

    def recent(self, limit=5):
        rows = []
        try:
            for line in self.journal.read_text().splitlines()[-100:]:
                rows.append(json.loads(line))
        except (OSError, ValueError):
            pass
        return rows[::-1][:limit]

    def _journal(self, row):
        self.journal.parent.mkdir(parents=True, exist_ok=True)
        with open(self.journal, 'a') as f:
            f.write(json.dumps(row) + '\n')
