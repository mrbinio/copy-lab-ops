"""Deterministic execution and transactional paper ledger, amounts in microdollars."""
import json
import sqlite3
import time
from contextlib import contextmanager
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from pathlib import Path

D = Decimal
SCALE = D(1_000_000)
STRATEGIES = {"value-v1": "Reference-aware value", "late-v1": "Late direction baseline", "early-v1": "Early direction baseline"}

class LedgerError(ValueError):
    """Requires explicit operator review before entries resume."""

def units(x, rounding=ROUND_FLOOR):
    return int((D(str(x)) * SCALE).to_integral_value(rounding=rounding))

def number(x):
    value = D(str(x))
    if not value.is_finite():
        raise ValueError("non-finite amount")
    return value

def simulate_fill(asks, notional, limit, fee_rate, min_shares, tick, depth_fraction="0.5"):
    """Full-notional FOK approximation at arrival snapshot; never infer queue position.

    Displayed depth haircut is applied before execution. Fees round UP per fill;
    shares round DOWN to six decimals. Fee exponent other than 1 is unsupported.
    """
    budget, cap, rate, tick, minimum, depth = map(number, (notional, limit, fee_rate, tick, min_shares, depth_fraction))
    if not (budget > 0 and 0 < cap < 1 and 0 <= rate <= 1 and tick > 0 and minimum > 0 and 0 < depth <= 1):
        raise ValueError("invalid execution parameters")
    cap = (cap / tick).to_integral_value(rounding=ROUND_FLOOR) * tick
    levels = sorted((number(p), number(q)) for p, q in asks)
    if any(not (0 < p < 1 and q >= 0 and p % tick == 0) for p, q in levels):
        raise ValueError("invalid book level")
    remaining, shares, spent, fee = budget, D(0), D(0), 0
    fills = []
    for p, q in levels:
        if p > cap:
            break
        take = min(q * depth, remaining / p).quantize(D("0.000001"), rounding=ROUND_FLOOR)
        if take <= 0:
            continue
        cost = take * p
        fee_piece = units(take * rate * p * (1-p), ROUND_CEILING)
        shares += take
        spent += cost
        fee += fee_piece
        remaining -= cost
        fills.append({"price": str(p), "shares": str(take), "fee_micro": fee_piece})
        if remaining < D("0.000001"):
            break
    if remaining >= D("0.000001") or shares < minimum:
        return None
    return {"shares": units(shares), "cost": units(spent, ROUND_CEILING), "fee": fee,
            "vwap": float(spent / shares), "limit": str(cap), "fills": fills}

