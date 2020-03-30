import yaml
from typing import Any, Dict, List, Optional
from .config_parser import ConfigParser
import device


class ConfigFileReader:
    def __init__(self, file_path: str):
        yaml.add_multi_constructor(
            '',
            self.__any_constructor,
            Loader=yaml.SafeLoader
        )
        self.file_path = file_path
        self.devices: List[device.DeviceAbstract] = []
        self.simulators: List[device.Simulator] = []
        self.__read_file()

    @staticmethod
    def __any_constructor(loader, node):
        if isinstance(node, yaml.MappingNode):
            return loader.construct_mapping(node)
        if isinstance(node, yaml.SequenceNode):
            return loader.construct_sequence(node)
        return loader.construct_scalar(node)

    def __file_load(self, file_path, raw=False):
        with open(file_path, 'r') as fs1:
            if raw:
                template = fs1.read()
            else:
                template = yaml.safe_load(fs1)
        return template

    def __read_file(self):
        file_content: Dict[str, Any] = self.__file_load(self.file_path)
        section = 'devices'
        if section in file_content and file_content[section] is not None:
            self.devices = [
                n for n in [
                    ConfigParser.parse_device(e) for e in file_content[section]
                ]
                if n is not None
            ]

        section = 'simulations'
        if section in file_content and file_content[section] is not None:
            self.simulators = [
                n for n in [
                    ConfigParser.parse_simulator(self.device_find(e['device_name']), e) for e in file_content[section]
                ] if n is not None
            ]
        pass

    def device_find(self, name: str) -> Optional[device.DeviceAbstract]:
        return next((e for e in self.devices if e.name == name), None)

    def simulator_find(self, name: str) -> Optional[device.Simulator]:
        return next((e for e in self.simulators if e.name == name), None)
