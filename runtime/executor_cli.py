import argparse
from typing import Any, Dict

import device
import yaml

from .config_parser import ConfigParser


class ExecutorCli:
    simulator: device.Simulator = None
    on_error = []

    @staticmethod
    def __any_constructor(loader, node):
        if isinstance(node, yaml.MappingNode):
            return loader.construct_mapping(node)
        if isinstance(node, yaml.SequenceNode):
            return loader.construct_sequence(node)
        return loader.construct_scalar(node)

    @staticmethod
    def __file_load(file_path, raw=False):
        with open(file_path, 'r') as fs1:
            if raw:
                template = fs1.read()
            else:
                template = yaml.safe_load(fs1)
        return template

    def initialize(self, args=None):
        yaml.add_multi_constructor(
            '',
            self.__any_constructor,
            Loader=yaml.SafeLoader
        )
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "--config", help="The file path to the config file")
        parser.add_argument(
            "--simulation",
            help="Simulation name (defined in config file) to run"
        )
        if args is None:
            args = vars(parser.parse_args())
        config: Dict[str, Any] = self.__file_load(args['config'])
        config_simulation = list(
            filter(lambda x: x['name'] == args['simulation'], config['simulations']))[0]
        config_device = list(filter(
            lambda x: x['name'] == config_simulation['device_name'], config['devices']))[0]
        self.simulator = ConfigParser.parse_simulator(
            ConfigParser.parse_device(config_device),
            config_simulation
        )
        self.simulator.name = args['simulation']
        self.simulator.device.name = config_simulation['device_name']
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
            self.simulator.device.handle_error(f"Unexpected Error: {str(e)}", device.ErrorReasons.UnknownException)
