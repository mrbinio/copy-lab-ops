import asyncio
import unittest
from unittest.mock import patch
from lab.wallet_observer import WalletObserver

class Memory:
    def __init__(self):self.data={}
    def get(self,k,default=None):return self.data.get(k,default)

class FastPollTests(unittest.IsolatedAsyncioTestCase):
    async def test_errors_back_off_then_return_to_one_second(self):
        obj=object.__new__(WalletObserver);obj.store=Memory();delays=[];count=0
        obj.store.data['wallet_roster']={'wallets':{'wallet':{'state':'paper_test'}}}
        async def poll(wallet):
            nonlocal count
            count+=1
            obj.store.data['wallet_observer:'+wallet]={'status':'ERROR' if count<3 else 'POLL_OK'}
        async def sleep(seconds):
            delays.append(seconds)
            if len(delays)==3:raise asyncio.CancelledError()
        obj.poll=poll
        with patch('lab.wallet_observer.time.monotonic',return_value=0),patch('lab.wallet_observer.asyncio.sleep',sleep):
            with self.assertRaises(asyncio.CancelledError):await obj.run_wallet('wallet')
        self.assertEqual(delays,[2,4,2])


class PollEveryTests(unittest.TestCase):
    def test_copied_wallets_keep_one_second_others_poll_slower(self):
        obj=object.__new__(WalletObserver);obj.store=Memory()
        obj.store.data['wallet_roster']={'wallets':{'a':{'state':'paper_test'},'b':{'state':'paused'},'c':{'state':'observed'}}}
        self.assertEqual([obj.poll_every(w) for w in 'abc'],[2,60,180])
        self.assertEqual(obj.poll_every('0x943cea746e701823b6902a6f4eaeed58207e77c2'),2)
