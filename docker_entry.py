import asyncio
import logging

import coloredlogs
from .runtime import ExecutorCli

coloredlogs.install(logging.DEBUG)
executer = ExecutorCli()
executer.initialize()
asyncio.run(executer.execute())