class Store:
    def __init__(self, path, initial=500):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
              PRAGMA journal_mode=WAL;
              CREATE TABLE IF NOT EXISTS accounts (strategy TEXT PRIMARY KEY, initial INTEGER NOT NULL, cash INTEGER NOT NULL);
              CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY, strategy TEXT NOT NULL, market TEXT NOT NULL, side TEXT NOT NULL,
                shares INTEGER NOT NULL, cost INTEGER NOT NULL, fee INTEGER NOT NULL,
                opened REAL NOT NULL, status TEXT NOT NULL, payout INTEGER, resolved REAL, redeemed REAL,
                evidence TEXT NOT NULL, UNIQUE(strategy,market));
              CREATE TABLE IF NOT EXISTS ledger (id INTEGER PRIMARY KEY, event_key TEXT UNIQUE NOT NULL,
                strategy TEXT NOT NULL, kind TEXT NOT NULL, amount INTEGER NOT NULL, ts REAL NOT NULL);
              CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, body TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS observations (id INTEGER PRIMARY KEY, ts REAL NOT NULL, kind TEXT NOT NULL, body TEXT NOT NULL);
              CREATE INDEX IF NOT EXISTS observations_time ON observations(ts);
              CREATE TABLE IF NOT EXISTS decisions (id INTEGER PRIMARY KEY, ts REAL NOT NULL, strategy TEXT NOT NULL,
                market TEXT NOT NULL, reason TEXT NOT NULL, body TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS labels (market TEXT PRIMARY KEY, winner TEXT NOT NULL, ts REAL NOT NULL, evidence TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS examples (market TEXT PRIMARY KEY, ts REAL NOT NULL, body TEXT NOT NULL);
            ''')
            for strategy in STRATEGIES:
                db.execute("INSERT OR IGNORE INTO accounts VALUES (?,?,?)", (strategy, units(initial), units(initial)))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=10000")
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def set(self, key, value):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO state VALUES (?,?)", (key, json.dumps(value, allow_nan=False)))

    def get(self, key, default=None):
        with self.connect() as db:
            row = db.execute("SELECT body FROM state WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def record(self, kind, body, ts=None):
        with self.connect() as db:
            db.execute("INSERT INTO observations(ts,kind,body) VALUES (?,?,?)", (ts or time.time(), kind, json.dumps(body, allow_nan=False)))

    def decide(self, strategy, market, reason, body, ts):
        with self.connect() as db:
            db.execute("INSERT INTO decisions(ts,strategy,market,reason,body) VALUES (?,?,?,?,?)", (ts,strategy,market,reason,json.dumps(body,allow_nan=False)))

    def open(self, strategy, market, side, fill, evidence, ts):
        if strategy not in STRATEGIES or side not in ("Up","Down"):
            raise ValueError("invalid strategy/side")
        if fill["shares"] <= 0 or fill["cost"] <= 0 or fill["fee"] < 0:
            raise ValueError("invalid fill")
        amount = fill["cost"] + fill["fee"]
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            a = db.execute("SELECT * FROM accounts WHERE strategy=?", (strategy,)).fetchone()
            if db.execute("SELECT 1 FROM positions WHERE strategy=? AND (market=? OR status IN ('OPEN','RESOLVED'))", (strategy,market)).fetchone():
                return "EXPOSURE_OR_DUPLICATE"
            # Research all-in ceiling is 1.1% of initial bankroll ($5 + fees on $500).
            # Worst-case loss is included in day/week budgets before accepting a fill.
            losses = []
            for horizon in (86400, 7*86400):
                row = db.execute("SELECT COALESCE(SUM(MIN(0,payout-cost-fee)),0) FROM positions WHERE strategy=? AND resolved>=?", (strategy,ts-horizon)).fetchone()
                losses.append(-row[0])
            if amount > a['initial'] * .011 or losses[0]+amount > a['initial']*.03 or losses[1]+amount > a['initial']*.06:
                return "RISK_LIMIT"
            if a['cash'] < amount:
                return "INSUFFICIENT_CASH"
            equity = peak = a['initial']
            # Realised P&L drawdown, evaluated after complete redemptions below.
            pnls = db.execute("SELECT payout-cost-fee FROM positions WHERE strategy=? AND status='REDEEMED' ORDER BY redeemed", (strategy,)).fetchall()
            for row in pnls:
                equity += row[0]
                peak = max(peak,equity)
            if peak-equity+amount > peak*.08:
                return "DRAWDOWN_LIMIT"
            payload = json.dumps({**evidence,"execution":fill}, allow_nan=False)
            db.execute("INSERT INTO positions(strategy,market,side,shares,cost,fee,opened,status,evidence) VALUES (?,?,?,?,?,?,?,'OPEN',?)", (strategy,market,side,fill['shares'],fill['cost'],fill['fee'],ts,payload))
            db.execute("UPDATE accounts SET cash=cash-? WHERE strategy=?", (amount,strategy))
            db.execute("INSERT INTO ledger(event_key,strategy,kind,amount,ts) VALUES (?,?,?,?,?)", (f"entry:{strategy}:{market}",strategy,"ENTRY",-amount,ts))
        return "FILLED"

    def resolve(self, market, winner, evidence, ts):
        if winner not in ("Up","Down") or evidence.get("source") != "clob_official_winner" or evidence.get("closed") is not True:
            raise ValueError("official binary resolution required")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT winner FROM labels WHERE market=?", (market,)).fetchone()
            if old and old[0] != winner:
                raise LedgerError("resolution conflict: pause and review")
            db.execute("INSERT OR IGNORE INTO labels VALUES (?,?,?,?)", (market,winner,ts,json.dumps(evidence)))
            db.execute("UPDATE positions SET status='RESOLVED', payout=CASE WHEN side=? THEN shares ELSE 0 END, resolved=? WHERE market=? AND status='OPEN'", (winner,ts,market))

    def redeem(self, now, delay=300):
        """PAPER cash release after explicit delay; not an on-chain redemption claim."""
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            for p in db.execute("SELECT * FROM positions WHERE status='RESOLVED' AND resolved<=?", (now-delay,)).fetchall():
                db.execute("INSERT INTO ledger(event_key,strategy,kind,amount,ts) VALUES (?,?,?,?,?)", (f"redeem:{p['id']}",p['strategy'],"PAPER_REDEMPTION",p['payout'],now))
                db.execute("UPDATE accounts SET cash=cash+? WHERE strategy=?", (p['payout'],p['strategy']))
                db.execute("UPDATE positions SET status='REDEEMED', redeemed=? WHERE id=?", (now,p['id']))

    def audit(self):
        with self.connect() as db:
            for a in db.execute("SELECT * FROM accounts"):
                delta = db.execute("SELECT COALESCE(SUM(amount),0) FROM ledger WHERE strategy=?", (a['strategy'],)).fetchone()[0]
                if a['cash'] < 0 or a['cash'] != a['initial']+delta:
                    raise LedgerError("ledger cash invariant violated")

    def snapshot(self):
        with self.connect() as db:
            accounts = []
            for a in db.execute("SELECT * FROM accounts"):
                positions = [dict(p) for p in db.execute("SELECT * FROM positions WHERE strategy=? ORDER BY opened", (a['strategy'],))]
                settled = [p for p in positions if p['payout'] is not None]
                curve, cumulative = [],0
                for p in sorted(settled,key=lambda p:p['resolved']):
                    cumulative += p['payout']-p['cost']-p['fee']
                    curve.append({"ts":p['resolved'],"pnl":cumulative/1e6})
                exposure = sum(p['cost']+p['fee'] for p in positions if p['status']=='OPEN')
                pending = sum(p['payout'] for p in positions if p['status']=='RESOLVED')
                accounts.append({"id":a['strategy'],"name":STRATEGIES[a['strategy']],"cash":a['cash']/1e6,
                    "initial":a['initial']/1e6,"pnl":cumulative/1e6,"fees":sum(p['fee'] for p in positions)/1e6,
                    "open_cost":exposure/1e6,"pending":pending/1e6,"trades":len(positions),"settled":len(settled),
                    "wins":sum(p['payout']>0 for p in settled),"curve":curve[-300:]})
            trades = [dict(p) for p in db.execute("SELECT id,strategy,market,side,shares,cost,fee,opened,status,payout,resolved FROM positions ORDER BY id DESC LIMIT 100")]
            decisions = [dict(d) for d in db.execute("SELECT ts,strategy,market,reason FROM decisions ORDER BY id DESC LIMIT 25")]
            count = db.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
            labels = db.execute("SELECT COUNT(*) FROM labels").fetchone()[0]
        return {"mode":"PAPER","live_enabled":False,"accounts":accounts,"trades":trades,"decisions":decisions,
                "observations":count,"labels":labels,"worker":self.get("worker",{}),"market":self.get("market",{}),
                "reference":self.get("reference",{}),"model":self.get("model",{"status":"COLLECTING","samples":0}),
                "price_history":self.get("price_history",[]),"generated_at":time.time()}
