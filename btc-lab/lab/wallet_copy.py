"""Forward-only fixed-size wallet-signal copy with optional CLOB live orders."""
import asyncio
import copy
import json
import logging
import math
import re
import time
from datetime import datetime
from decimal import Decimal, ROUND_FLOOR
from urllib.parse import quote
from .core import VenueClock, simulate_fill
from .mid_window import simulate_sale
from .reference import classify_rule
from .wallet_observer import get_active_wallets, wallet_label
from .strategy_control import is_paused as copy_paused, pauses as copy_pauses
from .copy_totals import paper_board, summarize as copy_summarize, path_stats, path_record
from .wallet_watch import build_watch
from .copy_policy import POLICY, band_reason, confirmed_source_price, decide_buy, decide_sell, remember_fill

log = logging.getLogger(__name__)

class CopyLedgerError(ValueError):pass

KEY='wallet_copy_execution'
INITIAL=500_000_000
BUDGET=5_000_000  # hard cap; the ticket itself is one market minimum
# The whole open position, including later buys and fees, stays inside that budget.
POSITION_LIMIT=BUDGET
MAX_OPEN_POSITIONS=5
# Existing count cap times the existing position budget. Not a higher risk limit.
WALLET_LIMIT=MAX_OPEN_POSITIONS*POSITION_LIMIT
EXECUTION='copy-exec-v4'


def _event_size(event):
    raw=(event or {}).get('size')
    if raw in (None,''):
        return None
    try:
        size=Decimal(str(raw))
    except Exception:
        return None
    if not size.is_finite() or size<=0:
        return None
    return size


def ensure_source_schema(db):
    # executescript commits. Skip it once the tables exist so a later
    # BEGIN IMMEDIATE still covers the anchor and the events together.
    exists=db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='wallet_source_positions'"
    ).fetchone()
    if not exists:
        db.executescript('''
          CREATE TABLE IF NOT EXISTS wallet_source_positions(
            wallet TEXT, token TEXT, shares TEXT, known INTEGER NOT NULL,
            PRIMARY KEY(wallet, token));
          CREATE TABLE IF NOT EXISTS wallet_source_events(
            wallet TEXT, event_key TEXT, token TEXT, side TEXT, size TEXT,
            proportion TEXT, known INTEGER NOT NULL,
            PRIMARY KEY(wallet, event_key));
        ''')
    position_cols={row[1] for row in db.execute('PRAGMA table_info(wallet_source_positions)')}
    if 'as_of' not in position_cols:
        db.execute('ALTER TABLE wallet_source_positions ADD COLUMN as_of TEXT')
    if 'anchor_at' not in position_cols:
        db.execute('ALTER TABLE wallet_source_positions ADD COLUMN anchor_at TEXT')
    event_cols={row[1] for row in db.execute('PRAGMA table_info(wallet_source_events)')}
    if 'source_ts' not in event_cols:
        db.execute('ALTER TABLE wallet_source_events ADD COLUMN source_ts TEXT')
    if 'anchor_block' not in position_cols:
        db.execute('ALTER TABLE wallet_source_positions ADD COLUMN anchor_block TEXT')
    # A book marked known before any timed reading was opened by assuming zero.
    # That is not a confirmed inventory. The events stay.
    db.execute(
        """UPDATE wallet_source_positions SET known=0, shares=''
           WHERE known=1 AND (anchor_at IS NULL OR anchor_at='')""")


def _source_result(proportion, known, shares_before, shares_after, duplicate=False):
    return {
        'proportion': proportion,
        'known': bool(known),
        'shares_before': shares_before,
        'shares_after': shares_after,
        'duplicate': duplicate,
    }


def _stored_source(row):
    raw=row['proportion']
    proportion=Decimal(raw) if raw else None
    return _source_result(proportion, row['known'], None, None, duplicate=True)


def _dec(raw):
    if raw is None or raw=='':
        return None
    try:
        value=Decimal(str(raw))
    except Exception:
        return None
    if not value.is_finite():
        return None
    return value


def _insert_source_event(db, wallet, event_key, token, side, size, proportion, known, source_ts):
    db.execute(
        '''INSERT INTO wallet_source_events
           (wallet,event_key,token,side,size,proportion,known,source_ts)
           VALUES (?,?,?,?,?,?,?,?)''',
        (wallet, event_key, token or '', side or '',
         '' if size is None else format(size, 'f'),
         '' if proportion is None else format(proportion, 'f'),
         1 if known else 0,
         '' if source_ts is None else format(source_ts, 'f')))


def mark_source_unknown(db, wallet, token, event_key, side, size, source_ts=None):
    """A gap or an unknown opening inventory. Later sells are not a faithful copy.

    The recorded event stays. Settlement of our own position does not read this flag.
    """
    ensure_source_schema(db)
    prior=db.execute(
        'SELECT proportion, known FROM wallet_source_events WHERE wallet=? AND event_key=?',
        (wallet, event_key)).fetchone()
    if prior:
        return _stored_source(prior)
    _insert_source_event(db, wallet, event_key, token, side, size, None, False, _dec(source_ts))
    db.execute(
        '''INSERT INTO wallet_source_positions(wallet,token,shares,known) VALUES (?,?,?,0)
           ON CONFLICT(wallet,token) DO UPDATE SET shares='', known=0''',
        (wallet, token or '', ''))
    return _source_result(None, False, None, None)


# One block holds far fewer than this many logs. The cursor orders a transfer
# by its block and the log inside that block. A second timestamp does not.
ORDER_SCALE=100_000_000


def order_cursor(block, log_index):
    block=int(block)
    log_index=int(log_index)
    if block<0 or log_index<0 or log_index>=ORDER_SCALE:
        return None
    return Decimal(block)*ORDER_SCALE+Decimal(log_index)


def end_of_block(block):
    return order_cursor(block, ORDER_SCALE-1)


def event_order(event):
    """Block and log index. A second-resolution timestamp is not an order."""
    if not isinstance(event, dict):
        return None
    block=event.get('blockNumber')
    index=event.get('logIndex')
    if block is None or index is None:
        return None
    try:
        if isinstance(block, str) and block.startswith('0x'):
            block=int(block, 16)
        if isinstance(index, str) and index.startswith('0x'):
            index=int(index, 16)
        return order_cursor(block, index)
    except (TypeError, ValueError):
        return None


def anchor_source_position(db, wallet, token, shares, block):
    """Confirmed inventory at the end of one block. A trade is not this reading.

    Transfers in that block are already inside the balance. Later transfers
    apply by block and log index. This does not open a buy.
    """
    ensure_source_schema(db)
    shares=_dec(shares)
    cursor=end_of_block(block) if block is not None else None
    if not token or shares is None or shares<0 or cursor is None:
        raise ValueError('SOURCE_ANCHOR_INVALID')
    stored=format(cursor, 'f')
    db.execute(
        '''INSERT INTO wallet_source_positions
           (wallet,token,shares,known,as_of,anchor_at,anchor_block)
           VALUES (?,?,?,1,?,?,?)
           ON CONFLICT(wallet,token) DO UPDATE SET
             shares=excluded.shares, known=1, as_of=excluded.as_of,
             anchor_at=excluded.anchor_at, anchor_block=excluded.anchor_block''',
        (wallet, token, format(shares, 'f'), stored, stored, str(int(block))))
    return source_position(db, wallet, token)


