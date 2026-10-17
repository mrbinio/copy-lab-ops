"""Real-money mirror of Mitch's PAPER desk. Polymarket CLOB V2, BTC 15m only.

Damian, 17 Oct 2026: Mitch's strategy goes to real USDC; his own wallet
strategy stays PAPER. The live side takes the same decisions as the PAPER
desk at the same moment: every PAPER copy (buy or sell) is mirrored here with
the same price cap. Only the size differs: each buy is the market minimum
while the wallet holds about 10 USDC, so the live result can be compared with
PAPER trade by trade.

Modes, from data/mitch_live.json:
  off  - nothing happens (default)
  dry  - the order is built and signed with the real key, never posted
  live - the order is posted; also needs live_gate.LIVE_ORDERS_ALLOWED

The key is read from secrets/polygon.key (owner-only file). It is never
logged, printed or stored anywhere else.
"""
import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from pathlib import Path

LOG = logging.getLogger('btc-lab.live')
CLOB = 'https://clob.polymarket.com'
CHAIN_ID = 137
MODES = ('off', 'dry', 'live')
# Hard limits for the test wallet. A config file may lower them, never raise.
# The market minimum is 5 shares on BTC 15m, about 2.5 USD near 50 cents.
MAX_ORDER_USD = Decimal('3')
MAX_EXPOSURE_USD = Decimal('10')
DAY_LOSS_STOP_USD = Decimal('5')
MIN_MARKET_BUY_USD = Decimal('1')
POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix='lab-live')
PUSD = '0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB'
WALLET_RPCS = ('https://polygon-bor-rpc.publicnode.com', 'https://polygon.drpc.org')


def ensure(db):
    db.execute('CREATE TABLE IF NOT EXISTS mitch_live_orders (id TEXT PRIMARY KEY, paper_key TEXT, body TEXT)')


def load_settings(root):
    try:
        raw = json.loads((Path(root) / 'data' / 'mitch_live.json').read_text())
    except (OSError, ValueError):
        raw = {}
    mode = raw.get('mode') if raw.get('mode') in MODES else 'off'

    def capped(name, ceiling):
        try:
            value = Decimal(str(raw.get(name, ceiling)))
        except Exception:
            return ceiling
        return min(value, ceiling) if value > 0 else ceiling
    return {
        'mode': mode,
        'max_order_usd': capped('max_order_usd', MAX_ORDER_USD),
        'max_exposure_usd': capped('max_exposure_usd', MAX_EXPOSURE_USD),
        'day_loss_stop_usd': capped('day_loss_stop_usd', DAY_LOSS_STOP_USD),
    }


def tick_floor(price, tick):
    tick = Decimal(str(tick))
    return (Decimal(str(price)) / tick).to_integral_value(rounding=ROUND_DOWN) * tick


def buy_amount(limit_price, min_shares, cap):
    """Dollars for one minimum buy at the cap price, or None when it does not fit the cap."""
    need = max(MIN_MARKET_BUY_USD, Decimal(str(min_shares or 0)) * Decimal(str(limit_price)))
    need = need.quantize(Decimal('0.01'), rounding=ROUND_UP)
    return need if need <= cap else None


