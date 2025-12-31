import asyncio


async def run_with_delay(to_run, delay_seconds):
    await asyncio.sleep(delay_seconds)
    await to_run
    pass
