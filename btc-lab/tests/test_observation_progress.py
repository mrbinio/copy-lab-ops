import asyncio, json, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace
from lab.core import Store
from lab.wallet_observation import ensure_schema, settle_batch, refresh_roster, ensure_meta
from lab.wallet_roster import bootstrap, admit_observed
class ProgressTests(unittest.TestCase):
 def test_unresolved_rows_do_not_starve_after_restart(self):
  with tempfile.TemporaryDirectory() as d:
   store=Store(Path(d)/'lab.db')
   with store.connect() as db:
    ensure_schema(db)
    for i in range(9):
     t=dict(id=str(i),wallet='w',status='OPEN',end=100,condition=str(i),token='yes',shares=5000000,cost=3000000,fee=100000)
     db.execute('INSERT INTO wallet_observation_positions VALUES (?,?,?)',(str(i),'w',json.dumps(t)))
   calls=[]
   def fetch(url):
    c=url.rsplit('/',1)[-1]; calls.append(c)
    return dict(condition_id=c,closed=c=='8',tokens=[dict(token_id='yes',winner=c=='8')])
   asyncio.run(settle_batch(SimpleNamespace(store=store,clock=lambda:1000,fetch=fetch)))
   self.assertEqual(calls,list(map(str,range(8))))
   asyncio.run(settle_batch(SimpleNamespace(store=store,clock=lambda:1001,fetch=fetch)))
   self.assertEqual(calls,list(map(str,range(9))))
   asyncio.run(settle_batch(SimpleNamespace(store=store,clock=lambda:1302,fetch=fetch)))
   with store.connect() as db:
    t=json.loads(db.execute("SELECT body FROM wallet_observation_positions WHERE id='8'").fetchone()[0])
   self.assertEqual(t['status'],'SETTLED'); self.assertEqual(t['pnl_micro'],1900000)
 def test_promotion_without_hourly_discovery(self):
  with tempfile.TemporaryDirectory() as d:
   store=Store(Path(d)/'lab.db'); bootstrap(store,10)
   w='0x'+'a'*40; admit_observed(store,w,10,{},'test'); meta=ensure_meta(store,10)
   with store.connect() as db:
    ensure_schema(db)
    for i in range(20):
     t=dict(policy=meta['version'],opened=20,closed_at=30,status='SETTLED',pnl_micro=10000,fee=100,market=str(i%5))
     db.execute('INSERT INTO wallet_observation_positions VALUES (?,?,?)',(str(i),w,json.dumps(t)))
   state,changed=refresh_roster(store,40)
   self.assertEqual(state['wallets'][w]['state'],'paper_test'); self.assertIn(w,changed)
