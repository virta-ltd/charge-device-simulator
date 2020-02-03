import asyncio
import logging

import coloredlogs
from runtime import ExecutorCli

coloredlogs.install(logging.DEBUG)
executor = ExecutorCli()
executor.initialize()
asyncio.run(executor.execute())
