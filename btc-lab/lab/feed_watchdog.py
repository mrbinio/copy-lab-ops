"""Reconnect silent target streams even if unrelated messages/PONG keep arriving."""
import asyncio
import time

async def fresh_messages(ws, source_timestamp, timeout=20):
    last=source_timestamp()
    deadline=time.monotonic()+timeout
    while True:
        remaining=deadline-time.monotonic()
        if remaining<=0:
            raise TimeoutError('No new valid TWAP60 observation within watchdog interval')
        try:
            message=await asyncio.wait_for(ws.recv(),timeout=remaining)
        except asyncio.TimeoutError as error:
            raise TimeoutError('No new valid TWAP60 observation within watchdog interval') from error
        yield message
        current=source_timestamp()
        if current is not None and (last is None or current>last):
            last=current
            deadline=time.monotonic()+timeout