class MitchLive:
    def __init__(self, store, root, clock=time.time, client_factory=None, pool=POOL):
        self.store = store
        self.root = Path(root)
        self.clock = clock
        self.pool = pool
        self._client_factory = client_factory or self._make_client
        self._client = None
        self._creds = False
        self._lock = threading.Lock()
        self._market_info = {}
        with store.connect() as db:
            ensure(db)

    # -- settings and safety ------------------------------------------------
    def settings(self):
        return load_settings(self.root)

    def key_path(self):
        return self.root / 'secrets' / 'polygon.key'

    def _make_client(self):
        from py_clob_client_v2.client import ClobClient
        from eth_account import Account
        key = self.key_path().read_text().strip()
        address = Account.from_key(key).address
        client = ClobClient(CLOB, chain_id=CHAIN_ID, key=key, signature_type=0, funder=address)
        del key
        return client

    def client(self):
        with self._lock:
            if self._client is None:
                self._client = self._client_factory()
            return self._client

    def _ensure_creds(self, client):
        """API credentials are derived from the key only when an order is posted."""
        if self._creds:
            return
        client.set_api_creds(client.create_or_derive_api_key())
        self._creds = True

    def _rows(self):
        with self.store.connect() as db:
            ensure(db)
            return [json.loads(b) for (b,) in db.execute('SELECT body FROM mitch_live_orders')]

    def exposure_usd(self, rows=None):
        rows = self._rows() if rows is None else rows
        return sum((Decimal(r.get('spent_usd') or '0') for r in rows
                    if r.get('status') == 'FILLED' and r.get('side') == 'BUY' and not r.get('closed')), Decimal(0))

    def day_loss_usd(self, rows=None):
        rows = self._rows() if rows is None else rows
        start = self.clock() - 86400
        return -sum((Decimal(r.get('pnl_usd') or '0') for r in rows
                     if r.get('closed') and float(r.get('closed_at') or 0) >= start), Decimal(0))

    def _save(self, row):
        with self.store.connect() as db:
            ensure(db)
            db.execute('INSERT OR REPLACE INTO mitch_live_orders VALUES (?,?,?)',
                       (row['id'], row.get('paper_key'), json.dumps(row)))

    def _min_shares(self, client, condition, token):
        hit = self._market_info.get(condition)
        if hit is None:
            info = client.get_clob_market_info(condition)
            hit = self._market_info[condition] = {'mos': info.get('mos'), 'tick': str(info.get('mts') or '0.01')}
            if len(self._market_info) > 200:
                self._market_info.pop(next(iter(self._market_info)))
        return hit

    # -- mirror of PAPER decisions -----------------------------------------
    def on_buy(self, wallet, paper_key, event, fill, limit_price, stopped=False):
        """Called right after a PAPER copy. Never blocks the PAPER path."""
        settings = self.settings()
        if settings['mode'] == 'off':
            return None
        job = {
            'id': 'live:' + paper_key[:24], 'paper_key': paper_key, 'wallet': wallet, 'side': 'BUY',
            'market': event.get('slug'), 'token': str(event.get('asset') or ''),
            'condition': event.get('conditionId'), 'source_price': str(event.get('price')),
            'source_ts': event.get('timestamp'), 'limit_price': str(limit_price),
            'paper_vwap': str(fill.get('vwap')), 'paper_cost_micro': fill.get('cost'),
            'decided_at': self.clock(), 'mode': settings['mode'], 'stopped': bool(stopped),
        }
        return self.pool.submit(self._buy, job, settings)

    def _buy(self, job, settings):
        started = self.clock()
        try:
            if job['stopped']:
                return self._finish(job, 'SKIPPED_STOP', started)
            rows = self._rows()
            if self.day_loss_usd(rows) >= settings['day_loss_stop_usd']:
                return self._finish(job, 'SKIPPED_DAY_LOSS_STOP', started)
            client = self.client()
            info = self._min_shares(client, job['condition'], job['token'])
            limit = tick_floor(min(Decimal(job['limit_price']), Decimal('0.99')), info['tick'])
            amount = buy_amount(limit, info['mos'], settings['max_order_usd'])
            if amount is None:
                return self._finish(job, 'SKIPPED_MIN_ABOVE_CAP', started, min_shares=info['mos'])
            if self.exposure_usd(rows) + amount > settings['max_exposure_usd']:
                return self._finish(job, 'SKIPPED_EXPOSURE_CAP', started, amount_usd=str(amount))
            from py_clob_client_v2.clob_types import MarketOrderArgsV2, OrderType
            order = client.create_market_order(MarketOrderArgsV2(
                token_id=job['token'], amount=float(amount), side='BUY', price=float(limit),
                order_type=OrderType.FOK))
            signed_at = self.clock()
            if settings['mode'] != 'live':
                return self._finish(job, 'DRY_SIGNED', started, amount_usd=str(amount),
                                    order_limit=str(limit), sign_ms=round((signed_at - started) * 1000, 1))
            from .live_gate import require_live
            require_live()
            self._ensure_creds(client)
            reply = client.post_order(order, OrderType.FOK)
            done = self.clock()
            ok = bool(reply and reply.get('success') and str(reply.get('status', '')).lower() in ('matched', 'mined', 'confirmed'))
            return self._finish(job, 'FILLED' if ok else 'NOT_FILLED', started, amount_usd=str(amount),
                                order_limit=str(limit), reply=_safe_reply(reply),
                                spent_usd=str(_spent(reply, amount)) if ok else '0',
                                shares=str(_shares(reply)) if ok else '0',
                                post_ms=round((done - signed_at) * 1000, 1))
        except Exception as error:
            LOG.warning('live buy %s: %s', job.get('paper_key', '')[:12], str(error)[:200])
            return self._finish(job, 'ERROR', started, error=str(error)[:300])

    def holding(self, wallet, token, rows=None):
        """Shares this mirror holds in a token for a wallet. In dry mode the signed
        buys count as held (shares = amount / limit), so sells are mirrored too."""
        rows = self._rows() if rows is None else rows
        held = Decimal(0)
        for r in rows:
            if r.get('wallet') != wallet or r.get('token') != token:
                continue
            if r.get('side') == 'BUY' and r.get('status') == 'FILLED':
                held += Decimal(r.get('shares') or '0')
            elif r.get('side') == 'BUY' and r.get('status') == 'DRY_SIGNED':
                held += (Decimal(r['amount_usd']) / Decimal(r['order_limit'])).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
            elif r.get('side') == 'SELL' and r.get('status') in ('FILLED', 'DRY_SIGNED'):
                held -= Decimal(r.get('shares') or '0')
        return max(held, Decimal(0))

    def on_sell(self, wallet, paper_key, event, fraction, floor_price):
        settings = self.settings()
        if settings['mode'] == 'off':
            return None
        job = {
            'id': 'live:' + paper_key[:24], 'paper_key': paper_key, 'wallet': wallet, 'side': 'SELL',
            'market': event.get('slug'), 'token': str(event.get('asset') or ''),
            'condition': event.get('conditionId'), 'source_price': str(event.get('price')),
            'source_ts': event.get('timestamp'), 'limit_price': str(floor_price), 'fraction': str(fraction),
            'decided_at': self.clock(), 'mode': settings['mode'], 'stopped': False,
        }
        return self.pool.submit(self._sell, job, settings)

    def _sell(self, job, settings):
        """Sells go on under STOP, like PAPER: STOP only blocks new buys."""
        started = self.clock()
        try:
            held = self.holding(job['wallet'], job['token'])
            shares = (held * Decimal(job['fraction'])).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
            if shares <= 0:
                return self._finish(job, 'SKIPPED_NOTHING_HELD', started)
            client = self.client()
            info = self._min_shares(client, job['condition'], job['token'])
            if Decimal(str(info['mos'] or 0)) > shares:
                return self._finish(job, 'HELD_BELOW_MIN', started, shares_wanted=str(shares), min_shares=info['mos'])
            floor = max(Decimal(str(info['tick'])), tick_floor(job['limit_price'], info['tick']))
            from py_clob_client_v2.clob_types import MarketOrderArgsV2, OrderType
            order = client.create_market_order(MarketOrderArgsV2(
                token_id=job['token'], amount=float(shares), side='SELL', price=float(floor),
                order_type=OrderType.FOK))
            signed_at = self.clock()
            if settings['mode'] != 'live':
                return self._finish(job, 'DRY_SIGNED', started, shares=str(shares), order_limit=str(floor),
                                    sign_ms=round((signed_at - started) * 1000, 1))
            from .live_gate import require_live
            require_live()
            self._ensure_creds(client)
            reply = client.post_order(order, OrderType.FOK)
            ok = bool(reply and reply.get('success') and str(reply.get('status', '')).lower() in ('matched', 'mined', 'confirmed'))
            return self._finish(job, 'FILLED' if ok else 'NOT_FILLED', started, shares=str(shares) if ok else '0',
                                order_limit=str(floor), reply=_safe_reply(reply),
                                post_ms=round((self.clock() - signed_at) * 1000, 1))
        except Exception as error:
            LOG.warning('live sell %s: %s', job.get('paper_key', '')[:12], str(error)[:200])
            return self._finish(job, 'ERROR', started, error=str(error)[:300])

    def _finish(self, job, status, started, **extra):
        row = dict(job, status=status, finished_at=self.clock(),
                   from_source_ms=round((self.clock() - float(job.get('source_ts') or started)) * 1000, 1),
                   **extra)
        self._save(row)
        LOG.info('live %s %s %s %s', row['mode'], row['side'], status, str(row.get('amount_usd', '')))
        return row

    def address(self):
        """The wallet's public address (derived once from the key file)."""
        if getattr(self, '_address', None) is None and self.key_path().exists():
            from eth_account import Account
            key = self.key_path().read_text().strip()
            self._address = Account.from_key(key).address
            del key
        return getattr(self, '_address', None)

    def wallet(self):
        """On-chain balances, read at most once a minute (public node first)."""
        now = self.clock()
        cached = getattr(self, '_wallet', None)
        if cached and now - cached['at'] < 55:
            return cached
        address = self.address()
        if not address:
            return None
        import urllib.request
        def call(method, params):
            last = None
            for url in WALLET_RPCS:
                try:
                    req = urllib.request.Request(url, data=json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params}).encode(),
                                                 headers={'Content-Type': 'application/json', 'User-Agent': 'BTC-Lab-Paper/0.1'})
                    return json.load(urllib.request.urlopen(req, timeout=8))['result']
                except Exception as error:
                    last = error
            raise RuntimeError(str(last)[:120])
        try:
            data = '0x70a08231' + address[2:].lower().rjust(64, '0')
            pusd = int(call('eth_call', [{'to': PUSD, 'data': data}, 'latest']), 16) / 1e6
            pol = int(call('eth_getBalance', [address, 'latest']), 16) / 1e18
            self._wallet = {'at': now, 'address': address, 'pusd': round(pusd, 6), 'pol': round(pol, 4)}
        except Exception as error:
            self._wallet = dict(cached or {'address': address}, at=now, error=str(error)[:120])
        return self._wallet

    def summary(self):
        rows = self._rows()
        settings = self.settings()
        counts = {}
        for r in rows:
            counts[r['status']] = counts.get(r['status'], 0) + 1
        recent = sorted(rows, key=lambda r: -float(r.get('finished_at') or 0))[:20]
        return {
            'at': self.clock(), 'mode': settings['mode'], 'key_present': self.key_path().exists(),
            'limits': {k: str(v) for k, v in settings.items() if k != 'mode'},
            'wallet': self.wallet(), 'counts': counts, 'exposure_usd': str(self.exposure_usd(rows)),
            'day_loss_usd': str(self.day_loss_usd(rows)), 'recent': recent,
        }


def _safe_reply(reply):
    if not isinstance(reply, dict):
        return {'raw': str(reply)[:200]}
    keep = ('success', 'status', 'orderID', 'errorMsg', 'makingAmount', 'takingAmount', 'transactionsHashes', 'tradeIDs')
    return {k: reply.get(k) for k in keep if k in reply}


def _spent(reply, amount):
    try:
        return Decimal(str(reply.get('makingAmount')))
    except Exception:
        return amount


def _shares(reply):
    try:
        return Decimal(str(reply.get('takingAmount')))
    except Exception:
        return Decimal(0)
