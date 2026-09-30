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
        self.assertEqual(delays,[2,4,1])
