"""Fresh, consistent read-only export. Local calendar days, including DST boundaries."""
import datetime as dt
import json
import time
from zoneinfo import ZoneInfo
from .mid_window import SPEC

ZONE=ZoneInfo('Europe/Stockholm')

def bounds(day):
    return (dt.datetime.combine(day,dt.time(),ZONE).timestamp(),
            dt.datetime.combine(day+dt.timedelta(days=1),dt.time(),ZONE).timestamp())

def build_report(store, day=None, now=None):
    now=time.time() if now is None else now
    today=dt.datetime.fromtimestamp(now,ZONE).date()
    day=dt.date.fromisoformat(day) if day else today-dt.timedelta(days=1)
    if day>=today:raise ValueError('Select a completed Stockholm day')
    start,end=bounds(day)
    with store.connect() as db:
        db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
        def state(key):
            r=db.execute('SELECT body FROM state WHERE key=?',(key,)).fetchone()
            return json.loads(r[0]) if r else {}
        worker=state('worker');model=state('model')
        accounts=[];daily=[]
        for a in db.execute('SELECT * FROM accounts'):
            rows=[dict(r) for r in db.execute('SELECT * FROM positions WHERE strategy=? ORDER BY resolved,id',(a['strategy'],))]
            settled=[r for r in rows if r['payout'] is not None]
            pnl=lambda r:r['payout']-r['cost']-r['fee']-r['exit_fee']
            closed=[r for r in settled if start<=r['resolved']<end]
            entries=[r for r in rows if start<=r['opened']<end]
            cumulative=peak=dd=0
            for r in settled:
                cumulative+=pnl(r);peak=max(peak,cumulative);dd=max(dd,peak-cumulative)
            losses=[sum(max(0,-pnl(r)) for r in settled if now-h<=r['resolved']<=now)/1e6 for h in (86400,7*86400)]
            first=db.execute('SELECT MIN(ts) FROM decisions WHERE strategy=?',(a['strategy'],)).fetchone()[0]
            reasons=[dict(r) for r in db.execute('SELECT reason,COUNT(*) recorded_events,COUNT(DISTINCT market) markets FROM decisions WHERE strategy=? AND ts>=? AND ts<? GROUP BY reason',(a['strategy'],start,end))]
            daily.append({'id':a['strategy'],'date':str(day),'entries':len(entries),'closed':len(closed),
                          'net_pnl_usd':sum(pnl(r) for r in closed)/1e6,
                          'profitable_closes':sum(pnl(r)>0 for r in closed),
                          'entry_fees_paid_usd':sum(r['fee'] for r in entries)/1e6,
                          'exit_fees_paid_usd':sum(r['exit_fee'] for r in closed)/1e6,
                          'unique_entry_windows':len({r['market'] for r in entries}),
                          'recorded_decisions':reasons,
                          'no_new_entries':not entries,'first_recorded_decision_at':first,
                          'active_in_period':first is not None and first<end})
            accounts.append({'id':a['strategy'],'initial':a['initial']/1e6,'cash':a['cash']/1e6,
                             'pnl':cumulative/1e6,'fees':sum(r['fee']+r['exit_fee'] for r in rows)/1e6,
                             'trades':len(rows),'settled':len(settled),'wins':sum(pnl(r)>0 for r in settled),
                             'unique_windows':len({r['market'] for r in rows}),'realized_drawdown_usd':dd/1e6,
                             'open_cost':sum(r['cost']+r['fee'] for r in rows if r['status']=='OPEN')/1e6,
                             'pending':sum(r['payout'] for r in rows if r['status']=='RESOLVED')/1e6,
                             'gross_losses_24h_usd':losses[0],'gross_losses_7d_usd':losses[1],
                             'loss_limit_24h_usd':a['initial']*.03/1e6,'loss_limit_7d_usd':a['initial']*.06/1e6})
        # Include all available daily rows, explicitly flag any lifetime trade truncation.
        columns='id,strategy,market,side,shares,cost,fee,exit_fee,opened,status,payout,resolved,redeemed'
        total=db.execute('SELECT COUNT(*) FROM positions').fetchone()[0]
        trades=[dict(r) for r in db.execute('SELECT '+columns+' FROM positions ORDER BY id DESC LIMIT 10000')]
        day_trades=[dict(r) for r in db.execute('SELECT '+columns+' FROM positions WHERE (opened>=? AND opened<?) OR (resolved>=? AND resolved<?) ORDER BY id',(start,end,start,end))]
        counts={'observations':db.execute('SELECT COUNT(*) FROM observations').fetchone()[0],
                'labels':db.execute('SELECT COUNT(*) FROM labels').fetchone()[0],
                'examples':db.execute('SELECT COUNT(*) FROM examples').fetchone()[0]}
        recorded=[dict(r) for r in db.execute('SELECT kind,COUNT(*) count,MIN(ts) first_ts,MAX(ts) last_ts FROM observations WHERE ts>=? AND ts<? GROUP BY kind',(start,end))]
        heartbeat=worker.get('heartbeat')
        return {'schema':'btc-daily-report-v2','report_id':f'{day}-Europe-Stockholm',
                'source':'PAPER_SERVICE','mode':'PAPER','live_enabled':False,
                'exported_at':dt.datetime.fromtimestamp(now,dt.timezone.utc).isoformat(),'generated_at':now,
                'period':{'date':str(day),'timezone':'Europe/Stockholm','start':start,'end_exclusive':end},
                'worker':worker,'heartbeat_age_seconds':now-heartbeat if heartbeat else None,
                'worker_fresh_at_export':heartbeat is not None and 0<=now-heartbeat<30,
                'reference':state('reference'),'model':model,'counts':counts,
                'exit_comparison_cumulative':state('exit_comparison'),
                'exit_comparison_error':state('exit_comparison_error'),
                'daily':daily,'accounts':accounts,'trades':trades,'period_trades':day_trades,
                'trades_truncated':total>len(trades),'total_trades':total,'trade_integer_scale':1000000,
                'recorded_data_in_period':recorded,'experiment':SPEC,
                'limitations':['Lifetime balances repeat when no trades close; daily is a separate period.',
                    'Decision events are throttled; counts are not opportunity counts or uptime.',
                    'Exports overlap: deduplicate trades by id, daily summaries by strategy and period.',
                    'No raw orderbook replay in this export. CLOSED is a simulated sale, not official settlement.',
                    'Model validation is not net profitability. Never compare different strategy start dates as equal exposure.']}