def apply_source_trade(db, wallet, token, event_key, side, size, source_ts):
    """Apply one detected source trade once, after a confirmed inventory.

    A first BUY does not prove the book was empty. Without a timed reading the
    proportion stays unknown. A late event inside an already applied span is a
    gap. The same event key does not change the shares a second time.
    """
    ensure_source_schema(db)
    prior=db.execute(
        'SELECT proportion, known FROM wallet_source_events WHERE wallet=? AND event_key=?',
        (wallet, event_key)).fetchone()
    if prior:
        return _stored_source(prior)
    ts=_dec(source_ts)
    if size is None or side not in ('BUY', 'SELL') or not token or ts is None:
        return mark_source_unknown(db, wallet, token, event_key, side, size, ts)
    row=db.execute(
        'SELECT shares, known, as_of, anchor_at FROM wallet_source_positions WHERE wallet=? AND token=?',
        (wallet, token)).fetchone()
    anchor=_dec(row['anchor_at']) if row else None
    as_of=_dec(row['as_of']) if row else None
    if row is None or not row['known'] or row['shares'] in (None, '') or anchor is None or as_of is None:
        return mark_source_unknown(db, wallet, token, event_key, side, size, ts)
    shares_before=Decimal(row['shares'])
    if ts<=anchor:
        _insert_source_event(db, wallet, event_key, token, side, size, None, False, ts)
        return _source_result(None, True, None, shares_before)
    if ts<=as_of:
        return mark_source_unknown(db, wallet, token, event_key, side, size, ts)
    if side=='BUY':
        shares_after=shares_before+size
        proportion=None
    elif size>shares_before:
        return mark_source_unknown(db, wallet, token, event_key, side, size, ts)
    else:
        proportion=size/shares_before
        shares_after=shares_before-size
    _insert_source_event(db, wallet, event_key, token, side, size, proportion, True, ts)
    db.execute(
        '''UPDATE wallet_source_positions
           SET shares=?, known=1, as_of=? WHERE wallet=? AND token=?''',
        (format(shares_after, 'f'), format(ts, 'f'), wallet, token))
    return _source_result(proportion, True, shares_before, shares_after)


def note_source_event(db, wallet, event_key, event, started, source_ts, first_seen):
    """Record a detected trade even when our copy does not run.

    A trade from before this process started does not invent an opening size.
    """
    if not isinstance(event, dict) or event.get('type')!='TRADE' or event.get('side') not in ('BUY', 'SELL'):
        return None
    side=event.get('side')
    token=str(event.get('asset') or '')
    size=_dec(event.get('_chain_shares')) or _event_size(event)
    order=event_order(event)
    # A second timestamp is not an order. Without a block and a log index the
    # proportion stays unknown. A confirmed balance stays in place: one
    # unordered signal does not erase it.
    if not token or size is None:
        return mark_source_unknown(db, wallet, token, event_key, side, size, order or _dec(source_ts))
    if order is None:
        if source_is_confirmed(db, wallet, token):
            return _source_result(None, True, None, None)
        return mark_source_unknown(db, wallet, token, event_key, side, size, _dec(source_ts))
    return apply_source_trade(db, wallet, token, event.get('_chain_key') or event_key, side, size, order)


def source_position(db, wallet, token):
    ensure_source_schema(db)
    row=db.execute(
        '''SELECT shares, known, anchor_block FROM wallet_source_positions
           WHERE wallet=? AND token=?''',
        (wallet, token)).fetchone()
    if not row:
        return {'shares': None, 'known': False, 'block': None}
    block=None
    if row['known'] and row['anchor_block']:
        try:
            block=int(row['anchor_block'])
        except (TypeError, ValueError):
            block=None
    shares=Decimal(row['shares']) if row['known'] and row['shares'] not in (None, '') else None
    return {'shares': shares, 'known': bool(row['known']), 'block': block}


def source_is_confirmed(db, wallet, token):
    ensure_source_schema(db)
    row=db.execute(
        'SELECT known, anchor_at FROM wallet_source_positions WHERE wallet=? AND token=?',
        (wallet, token)).fetchone()
    return bool(row and row['known'] and row['anchor_at'])


def sell_cut(our_shares, proportion):
    """Our share count for a known source fraction. Unknown is not a full close."""
    if proportion is None:
        return None, 'SOURCE_PROPORTION_UNKNOWN'
    try:
        proportion=Decimal(str(proportion))
    except Exception:
        return None, 'SOURCE_PROPORTION_UNKNOWN'
    if not proportion.is_finite() or proportion<=0 or proportion>1:
        return None, 'SOURCE_PROPORTION_UNKNOWN'
    whole=int(our_shares)
    cut=int((Decimal(whole)*proportion).to_integral_value(rounding=ROUND_FLOOR))
    if cut<=0:
        return None, 'SELL_BELOW_MINIMUM'
    return min(cut, whole), None


def exposure_block(open_rows, market, debit, opening_new, cash):
    """Position and wallet caps, including add-ons, fees and capital already reserved."""
    debit=int(debit)
    rows=[t for t in open_rows if t.get('status') in ('OPEN', 'RESOLVED')]
    if opening_new and len(rows)>=MAX_OPEN_POSITIONS:
        return 'COPY_POSITION_ALREADY_OPEN'
    market_tied=sum(int(t['cost'])+int(t['fee']) for t in rows if t.get('market')==market and t.get('status')=='OPEN')
    if market_tied+debit>POSITION_LIMIT:
        return 'COPY_EXPOSURE_LIMIT'
    wallet_tied=sum(int(t['cost'])+int(t['fee']) for t in rows)
    if wallet_tied+debit>WALLET_LIMIT:
        return 'COPY_EXPOSURE_LIMIT'
    if int(cash)<debit:
        return 'COPY_CASH_LIMIT'
    return None
MIN_SOURCE_PRICE=Decimal('0.20')
MAX_SOURCE_PRICE=Decimal('0.70')
# Ended hypothetical fills first. This does not create a buy and does not
# change the 90s or 20–70c gates. A market that was just tried and is still
# unresolved waits out the retry interval, so the next records get a turn.
REVIEW_FILL_LIMIT=8
REVIEW_OTHER_LIMIT=5
REVIEW_RETRY_SECONDS=60

def _due_fills(db, now, limit, reasons=()):
    reason_sql=''
    params=[now, now-REVIEW_RETRY_SECONDS]
    if reasons:
        reason_sql=" AND json_extract(body,'$.reason') IN (%s)" % ','.join('?' * len(reasons))
        params.extend(reasons)
    params.append(limit)
    return [dict(r) for r in db.execute(
        f"""SELECT * FROM wallet_copy_skip_reviews
           WHERE end<=? AND checked<=?
             AND json_extract(body,'$.shadow.status')='FILLED_PENDING_SETTLEMENT'
             AND IFNULL(json_extract(body,'$.status'),'')!='RESOLVED'
             {reason_sql}
           ORDER BY checked, end LIMIT ?""", params)]

def due_skip_reviews(db, now, fill_limit=REVIEW_FILL_LIMIT, other_limit=REVIEW_OTHER_LIMIT):
    fills=_due_fills(db, now, fill_limit)
    # Observation tickets sit behind older skips. Give them their own due
    # slots so eight ancient markets cannot keep their result unknown.
    seen={(r['wallet'], r['event_key']) for r in fills}
    for row in _due_fills(db, now, fill_limit, ('COPY_PAUSED', 'PAUSED')):
        if (row['wallet'], row['event_key']) in seen:continue
        fills.append(row)
        seen.add((row['wallet'], row['event_key']))
    rest=[]
    for r in db.execute(
            'SELECT * FROM wallet_copy_skip_reviews WHERE end<=? AND checked<=? ORDER BY checked,end LIMIT ?',
            (now, now-REVIEW_RETRY_SECONDS, other_limit+len(seen))):
        row=dict(r)
        if (row['wallet'], row['event_key']) in seen:continue
        rest.append(row)
        if len(rest)>=other_limit:break
    return fills+rest

