import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, AsyncMock
from lab.core import Store, simulate_fill
from lab.mid_window import exit_intent
from lab.worker import Worker

class StopTests(unittest.IsolatedAsyncioTestCase):
    async def test_stop_after_minute_ten_retries_failed_arrival_and_accounts_fees(self):
        for strategy in ('early-v1','mid-window-v1','eth-mid-window-v1'):
            with self.subTest(strategy=strategy),tempfile.TemporaryDirectory() as d:
                asset='ETH' if strategy.startswith('eth-') else 'BTC'
                store=Store(Path(d)/'db',asset=asset);worker=Worker(store,d);start=1800000000;now=start+650
                slug=f'{asset.lower()}-updown-15m-{start}'
                fill=simulate_fill([['.60','100']],'4.67','.60','.07','5','.01')
                self.assertLessEqual(fill['cost']+fill['fee'],5000000)
                store.open(strategy,slug,'Up',fill,{'risk_policy':asset.lower()+'-stop10-v1'},start+200)
                def book(bid,size='100',now_ts=None):
                    return {'source_ts':now_ts or now,'bids':[[bid,size]],'asks':[['.60','100']],'min_shares':'5','tick':'.01'}
                m={'slug':slug,'start':start,'accepting':True,'fee_verified':True,'rule_supported':True,'fee_rate':.07,'books':{'Up':book('.54')}}
                with store.connect() as db:p=dict(db.execute('SELECT * FROM positions').fetchone())
                if strategy == 'early-v1':
                    # early-v1 retains stop-loss exit logic
                    self.assertEqual(exit_intent(p,m,now)[1],'EXIT_STOP')
                    with patch('lab.worker.time.time',side_effect=lambda:now),patch('lab.worker.asyncio.sleep',new_callable=AsyncMock):
                        worker.books=AsyncMock(return_value={'Up':book('.53',now_ts=now+.1)})
                        await worker.paper_exits(m,True)
                        self.assertEqual(store.snapshot()['trades'][0]['status'],'OPEN')
                        now+=2;m['books']['Up']=book('.53')
                        worker.books=AsyncMock(return_value={'Up':book('.53',now_ts=now+.1)})
                        await worker.paper_exits(m,True)
                    tr=store.snapshot()['trades'][0]
                    self.assertEqual(tr['status'],'CLOSED');self.assertGreater(tr['exit_fee'],0)
                    self.assertLess(tr['payout']-tr['cost']-tr['fee']-tr['exit_fee'],0)
                    store.resolve(slug,'Up',{'source':'clob_official_winner','closed':True},start+901);store.redeem(start+1300);store.audit()
                    self.assertEqual(store.snapshot()['trades'][0]['status'],'CLOSED')
                else:
                    # mid-window-v1 and eth-mid-window-v1 hold to official resolution
                    self.assertEqual(exit_intent(p,m,now)[1],'HOLD_TO_OFFICIAL_RESOLUTION')
                    with patch('lab.worker.time.time',side_effect=lambda:now),patch('lab.worker.asyncio.sleep',new_callable=AsyncMock):
                        worker.books=AsyncMock(return_value={'Up':book('.53',now_ts=now+.1)})
                        await worker.paper_exits(m,True)
                    self.assertEqual(store.snapshot()['trades'][0]['status'],'OPEN')

    async def test_new_policy_is_tighter_without_rewriting_legacy(self):
        m={'start':0,'fee_rate':.07,'books':{'Up':{'source_ts':300,'bids':[['.54','100']],'min_shares':'5','tick':'.01'}}}
        p={'strategy':'mid-window-v1','side':'Up','shares':8000000,'cost':4800000,'fee':134400,'evidence':'{}'}
        self.assertEqual(exit_intent(p,m,300)[1],'HOLD_TO_OFFICIAL_RESOLUTION')
        p['evidence']=json.dumps({'risk_policy':'btc-stop10-v1'})
        self.assertEqual(exit_intent(p,m,300)[1],'HOLD_TO_OFFICIAL_RESOLUTION')
        m['books']['Up']['source_ts']=290
        self.assertEqual(exit_intent(p,m,300)[1],'HOLD_TO_OFFICIAL_RESOLUTION')
        m['books']['Up'].update(source_ts=300,bids=[['.54','1']])
        self.assertEqual(exit_intent(p,m,300)[1],'HOLD_TO_OFFICIAL_RESOLUTION')
