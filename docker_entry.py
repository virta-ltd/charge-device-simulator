import asyncio
import logging

import coloredlogs
from executer_cli import ExecuterCli

coloredlogs.install(logging.DEBUG)
executer = ExecuterCli()
executer.initialize()
asyncio.run(executer.execute())