def market_spec(raw, event, now):
    slug=str(event.get('slug',''))
    match=re.fullmatch(r'(btc|eth)-updown-(5m|15m)-(\d+)',slug)
    if not match or raw.get('slug')!=slug:raise ValueError('UNSUPPORTED_MARKET')
    asset,interval,start=match.groups();start=int(start);end=start+(300 if interval=='5m' else 900)
    def timestamp(value):
        d=datetime.fromisoformat(value.replace('Z','+00:00'))
        if d.tzinfo is None:raise ValueError('MISSING_TIMEZONE')
        return d.timestamp()
    if timestamp(raw['eventStartTime'])!=start or timestamp(raw['endDate'])!=end:raise ValueError('WINDOW_MISMATCH')
    if not start<=now<end or raw.get('active') is not True or raw.get('closed') is not False or raw.get('acceptingOrders') is not True:raise ValueError('MARKET_CLOSED')
    if str(raw.get('conditionId'))!=str(event.get('conditionId')):raise ValueError('CONDITION_MISMATCH')
    names=raw['outcomes'];tokens=raw['clobTokenIds']
    names=json.loads(names) if isinstance(names,str) else names
    tokens=json.loads(tokens) if isinstance(tokens,str) else tokens
    if len(names)!=2 or set(names)!={'Up','Down'} or len(tokens)!=2 or len(set(tokens))!=2:raise ValueError('TOKEN_MAPPING')
    mapping=dict(zip(map(str,tokens),names));token=str(event.get('asset',''))
    if token not in mapping:raise ValueError('TOKEN_MISMATCH')
    kind,topic,schema=classify_rule(raw.get('description',''),asset.upper())
    if topic is None:raise ValueError('RULE_UNVERIFIED')
    fees=raw.get('feeSchedule') or {}
    if raw.get('feesEnabled') is False:rate=0
    elif raw.get('feesEnabled') is True and fees.get('exponent')==1 and 'rate' in fees:rate=float(fees['rate'])
    else:raise ValueError('FEE_UNVERIFIED')
    if not math.isfinite(rate) or not 0<=rate<=1:raise ValueError('FEE_INVALID')
    return dict(slug=slug,asset=asset.upper(),interval=interval,start=start,end=end,condition=raw['conditionId'],
                token=token,side=mapping[token],fee_rate=rate,rule_kind=kind,description=raw.get('description',''))

def public_trade(t):
    fields='id wallet strategy market condition asset interval token side end status opened shares cost fee exit_fee payout closed_at resolved pnl_micro official_seen_at'.split()
    result={k:t[k] for k in fields if k in t}
    e=t.get('entry_evidence',{})
    result.update(source_transaction=e.get('source_event',{}).get('transactionHash'),source_price=e.get('source_event',{}).get('price'),
        source_timestamp=e.get('source_timestamp'),first_seen=e.get('first_seen'),copy_delay=e.get('copy_delay'),
        entry_fill=t.get('entry_fill'),exit_fill=t.get('exit_evidence',{}).get('fill'))
    return result

FLOW_WINDOW=900

def decide_copy_flow(now, copying, last_signal_at, copy_wallet_signals, recent_copied_buys, observer_down):
    """One status. A live server is not evidence that a buy was copied."""
    if recent_copied_buys:
        code='copying'
        detail_pl='W tym oknie jest skopiowany zakup.'
        detail_en='A buy was copied in this window.'
    elif not last_signal_at or now-last_signal_at>FLOW_WINDOW:
        if observer_down:
            code='feed'
            detail_pl='Odbiór portfela kopiowanego nie odpowiada.'
            detail_en='The copied wallet feed is not answering.'
        else:
            code='no_signals'
            detail_pl='Śledzone portfele nie mają nowego BUY ani SELL.'
            detail_en='Watched wallets have no new BUY or SELL.'
    elif not copy_wallet_signals:
        code='paused'
        noun='portfela' if copying==1 else 'portfeli'
        detail_pl='Kopiowanie włączone dla %d %s, bez ich transakcji. Transakcje są na portfelach wstrzymanych albo tylko obserwowanych.'%(copying,noun)
        detail_en='Copying is on for %d wallets, and they have no trade. The trades are on paused or observed wallets.'%copying
    else:
        code='filtered'
        detail_pl='Portfel z włączonym kopiowaniem dostał sygnał, a zakup nie powstał.'
        detail_en='A wallet with copying on received a signal and no buy was opened.'
    return {
        'code':code,
        'last_signal_at':last_signal_at,
        'copying':copying,
        'detail_pl':detail_pl,
        'detail_en':detail_en,
        'generated_at':now,
    }


