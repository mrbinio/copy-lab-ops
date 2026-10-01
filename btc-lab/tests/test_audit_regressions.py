import asyncio,tempfile
from pathlib import Path
from unittest.mock import AsyncMock,patch
from lab.core import Store,simulate_fill,LedgerError
from lab.worker import Worker
async def check(error,stage='reconciliation'):
 with tempfile.TemporaryDirectory() as d:
  s=Store(Path(d)/'db');w=Worker(s,d);now=1800000300;start=1800000000;slug=f'btc-updown-15m-{start}'
  s.open('mid-window-v1',slug,'Up',simulate_fill([['.60','100']],'4.67','.60','.07','5','.01'),{'risk_policy':'btc-stop10-v1'},start+200)
  def b(ts):return {'source_ts':ts,'bids':[['.50','100']],'asks':[['.60','100']],'min_shares':'5','tick':'.01'}
  m=dict(slug=slug,start=start,accepting=True,fee_verified=True,rule_supported=True,fee_rate=.07,books={'Up':b(now)})
  w.books=AsyncMock(return_value={'Up':b(now+.1)});w.last_research=now;s.set('model',{'feature_schema':'spot-v1'})
  w.reconcile=AsyncMock(side_effect=error if stage=='reconciliation' else None)
  async def cycle(entries_allowed=True):
   if stage=='collection':raise error
   await w.paper_exits(m,entries_allowed)
  w.cycle=cycle
  with patch('lab.worker.time.time',return_value=now),patch('lab.worker.asyncio.sleep',new_callable=AsyncMock):
   await w.iteration()
   if stage=='collection':await w.paper_exits(m,False)
  with s.connect() as db:status=db.execute('SELECT status FROM positions').fetchone()[0]
  return w.ledger_ok,status

import asyncio,json,tempfile
from pathlib import Path
from unittest.mock import patch,AsyncMock
from lab.core import Store,simulate_fill,LedgerError
from lab.worker import Worker

async def exit_probe(strategy,policy,elapsed,corrupt=False,same=False):
 with tempfile.TemporaryDirectory() as d:
  s=Store(Path(d)/'db');w=Worker(s,d);start=1800000000;now=start+elapsed;slug=f'btc-updown-15m-{start}'
  f=simulate_fill([['.60','100']],'4.67','.60','.07','5','.01');s.open(strategy,slug,'Up',f,{'risk_policy':policy},start+200)
  if corrupt:
   with s.connect() as db:db.execute('UPDATE accounts SET cash=cash+1000000 WHERE strategy=?',(strategy,))
   try:s.audit()
   except LedgerError:pass
   else:raise AssertionError('corruption not detected')
  def book(ts):return {'source_ts':ts,'bids':[['.50','100']],'asks':[['.60','100']],'min_shares':'5','tick':'.01'}
  m={'slug':slug,'start':start,'accepting':True,'fee_verified':True,'rule_supported':True,'fee_rate':.07,'books':{'Up':book(now)}}
  w.books=AsyncMock(return_value={'Up':book(now if same else now+.1)})
  with patch('lab.worker.time.time',return_value=now),patch('lab.worker.asyncio.sleep',new_callable=AsyncMock):await w.paper_exits(m,False)
  with s.connect() as db:status=db.execute('SELECT status FROM positions').fetchone()[0]
  return status

async def entry_probe():
 with tempfile.TemporaryDirectory() as d:
  s=Store(Path(d)/'db');w=Worker(s,d);clock=[9299.9];w.reference={'price':70100,'source_ts':9299.9,'received_at':9299.9};w.history.append((9000,70000))
  raw={'slug':'btc-updown-15m-9000','conditionId':'c','outcomes':'["Up","Down"]','clobTokenIds':'["u","d"]','active':True,'closed':False,'acceptingOrders':True,'feesEnabled':True,'feeSchedule':{'rate':.07,'exponent':1},'description':'Bitcoin at the end is greater than or equal to the beginning. Source: Chainlink.'}
  def fetch(url):
   if '/markets/slug/' in url:return raw
   token=url.split('token_id=')[1]
   return {'asset_id':token,'timestamp':int(clock[0]*1000),'asks':[{'price':'.60','size':'100'}],'bids':[{'price':'.59','size':'100'}],'min_order_size':'5','tick_size':'.01'}
  def choose(strategy,m,r,model,now,paused=False):
   if strategy!='mid-window-v2':return None,'TEST_OTHER'
   return {'strategy':strategy,'market':m['slug'],'side':'Up','limit':.61,'probability':None,'decision_at':now,'hypothesis':{}},'SIGNAL'
  async def delay(seconds):clock[0]+=.5
  w.choose_entry=choose
  with patch('lab.worker.get_json',side_effect=fetch),patch('lab.worker.time.time',side_effect=lambda:clock[0]),patch('lab.worker.asyncio.sleep',side_effect=delay):await w.cycle()
  with s.connect() as db:rows=[dict(r) for r in db.execute("SELECT strategy,opened FROM positions WHERE strategy='mid-window-v2'")]
  return rows



import unittest
class AuditRegressionTests(unittest.IsolatedAsyncioTestCase):
 async def test_network_failure_allows_exit(self):
  self.assertEqual(await check(TimeoutError('network')),(True,'OPEN'))
 async def test_reconciliation_ledger_failure_blocks_exit(self):
  self.assertEqual(await check(LedgerError('integrity')),(False,'OPEN'))
 async def test_collection_ledger_failure_blocks_exit(self):
  self.assertEqual(await check(LedgerError('sale'),'collection'),(False,'OPEN'))
 async def test_v2_protected_exit_after_600(self):
  self.assertEqual(await exit_probe('mid-window-v2','btc-mid-v2-stop10',650),'OPEN')
 async def test_same_arrival_timestamp_blocks_exit(self):
  self.assertEqual(await exit_probe('mid-window-v1','btc-stop10-v1',300,same=True),'OPEN')
 async def test_newer_arrival_allows_exit(self):
  self.assertEqual(await exit_probe('mid-window-v1','btc-stop10-v1',300),'OPEN')
 async def test_v2_arrival_after_entry_window_is_rejected(self):
  self.assertEqual(await entry_probe(),[])
