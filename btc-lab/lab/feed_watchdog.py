"""Reconnect silent target streams even if unrelated messages/PONG keep arriving."""
import asyncio
import time


def next_backoff(seconds, cap=30):
    """Double the wait after a failed handshake. Cap it so a dead host is not a spin loop."""
    try:
        seconds = float(seconds)
    except (TypeError, ValueError):
        seconds = 1
    if seconds < 1:
        seconds = 1
    return min(seconds * 2, cap)

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