class WalletCopy:
    # Max total CLOB exposure across all open orders (safety cap)
    CLOB_MAX_EXPOSURE_USD = 10.0

    def __init__(self,store,fetch,paused=lambda:False,clock=time.time,sleep=asyncio.sleep,clob_client=None):
        self.store,self.fetch,self.paused,self.clock,self.sleep=store,fetch,paused,clock,sleep
        self.clob_client = clob_client
        self._clob_exposure_usd = 0.0  # running total of CLOB orders placed
        self._market_cache={}
        with store.connect() as db:
            db.executescript('''
              CREATE TABLE IF NOT EXISTS wallet_copy_skip_reviews(wallet TEXT,event_key TEXT,end REAL,checked REAL DEFAULT 0,body TEXT,PRIMARY KEY(wallet,event_key));
              CREATE TABLE IF NOT EXISTS wallet_copy_accounts(wallet TEXT PRIMARY KEY,cash INTEGER NOT NULL);
              CREATE TABLE IF NOT EXISTS wallet_copy_events(wallet TEXT,event_key TEXT,ts REAL,reason TEXT,body TEXT,PRIMARY KEY(wallet,event_key));
              CREATE TABLE IF NOT EXISTS wallet_copy_positions(id TEXT PRIMARY KEY,wallet TEXT,body TEXT);
              CREATE TABLE IF NOT EXISTS wallet_copy_ledger(id TEXT PRIMARY KEY,wallet TEXT,amount INTEGER NOT NULL);
            ''')
            for wallet in get_active_wallets(store):db.execute('INSERT OR IGNORE INTO wallet_copy_accounts VALUES (?,?)',(wallet,INITIAL))
            db.execute("UPDATE wallet_copy_events SET reason='ABORTED_ON_RESTART' WHERE reason='PROCESSING'")
        if not store.get('wallet_copy_start',{}):store.set('wallet_copy_start',{'at':clock()})
        self.started=store.get('wallet_copy_start',{})['at']
        try:
            from .wallet_roster import tick as roster_tick
            roster_tick(store, clock())
        except Exception:
            pass
        self.last_publish=0
        self._scan_at=0
        self._scan={}
        self.watch={}
        self._consumed={}
        self._obs_consumed={}
        self.book_clock=VenueClock()
        if not hasattr(store,"wallet_activity_ready"):store.wallet_activity_ready=asyncio.Event()
        self.publish('STARTED')

    def positions(self,db):return [json.loads(r[0]) for r in db.execute('SELECT body FROM wallet_copy_positions')]

    def publish(self,status,error=None):
        now=self.clock()
        roster=(self.store.get('wallet_roster') or {}).get('wallets') or {}
        with self.store.connect() as db:
            trades=self.positions(db);accounts=[]
            for wallet in get_active_wallets(self.store):
                db.execute('INSERT OR IGNORE INTO wallet_copy_accounts VALUES (?,?)',(wallet,INITIAL))
                rows=[t for t in trades if t['wallet']==wallet]
                closed=sorted((t for t in rows if t['status'] in ('CLOSED','SETTLED')),key=lambda t:t['closed_at'])
                pnl=sum(t['pnl_micro'] for t in closed);exposure=sum(t['cost']+t['fee'] for t in rows if t['status'] in ('OPEN','RESOLVED'))
                cash=db.execute('SELECT cash FROM wallet_copy_accounts WHERE wallet=?',(wallet,)).fetchone()[0]
                ledger=db.execute('SELECT COALESCE(SUM(amount),0) FROM wallet_copy_ledger WHERE wallet=?',(wallet,)).fetchone()[0]
                if cash<0 or cash!=INITIAL+ledger or cash+exposure!=INITIAL+pnl:raise CopyLedgerError('COPY_LEDGER_MISMATCH')
                curve=[];total=peak=dd=0
                for t in closed:
                    total+=t['pnl_micro'];peak=max(peak,total);dd=max(dd,peak-total);curve.append({'ts':t['closed_at'],'pnl':total/1e6})
                last=db.execute('SELECT ts,reason FROM wallet_copy_events WHERE wallet=? ORDER BY ts DESC,rowid DESC LIMIT 1',(wallet,)).fetchone()
                roster_row=roster.get(wallet) or {}
                accounts.append(dict(id='copy-'+wallet,wallet=wallet,name='Copy '+wallet_label(wallet)+' · PAPER',initial=500,cash=cash/1e6,pnl=pnl/1e6,
                    roster_state=roster_row.get('state'),watch=self.watch.get(wallet),
                    fees=sum(t['fee']+t.get('exit_fee',0) for t in rows)/1e6,open_cost=exposure/1e6,pending=0,
                    trades=len(rows),settled=len(closed),wins=sum(t['pnl_micro']>0 for t in closed),curve=curve[-300:],
                    max_drawdown_usd=dd/1e6,independent_windows=len({t['market'] for t in closed}),
                    current_block=self.risk_reason(db,wallet,now),last_reason=last['reason'] if last else 'NO_NEW_SOURCE_TRADE',last_decision_at=last['ts'] if last else None))
            if now-self._scan_at>=30 or not self._scan:
                reasons=[dict(r) for r in db.execute('SELECT wallet,reason,COUNT(*) AS count FROM wallet_copy_events GROUP BY wallet,reason')]
                recent=[]
                for r in db.execute('SELECT wallet,event_key,ts,reason,body FROM wallet_copy_events ORDER BY ts DESC,rowid DESC LIMIT 30'):
                    e=json.loads(r['body']);recent.append({k:r[k] for k in ('wallet','event_key','ts','reason')}|{'error':e.get('error'),'copy_delay':e.get('copy_delay')})
                errors=[dict(r)|{'detail':json.loads(r['body']).get('error')} for r in db.execute("SELECT wallet,event_key,ts,body FROM wallet_copy_events WHERE reason='ERROR' ORDER BY ts DESC LIMIT 30")]
                self._scan={'reasons':reasons,'recent':recent,'errors':errors}
                self._scan_at=now
        if 'skip' not in self._scan or now-self._scan.get('skip_at',0)>=30:
            self._scan['skip']=self.skip_summary()
            self._scan['skip_at']=now
        reasons,recent,errors=self._scan['reasons'],self._scan['recent'],self._scan['errors']
        samples=[]
        for t in trades:
            path=(t.get('entry_evidence') or {}).get('path_ms')
            if path:samples.append(path)
        roster_state=self.store.get('wallet_roster',{})
        totals=copy_summarize(trades,copy_pauses(self.store),now,observed=len(get_active_wallets(self.store)),copy_wallets=list(get_active_wallets(self.store)),roster=roster_state)
        board=paper_board(trades,roster_state,copy_pauses(self.store),now)
        self.store.set(KEY,dict(spec='wallet-signal-copy-v1',status=status,error=error,updated_at=now,started_at=self.started,board=board,
            mode='PAPER + CLOB' if self.clob_client else 'PAPER ONLY',accounts=accounts,recent_trades=[public_trade(t) for t in sorted(trades,key=lambda t:t['opened'],reverse=True)[:100]],
            trades_truncated=len(trades)>100,reasons=reasons,recent_decisions=recent,
            skip_review=self._scan['skip'],recent_errors=errors,entry_policy='copy-immediate-v7',
            totals=totals,path_ms=path_stats(samples[-200:]),
            clock_skew={'book':round(self.book_clock.skew(),3),'samples':len(self.book_clock.offsets)},
            watch_updated_at=getattr(self,'watch_at',None),
            execution=EXECUTION,
            flow=self.store.get('wallet_copy_flow') or {},
            scope='BTC/ETH 5m and 15m only; one market minimum per buy (not the source size), source price band 20-70c is a limit of this PAPER version; 500USD separate virtual scenarios; an added buy increases the open lot only inside the 5USD position cap; a source SELL closes the fraction of the source position immediately before that sell',
            limitation='The 20-70c band is our version limit, not a claim that a price outside it is automatically a losing trade. Changing it belongs in a separate PAPER. The sell fraction uses detected source buys and sells, including ones we did not copy. An unknown opening position or a gap is not a faithful copy and does not invent a fraction. Settlement still runs. FOK at fresh delayed books with 50% depth. A slice below the market minimum is not filled. SELL is allowed while new buys are paused. Signal age 90s. One position including add-ons and fees stays within 5USD. Five positions cap the wallet at 25USD. No profitability guarantee.'))

    def skip_summary(self):
        with self.store.connect() as db:
            rows=[json.loads(r[0]) for r in db.execute('SELECT body FROM wallet_copy_skip_reviews ORDER BY end DESC LIMIT 100')]
            total=db.execute('SELECT COUNT(*) FROM wallet_copy_skip_reviews').fetchone()[0]
        return dict(spec='skip-outcome-v1',total=total,recent=rows,truncated=total>100,
            limitation='Shadow hold-to-settlement PnL only with recorded delayed full fill; otherwise null. Independent tickets, not portfolio or copied SELL returns.')

    def reason(self,row,reason,extra=None):
        event=json.loads(row['body']);now=self.clock()
        evidence=dict(source_event=event,source_timestamp=row['source_ts'],first_seen=row['first_seen'],
            decision_at=now,detection_delay=row['first_seen']-row['source_ts'],decision_delay=now-row['source_ts'],
            policy=POLICY,reason=reason,decision_book=None)
        evidence.update(extra or {})
        with self.store.connect() as db:
            db.execute('UPDATE wallet_copy_events SET reason=?,body=? WHERE wallet=? AND event_key=?',
                (reason,json.dumps(evidence,allow_nan=False),row['wallet'],row['event_key']))
            match=re.fullmatch(r'(btc|eth)-updown-(5m|15m)-(\d+)',str(event.get('slug','')))
            if (match and event.get('type')=='TRADE' and event.get('side')=='BUY'
                and reason not in ('PRE_ACTIVATION','SOURCE_IDENTITY_MISMATCH','NOT_BUY_OR_SELL')
                and row['source_ts']>=self.started and event.get('conditionId') and event.get('asset')):
                end=int(match[3])+(300 if match[2]=='5m' else 900)
                review=dict(evidence,status='PENDING',source_side_won=None,counterfactual_pnl=None)
                db.execute('INSERT OR IGNORE INTO wallet_copy_skip_reviews(wallet,event_key,end,body) VALUES (?,?,?,?)',
                    (row['wallet'],row['event_key'],end,json.dumps(review,allow_nan=False)))

    async def review_skips(self):
        now=self.clock()
        # The select is off the event loop. Prefer ended hypothetical fills so a
        # backlog of unavailable skips cannot keep their result unknown.
        rows=await asyncio.to_thread(self._due_reviews, now)
        self.store.set('wallet_skip_review_beat', {'at': now, 'selected': len(rows)})
        for row in rows:
            review=json.loads(row['body'])
            if review['status']=='RESOLVED':continue
            try:
                event=review['source_event']
                raw=await asyncio.to_thread(self.fetch,'https://clob.polymarket.com/markets/'+quote(str(event['conditionId']),safe=''))
                if raw.get('condition_id')!=event['conditionId']:raise ValueError('REVIEW_CONDITION_MISMATCH')
                tokens=raw.get('tokens',[]);winners=[t for t in tokens if t.get('winner') is True]
                if raw.get('closed') is True and len(winners)==1:
                    if str(event['asset']) not in {str(t['token_id']) for t in tokens}:raise ValueError('REVIEW_TOKEN_MISMATCH')
                    review.update(status='RESOLVED',source_side_won=str(winners[0]['token_id'])==str(event['asset']),official_seen_at=self.clock())
                self.score_shadow(review)
                review.pop('error',None)
            except Exception as error:
                review['error']=str(error)[:200]
            with self.store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                current=json.loads(db.execute('SELECT body FROM wallet_copy_skip_reviews WHERE wallet=? AND event_key=?',(row['wallet'],row['event_key'])).fetchone()[0])
                if 'shadow' in current:review['shadow']=current['shadow']
                self.score_shadow(review)
                db.execute('UPDATE wallet_copy_skip_reviews SET checked=?,body=? WHERE wallet=? AND event_key=?',
                    (1e30 if review['status']=='RESOLVED' else now,json.dumps(review),row['wallet'],row['event_key']))

    def risk_reason(self,db,wallet,now,extra_position=True):
        rows=[t for t in self.positions(db) if t['wallet']==wallet]
        if extra_position and sum(1 for t in rows if t['status'] in ('OPEN','RESOLVED'))>=MAX_OPEN_POSITIONS:return 'COPY_POSITION_ALREADY_OPEN'
        if db.execute('SELECT cash FROM wallet_copy_accounts WHERE wallet=?',(wallet,)).fetchone()[0]<BUDGET:return 'COPY_CASH_LIMIT'
        return None

    def risk(self,db,wallet,now,extra_position=True):return self.risk_reason(db,wallet,now,extra_position) is None

    def paper_pnl_micro(self,db,wallet):
        return sum(t['pnl_micro'] for t in self.positions(db) if t['wallet']==wallet and t['status'] in ('CLOSED','SETTLED'))

    async def book(self,token):
        from .worker import normalize_book
        raw=await asyncio.to_thread(self.fetch,'https://clob.polymarket.com/book?token_id='+quote(token,safe=''))
        return normalize_book(raw,token,self.clock(),max_age=15,venue_clock=self.book_clock)

    def _pending_query(self,db,wallets,now,limit):
        if not wallets or limit<=0:return []
        # The wallet key walks each trader's whole history. The time index
        # reads only the last 90 seconds, which is the queue that can still copy.
        if not db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='index' AND name='wallet_activity_seen'"
        ).fetchone():
            db.execute('CREATE INDEX IF NOT EXISTS wallet_activity_seen ON wallet_activity(first_seen)')
        marks=','.join('?'*len(wallets))
        return [dict(r) for r in db.execute(
            f"SELECT a.* FROM wallet_activity a INDEXED BY wallet_activity_seen "
            f"LEFT JOIN wallet_copy_events e "
            f"ON a.wallet=e.wallet AND a.event_key=e.event_key "
            f"WHERE e.event_key IS NULL AND a.first_seen>=? AND a.wallet IN ({marks}) "
            f"ORDER BY a.first_seen ASC LIMIT ?",(now-90,*wallets, limit))]

    def pending_activity(self,db,active=None):
        """Only fresh rows. A full-table INSERT every second blocked the event loop
        and the WebSocket handshakes timed out while SQLite held the thread.

        A wallet with copying on is read before a paused backlog, and observed
        names fill only the slots that remain.
        """
        active=list(active if active is not None else get_active_wallets(self.store))
        now=self.clock()
        if not active:
            return []
        roster=(self.store.get('wallet_roster') or {}).get('wallets') or {}
        copying=[];paused=[];lo=[]
        for wallet in active:
            state=(roster.get(wallet) or {}).get('state')
            if state=='observed':lo.append(wallet)
            elif state in ('paper_test','paper_active'):copying.append(wallet)
            else:paused.append(wallet)
        rows=self._pending_query(db,copying,now,20)
        if len(rows)<20:rows.extend(self._pending_query(db,paused,now,20-len(rows)))
        if len(rows)<20:rows.extend(self._pending_query(db,lo,now,20-len(rows)))
        return rows

    async def process(self,row,shadow=True,sell_proportion=None):
        await self._process(row,sell_proportion=sell_proportion)
        if shadow:
            await self._capture_shadow(row)

    async def _capture_shadow(self,row):
        # Independent diagnostic; never changes cash, risk or the actual copy decision.
        with self.store.connect() as db:
            saved=db.execute('SELECT body FROM wallet_copy_skip_reviews WHERE wallet=? AND event_key=?',
                (row['wallet'],row['event_key'])).fetchone()
        if not saved:return
        review=json.loads(saved[0])
        if 'shadow' in review:return
        shadow=dict(policy='skip-hold-arrival-v1',status='UNAVAILABLE',pnl_micro=None,
            limitation='Independent 5USD hypothetical ticket held to official settlement; not source SELL replication or portfolio returns.')
        event=review['source_event']
        try:
            now=self.clock()
            # COPY_PAUSED still gets a hypothetical ticket. Real buys stay blocked.
            # SOURCE_TOO_OLD does not: a reboot must not invent late copies.
            if self.paused() or review['reason'] in ('PAUSED','ERROR','SOURCE_TOO_OLD','SOURCE_IDENTITY_MISMATCH','SOURCE_PRICE_INVALID','SOURCE_PRICE_MISSING'):raise ValueError('NOT_ELIGIBLE_FOR_SHADOW')
            if not 0<=now-review['decision_at']<=5:raise ValueError('CAPTURE_TOO_LATE_NO_BACKFILL')
            raw=await asyncio.to_thread(self.fetch,'https://gamma-api.polymarket.com/markets/slug/'+quote(event['slug'],safe=''))
            m=market_spec(raw,event,self.clock())
            decision=await self.book(m['token']);at=self.clock()
            if not (0<=self.book_clock.age(decision['source_ts'],at)<=5 and decision['asks']):raise ValueError('DECISION_STALE_OR_EMPTY')
            limit=min(Decimal('.999999'),min(Decimal(p) for p,q in decision['asks'])+Decimal('.02'))
            shadow.update(decision_book=decision,decision_at=at,limit=str(limit))
            await self.sleep(.25)
            arrival=await self.book(m['token']);now=self.clock()
            shadow.update(arrival_book=arrival,arrival_at=now,source_to_arrival_seconds=now-row['source_ts'])
            if not (.25<=now-at<=5 and 0<=self.book_clock.age(arrival['source_ts'],now)<=5 and arrival['source_ts']>decision['source_ts']
                    and arrival['received_at']>=at+.25 and now<m['end']):raise ValueError('ARRIVAL_INVALID')
            ask=min(Decimal(p) for p,q in arrival['asks'])
            notional=(Decimal(str(arrival['min_shares']))*ask).quantize(Decimal('.000001'),rounding=ROUND_FLOOR)
            fill=simulate_fill(arrival['asks'],notional,limit,m['fee_rate'],arrival['min_shares'],arrival['tick'])
            if fill and fill['cost']+fill['fee']<=BUDGET:
                shadow.update(status='FILLED_PENDING_SETTLEMENT',fill=fill,fee_rate=m['fee_rate'])
            else:shadow['status']='NO_FULL_FILL'
        except Exception as error:shadow['error']=str(error)[:200]
        # Merge with latest review so background settlement cannot be overwritten.
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            latest=json.loads(db.execute('SELECT body FROM wallet_copy_skip_reviews WHERE wallet=? AND event_key=?',
                (row['wallet'],row['event_key'])).fetchone()[0])
            latest['shadow']=shadow
            self.score_shadow(latest)
            db.execute('UPDATE wallet_copy_skip_reviews SET body=? WHERE wallet=? AND event_key=?',
                (json.dumps(latest),row['wallet'],row['event_key']))

    @staticmethod
    def score_shadow(review):
        shadow=review.get('shadow',{})
        if review.get('status')=='RESOLVED' and shadow.get('status')=='FILLED_PENDING_SETTLEMENT':
            fill=shadow['fill'];payout=fill['shares'] if review['source_side_won'] else 0
            shadow.update(status='SETTLED',payout_micro=payout,pnl_micro=payout-fill['cost']-fill['fee'])
            review['counterfactual_pnl']=shadow['pnl_micro']/1e6

    async def _prepare_sell(self,row):
        """Chain read for one sell. Other wallets keep moving while this runs."""
        import time as time_module
        from .source_chain import historical_sell_proportion, reader_from_env
        event=json.loads(row['body'])
        reader=getattr(self,'source_reader',None) or reader_from_env()
        if reader is None:
            return None,0.0
        started=time_module.perf_counter()
        try:
            result=await asyncio.to_thread(
                historical_sell_proportion,reader,row['wallet'],str(event.get('asset') or ''),
                event.get('transactionHash'),event.get('size'))
        except Exception:
            result={'proportion':None,'known':False}
        elapsed=time_module.perf_counter()-started
        self.last_sell_read_s=elapsed
        return result,elapsed

    async def _apply_batch(self,rows):
        """Start every sell read first. Each wallet keeps its own order.

        A sell on one wallet does not wait in front of another wallet's signal.
        """
        tasks={}
        wallets=[]
        grouped={}
        for row in rows:
            grouped.setdefault(row['wallet'],[]).append(row)
            if row['wallet'] not in wallets:
                wallets.append(row['wallet'])
            body=json.loads(row['body'])
            if body.get('type')=='TRADE' and body.get('side')=='SELL':
                tasks[row['event_key']]=asyncio.create_task(self._prepare_sell(row))
        async def drain(wallet):
            for row in grouped[wallet]:
                proportion=None
                task=tasks.get(row['event_key'])
                if task is not None:
                    proportion,elapsed=await task
                    if elapsed:
                        self.store.set('wallet_source_sell_read_ms',{'ms':round(elapsed*1000,1)})
                await self.process(row,shadow=False,sell_proportion=proportion)
        await asyncio.gather(*(drain(wallet) for wallet in wallets))

    async def _process(self,row,sell_proportion=None):
        queued_at=self.clock();wallet=row['wallet'];key=row['event_key'];event=json.loads(row['body'])
        now=queued_at
        with self.store.connect() as db:
            inserted=db.execute('INSERT OR IGNORE INTO wallet_copy_events VALUES (?,?,?,?,?)',(wallet,key,now,'PROCESSING','{}')).rowcount
        if not inserted:return
        try:
            identity_ok=str(event.get('proxyWallet','')).lower()==wallet and float(event.get('timestamp',0))==row['source_ts']
            source_note=None
            handled=False
            if sell_proportion is not None and identity_ok and event.get('side')=='SELL':
                source_note=sell_proportion
                handled=True
            if not handled and identity_ok and event.get('type')=='TRADE' and event.get('side') in ('BUY','SELL'):
                with self.store.connect() as db:
                    db.execute('BEGIN IMMEDIATE')
                    source_note=note_source_event(db,wallet,key,event,self.started,row['source_ts'],row['first_seen'])
            if row['first_seen']<self.started or row['source_ts']<self.started:self.reason(row,'PRE_ACTIVATION');return
            if not 0<=now-row['source_ts']<=90 or not 0<=now-row['first_seen']<=90:self.reason(row,'SOURCE_TOO_OLD');return
            if not identity_ok:
                self.reason(row,'SOURCE_IDENTITY_MISMATCH');return
            if event.get('type')!='TRADE' or event.get('side') not in ('BUY','SELL'):self.reason(row,'NOT_BUY_OR_SELL');return
            kind=event['side']
            # A pause stops a new buy. It does not block a SELL of an open PAPER position
            # or the official settlement path, which never enters this function.
            if kind=='BUY' and self.paused():self.reason(row,'PAUSED');return
            if kind=='BUY' and copy_paused(self.store,'copy-'+wallet):self.reason(row,'COPY_PAUSED');return
            if not re.fullmatch(r'(btc|eth)-updown-(5m|15m)-\d+',str(event.get('slug',''))):self.reason(row,'UNSUPPORTED_MARKET');return
            slug=str(event['slug'])
            raw=await asyncio.to_thread(self.fetch,'https://gamma-api.polymarket.com/markets/slug/'+quote(slug,safe=''))
            m=market_spec(raw,event,self.clock())
            with self.store.connect() as db:
                held=self.positions(db)
                open_trade=next((t for t in held if t['wallet']==wallet and t['token']==m['token'] and t['status']=='OPEN'),None)
                adding=kind=='BUY' and open_trade is not None
                blocked=self.risk_reason(db,wallet,self.clock(),extra_position=not adding) if kind=='BUY' else None
                if blocked:self.reason(row,blocked);return
                same_market=any(t for t in held if t['wallet']==wallet and t['market']==m['slug'] and t['status'] in ('OPEN','RESOLVED'))
                if kind=='BUY' and not adding and same_market:self.reason(row,'COPY_POSITION_ALREADY_OPEN');return
                if kind=='SELL' and not open_trade:self.reason(row,'NO_COPIED_POSITION');return
            sell_shares=None
            proportion=None if not source_note else source_note.get('proportion')
            if kind=='SELL':
                if _event_size(event) is None:
                    self.reason(row,'SOURCE_SIZE_MISSING',{'source_copy':'unknown'});return
                if proportion is None:
                    self.reason(row,'SOURCE_PROPORTION_UNKNOWN',{'source_copy':'unknown'});return
                sell_shares,why=sell_cut(open_trade['shares'],proportion)
                if why:self.reason(row,why,{'source_copy':'unknown' if why=='SOURCE_PROPORTION_UNKNOWN' else 'matched'});return
            source_price=None
            if kind=='BUY':
                source_price,why=confirmed_source_price(event)
                if why:self.reason(row,why);return
                why=band_reason(source_price)
                if why:self.reason(row,why);return
            t_book=self.clock();decision=await self.book(m['token']);at=self.clock()
            await self.sleep(.25)
            arrival=await self.book(m['token'])
            arrival=dict(arrival);arrival['token']=m['token'];arrival['fee_rate']=m['fee_rate']
            if kind=='BUY':
                why,fill=decide_buy(source_price,arrival,self._consumed,BUDGET)
                if why:self.reason(row,why,{'decision_book':decision,'arrival_book':arrival});return
                limit=fill['limit']
            else:
                why,fill=decide_sell(arrival,sell_shares,self._consumed)
                if why:self.reason(row,why,{'decision_book':decision,'arrival_book':arrival});return
                limit=fill.get('floor')
            now=self.clock()
            timing=path_record(event,row,queued_at,t_book,at,now)
            # From the API timestamp only. chain_fast has no source-trade clock.
            copy_delay=None if timing['detect_from_trade_ms'] is None else now-row['source_ts']
            evidence=dict(source_event=event,source_timestamp=row['source_ts'],first_seen=row['first_seen'],decision_at=at,arrival_at=now,
                detection_delay=None if timing['detect_from_trade_ms'] is None else timing['detect_from_trade_ms']/1000,
                copy_delay=copy_delay,
                path_ms=timing,
                decision_book=decision,arrival_book=arrival,market_metadata=raw)
            if kind=='BUY':
                evidence['copy_policy']=POLICY
                evidence['execution']=EXECUTION
                evidence['source_price']=str(source_price)
                evidence['path_ms']['paper_ms']=round((self.clock()-now)*1000,1)
                remember_fill(self._consumed,arrival,fill)
                if adding:
                    if not self._add_lot(open_trade,fill,evidence,wallet,key,now):return
                else:
                    trade=dict(id=wallet+':'+key,wallet=wallet,strategy='copy-'+wallet,market=m['slug'],condition=m['condition'],asset=m['asset'],interval=m['interval'],
                        token=m['token'],side=m['side'],end=m['end'],status='OPEN',opened=now,shares=fill['shares'],cost=fill['cost'],fee=fill['fee'],exit_fee=0,
                        entry_evidence=evidence,entry_fill=fill)
                    if not self._open_lot(trade,evidence,wallet,key):return
                if self.clob_client:
                    evidence['clob_order']=await self.place_clob_buy(wallet,m['token'],limit,fill)
                    with self.store.connect() as db:
                        db.execute("UPDATE wallet_copy_events SET body=? WHERE wallet=? AND event_key=?",
                            (json.dumps(evidence),wallet,key))
            else:
                evidence['source_proportion']=format(Decimal(str(proportion)),'f')
                evidence['source_copy']='matched'
                remember_fill(self._consumed,arrival,fill)
                if int(sell_shares)>=int(open_trade['shares']):
                    self.close(open_trade,fill['proceeds'],fill['fee'],now,'CLOSED',{'fill':fill,'evidence':evidence},row)
                else:
                    self._partial_close(open_trade,sell_shares,fill,now,evidence,row)
        except Exception as error:self.reason(row,'ERROR',{'error':str(error)[:400]})

    async def place_clob_buy(self,wallet,token,limit,fill):
        with self.store.connect() as db:
            pnl=self.paper_pnl_micro(db,wallet)
        if pnl<0:
            log.info('CLOB skipped %s: paper result is negative',wallet[-8:])
            return {'ok':False,'reason':'PAPER_NEGATIVE','pnl_usd':pnl/1e6}
        clob_budget=min(5.0,float(fill['cost']+fill['fee'])/1e6)
        clob_price=float(limit)
        clob_size=clob_budget/clob_price if clob_price>0 else 0
        remaining=self.CLOB_MAX_EXPOSURE_USD-self._clob_exposure_usd
        if clob_budget>remaining:
            clob_budget=max(0,remaining)
            clob_size=clob_budget/clob_price if clob_price>0 else 0
        log.info('CLOB BUY attempt: token=%s price=%.4f size=%.2f budget=$%.2f exposure=$%.2f/%s',
                 token[:16],clob_price,clob_size,clob_budget,self._clob_exposure_usd,self.CLOB_MAX_EXPOSURE_USD)
        if clob_budget<0.50 or clob_size<5:
            return {'ok':False,'reason':'BELOW_MINIMUM','budget':clob_budget,'size':clob_size,'remaining_exposure':remaining}
        try:
            result=await asyncio.to_thread(self.clob_client.buy,token,clob_price,round(clob_size,2))
            if result.get('ok'):
                self._clob_exposure_usd+=clob_budget
            log.info('CLOB order result: %s',json.dumps(result,default=str)[:500])
            return result
        except Exception as error:
            log.error('CLOB order error: %s',error)
            return {'ok':False,'error':str(error)[:400]}

    def _set_copy_reason(self,db,wallet,key,reason,evidence):
        db.execute('UPDATE wallet_copy_events SET reason=?,body=? WHERE wallet=? AND event_key=?',
            (reason,json.dumps(evidence),wallet,key))

    def _open_lot(self,trade,evidence,wallet,key):
        debit=int(trade['cost'])+int(trade['fee'])
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            held=[t for t in self.positions(db) if t['wallet']==wallet]
            cash=db.execute('SELECT cash FROM wallet_copy_accounts WHERE wallet=?',(wallet,)).fetchone()[0]
            blocked=exposure_block(held,trade['market'],debit,True,cash)
            if not blocked and any(t.get('market')==trade['market'] and t.get('status') in ('OPEN','RESOLVED') for t in held):
                blocked='COPY_POSITION_ALREADY_OPEN'
            if blocked:
                self._set_copy_reason(db,wallet,key,blocked,evidence)
                return False
            db.execute('INSERT INTO wallet_copy_positions VALUES (?,?,?)',(trade['id'],wallet,json.dumps(trade)))
            db.execute('UPDATE wallet_copy_accounts SET cash=cash+? WHERE wallet=?',(-debit,wallet))
            db.execute('INSERT INTO wallet_copy_ledger VALUES (?,?,?)',('buy:'+trade['id'],wallet,-debit))
            self._set_copy_reason(db,wallet,key,'COPIED_BUY',evidence)
        return True

    def _add_lot(self,trade,fill,evidence,wallet,key,now):
        debit=int(fill['cost'])+int(fill['fee'])
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            current=json.loads(db.execute('SELECT body FROM wallet_copy_positions WHERE id=?',(trade['id'],)).fetchone()[0])
            if current['status']!='OPEN':
                self._set_copy_reason(db,wallet,key,'COPY_EXPOSURE_LIMIT',evidence)
                return False
            held=[t for t in self.positions(db) if t['wallet']==wallet and t['id']!=trade['id']]
            held.append(current)
            cash=db.execute('SELECT cash FROM wallet_copy_accounts WHERE wallet=?',(wallet,)).fetchone()[0]
            blocked=exposure_block(held,current['market'],debit,False,cash)
            if blocked:
                self._set_copy_reason(db,wallet,key,blocked,evidence)
                return False
            current['shares']=int(current['shares'])+int(fill['shares'])
            current['cost']=int(current['cost'])+int(fill['cost'])
            current['fee']=int(current['fee'])+int(fill['fee'])
            current.setdefault('lots',[]).append({'event_key':key,'shares':fill['shares'],'cost':fill['cost'],'fee':fill['fee'],'at':now})
            evidence=dict(evidence,added_to=trade['id'])
            db.execute('UPDATE wallet_copy_positions SET body=? WHERE id=?',(json.dumps(current),trade['id']))
            db.execute('UPDATE wallet_copy_accounts SET cash=cash+? WHERE wallet=?',(-debit,wallet))
            db.execute('INSERT INTO wallet_copy_ledger VALUES (?,?,?)',('buy:'+trade['id']+':'+key,wallet,-debit))
            self._set_copy_reason(db,wallet,key,'COPIED_BUY',evidence)
        return True

    def _partial_close(self,trade,sold_shares,fill,now,evidence,row):
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            current=json.loads(db.execute('SELECT body FROM wallet_copy_positions WHERE id=?',(trade['id'],)).fetchone()[0])
            if current['status']!='OPEN':return
            whole=int(current['shares'])
            sold=int(sold_shares)
            if sold<=0 or sold>=whole:return
            alloc_cost=int(current['cost'])*sold//whole
            alloc_fee=int(current['fee'])*sold//whole
            payout=int(fill['proceeds'])
            exit_fee=int(fill['fee'])
            slice_id=trade['id']+':sell:'+row['event_key']
            closed=dict(current)
            closed.pop('lots',None)
            closed.update(id=slice_id,status='CLOSED',shares=sold,cost=alloc_cost,fee=alloc_fee,payout=payout,exit_fee=exit_fee,
                closed_at=now,resolved=now,pnl_micro=payout-exit_fee-alloc_cost-alloc_fee,
                exit_evidence={'fill':fill,'evidence':evidence,'partial':True})
            current['shares']=whole-sold
            current['cost']=int(current['cost'])-alloc_cost
            current['fee']=int(current['fee'])-alloc_fee
            db.execute('INSERT INTO wallet_copy_positions VALUES (?,?,?)',(slice_id,trade['wallet'],json.dumps(closed)))
            db.execute('UPDATE wallet_copy_positions SET body=? WHERE id=?',(json.dumps(current),trade['id']))
            credit=payout-exit_fee
            db.execute('UPDATE wallet_copy_accounts SET cash=cash+? WHERE wallet=?',(credit,trade['wallet']))
            db.execute('INSERT INTO wallet_copy_ledger VALUES (?,?,?)',('close:'+slice_id,trade['wallet'],credit))
            db.execute("UPDATE wallet_copy_events SET reason='COPIED_SELL',body=? WHERE wallet=? AND event_key=?",(json.dumps(evidence),row['wallet'],row['event_key']))

    def close(self,trade,payout,fee,now,status,evidence,row=None):
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            current=json.loads(db.execute('SELECT body FROM wallet_copy_positions WHERE id=?',(trade['id'],)).fetchone()[0])
            if current['status'] not in ('OPEN','RESOLVED'):return
            current.update(status=status,payout=payout,exit_fee=fee,closed_at=now,resolved=now,
                pnl_micro=payout-fee-current['cost']-current['fee'],exit_evidence=evidence)
            db.execute('UPDATE wallet_copy_positions SET body=? WHERE id=?',(json.dumps(current),trade['id']))
            db.execute('UPDATE wallet_copy_accounts SET cash=cash+? WHERE wallet=?',(payout-fee,trade['wallet']))
            db.execute('INSERT INTO wallet_copy_ledger VALUES (?,?,?)',('close:'+trade['id'],trade['wallet'],payout-fee))
            if row:db.execute("UPDATE wallet_copy_events SET reason='COPIED_SELL',body=? WHERE wallet=? AND event_key=?",(json.dumps(evidence),row['wallet'],row['event_key']))

    async def settle(self):
        now=self.clock()
        with self.store.connect() as db:trades=self.positions(db)
        for trade in trades:
            if trade['status']=='RESOLVED':
                if now>=trade['official_seen_at']+300:self.close(trade,trade['official_payout'],0,now,'SETTLED',trade['official_evidence'])
                continue
            if trade['status']!='OPEN' or now<trade['end']:continue
            raw=await asyncio.to_thread(self.fetch,'https://clob.polymarket.com/markets/'+quote(trade['condition'],safe=''))
            if raw.get('condition_id')!=trade['condition']:raise ValueError('SETTLEMENT_CONDITION_MISMATCH')
            winners=[t for t in raw.get('tokens',[]) if t.get('winner') is True]
            if raw.get('closed') is not True or len(winners)!=1:continue
            tokens={str(t['token_id']) for t in raw['tokens']}
            if trade['token'] not in tokens:raise ValueError('SETTLEMENT_TOKEN_MISMATCH')
            trade.update(status='RESOLVED',official_seen_at=self.clock(),official_evidence=raw,
                official_payout=trade['shares'] if str(winners[0]['token_id'])==trade['token'] else 0)
            with self.store.connect() as db:db.execute('UPDATE wallet_copy_positions SET body=? WHERE id=?',(json.dumps(trade),trade['id']))

    def _due_reviews(self, now):
        with self.store.connect() as db:
            return due_skip_reviews(db, now)

    async def _refresh_watch(self):
        try:
            self.watch=await asyncio.to_thread(build_watch, self.store, self.clock())
            self.watch_at=self.clock()
            self.store.set('wallet_watch_error', {})
        except Exception as error:
            self.store.set('wallet_watch_error', {'at': self.clock(), 'error': str(error)[:200]})

    async def _reconcile_sources(self):
        """Block-scoped token balances. The copy loop keeps running on the other task."""
        from .source_chain import reconcile_recent
        try:
            await asyncio.to_thread(reconcile_recent, self.store, self.clock())
        except Exception as error:
            self.store.set('wallet_source_anchor_error', {
                'at': self.clock(), 'error': type(error).__name__})

    async def upkeep(self):
        """Settlement and skip review, beside the copy path instead of inside it.

        Settling an ended window costs one request per position. Running that
        before new activity delayed a fresh copy by up to three seconds.
        The watch summary is a read on another thread. It does not scan from step().
        """
        while True:
            await self._reconcile_sources()
            await asyncio.to_thread(self._write_flow)
            await self._refresh_watch()
            try:
                from .wallet_observation import observe_batch
                await observe_batch(self)
                self.store.set('wallet_observation_error', {})
            except Exception as error:
                self.store.set('wallet_observation_error', {'at': self.clock(), 'error': str(error)[:200]})
            for job, key, width in ((self.settle, 'wallet_copy_settlement_error', 400),
                                    (self.review_skips, 'wallet_skip_review_error', 200)):
                try:
                    await job()
                    self.store.set(key, {})
                except Exception as error:
                    self.store.set(key, {'at': self.clock(), 'error': str(error)[:width]})
            await self.sleep(30)

    def _load_pending(self, active):
        with self.store.connect() as db:
            has=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='wallet_activity'").fetchone()
            return self.pending_activity(db, active) if has else []

    async def step(self):
        try:
            # Observer wakes this loop immediately after persisting new activity.
            # The read runs off the event loop so a slow query cannot freeze RTDS.
            active=list(get_active_wallets(self.store))
            rows=await asyncio.to_thread(self._load_pending, active)
            await self._apply_batch(rows)
            # A hypothetical ticket stays on the direct process() path.
            # The full decision-table scan is cached inside publish.
            if rows or self.clock()-self.last_publish>=2:
                self.publish('RUNNING');self.last_publish=self.clock()
            self.store.set('wallet_copy_error',{})
        except Exception as error:
            # A ledger mismatch blocks further execution until process/operator review.
            self.store.set('wallet_copy_error',{'at':self.clock(),'error':str(error)[:400]})
            raise

    def _write_flow(self):
        now=self.clock()
        roster=(self.store.get('wallet_roster') or {}).get('wallets') or {}
        copying=[wallet for wallet,row in roster.items() if row.get('state') in ('paper_test','paper_active')]
        last_signal_at=None
        copy_wallet_signals=0
        recent_copied_buys=0
        with self.store.connect() as db:
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='wallet_activity'").fetchone():
                since=now-FLOW_WINDOW
                row=db.execute(
                    """SELECT MAX(source_ts) FROM wallet_activity
                       WHERE first_seen>=? AND json_extract(body,'$.side') IN ('BUY','SELL')""",
                    (since,)).fetchone()
                last_signal_at=row[0] if row else None
                if copying:
                    marks=','.join('?'*len(copying))
                    copy_wallet_signals=db.execute(
                        f"""SELECT COUNT(*) FROM wallet_activity
                            WHERE first_seen>=? AND wallet IN ({marks})
                              AND json_extract(body,'$.side') IN ('BUY','SELL')""",
                        (since,*copying)).fetchone()[0]
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='wallet_copy_events'").fetchone():
                recent_copied_buys=db.execute(
                    "SELECT COUNT(*) FROM wallet_copy_events WHERE reason='COPIED_BUY' AND ts>=?",
                    (now-FLOW_WINDOW,)).fetchone()[0]
        down=False
        if copying:
            down=True
            for wallet in copying:
                obs=self.store.get('wallet_observer:'+wallet) or {}
                checked=obs.get('checked_at') or 0
                if obs.get('status')!='ERROR' and now-checked<=120:
                    down=False
                    break
        flow=decide_copy_flow(now,len(copying),last_signal_at,copy_wallet_signals,recent_copied_buys,down)
        self.store.set('wallet_copy_flow',flow)
        return flow

    async def run(self):
        await asyncio.to_thread(self._write_flow)
        upkeep=asyncio.create_task(self.upkeep())
        try:
            while True:
                self.store.wallet_activity_ready.clear()
                try:await self.step()
                except CopyLedgerError:
                    log.error('copy ledger mismatch; retrying in 30s')
                    await self.sleep(30)
                    continue
                except Exception:
                    await self.sleep(10)
                    continue
                try:await asyncio.wait_for(self.store.wallet_activity_ready.wait(),timeout=1)
                except asyncio.TimeoutError:pass
        finally:
            upkeep.cancel()
