import asyncio
import unittest
from lab.feed_watchdog import fresh_messages

class Socket:
    def __init__(self,message='PONG',delay=.001):self.message=message;self.delay=delay
    async def recv(self):
        await asyncio.sleep(self.delay)
        return self.message

class WatchdogTests(unittest.IsolatedAsyncioTestCase):
    async def test_silence_times_out(self):
        with self.assertRaises(TimeoutError):
            async for _ in fresh_messages(Socket(delay=1),lambda:None,timeout=.02):pass
    async def test_pongs_or_duplicate_source_do_not_extend_deadline(self):
        count=0
        with self.assertRaises(TimeoutError):
            async for _ in fresh_messages(Socket(),lambda:100,timeout=.02):count+=1
        self.assertGreater(count,0)
    async def test_new_valid_source_extends_deadline(self):
        source=[None];count=0
        async for _ in fresh_messages(Socket(delay=.005),lambda:source[0],timeout=.03):
            count+=1;source[0]=count
            if count==15:break
        self.assertEqual(count,15)
    async def test_connection_failure_propagates(self):
        class Broken:
            async def recv(self):raise OSError('disconnected')
        with self.assertRaises(OSError):
            async for _ in fresh_messages(Broken(),lambda:None):pass
