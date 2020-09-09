import argparse
from typing import Any, Dict

import device

from .config_parser import ConfigParser
from .config_file_reader import ConfigFileReader
from runtime.error_message import ErrorMessage


class ExecutorCli:
    simulator: device.Simulator = None
    on_error = []

    def initialize(self, args=None):
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "--config", help="The file path to the config file")
        parser.add_argument(
            "--simulation",
            help="Simulation name (defined in config file) to run"
        )
        if args is None:
            args = vars(parser.parse_args())
        config_reader = ConfigFileReader(file_path=args['config'])
        self.simulator = config_reader.simulator_find(args['simulation'])
        if self.simulator is None:
            raise NameError('Simulation not found')
        self.simulator.on_error = self.on_error
        pass

    async def execute(self):
        if self.simulator is None or self.simulator.device is None:
            return
        try:
            await self.simulator.initialize()
            await self.simulator.lifecycle_start()
            await self.simulator.end()
        except Exception as e:
            await self.simulator.device.handle_error(ErrorMessage(e).get(), device.ErrorReasons.UnknownException)
