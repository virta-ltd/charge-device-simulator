import argparse
import asyncio
import logging
from typing import Dict, Any, Optional

import coloredlogs
import yaml

import device


def any_constructor(loader, tag_suffix, node):
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    return loader.construct_scalar(node)


def file_load(file_path, raw=False):
    with open(file_path, 'r') as fs1:
        if raw:
            template = fs1.read()
        else:
            template = yaml.safe_load(fs1)
    return template


async def main():
    coloredlogs.install(logging.DEBUG)

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", help="The file path to the config file")
    parser.add_argument(
        "--simulation",
        help="Simulation name (defined in config file) to run"
    )
    args = parser.parse_args()
    config: Dict[str, Any] = file_load(args.config)
    config_simulation = list(filter(lambda x: x['name'] == args.simulation, config['simulations']))[0]
    config_device = list(filter(lambda x: x['name'] == config_simulation['device_name'], config['devices']))[0]

    dev_target: Optional[device.DeviceAbstract] = None
    if config_device['type'] == 'ocpp-j':
        dev1 = device.DeviceOcppJ(config_device['spec_identifier'])
        dev1.server_address = config_device['server_address']
        if 'spec_chargeBoxSerialNumber' in config_device:
            dev1.spec_chargeBoxSerialNumber = config_device['spec_chargeBoxSerialNumber']
        if 'spec_chargePointModel' in config_device:
            dev1.spec_chargePointModel = config_device['spec_chargePointModel']
        if 'spec_chargePointVendor' in config_device:
            dev1.spec_chargePointVendor = config_device['spec_chargePointVendor']
        if 'spec_firmwareVersion' in config_device:
            dev1.spec_firmwareVersion = config_device['spec_firmwareVersion']
        if 'spec_iccid' in config_device:
            dev1.spec_iccid = config_device['spec_iccid']
        if 'spec_imsi' in config_device:
            dev1.spec_imsi = config_device['spec_imsi']
        if 'spec_meterType' in config_device:
            dev1.spec_meterType = config_device['spec_meterType']
        if 'spec_meterSerialNumber' in config_device:
            dev1.spec_meterSerialNumber = config_device['spec_meterSerialNumber']
        dev_target = dev1
    elif config_device['type'] == 'ensto':
        dev1 = device.DeviceEnsto(config_device['spec_identifier'])
        dev1.server_host = config_device['server_host']
        dev1.server_port = config_device['server_port']
        if 'spec_vendor' in config_device:
            dev1.spec_vendor = config_device['spec_vendor']
        if 'spec_model' in config_device:
            dev1.spec_model = config_device['spec_model']
        if 'spec_sw' in config_device:
            dev1.spec_sw = config_device['spec_sw']
        dev_target = dev1

    if dev_target is None:
        return
    if 'register_on_initialize' in config_simulation:
        dev_target.register_on_initialize = config_device['register_on_initialize']
    if 'error_exit' in config_simulation:
        dev_target.error_exit = config_simulation['error_exit']

    simulator1 = device.Simulator(dev_target)
    simulator1.flow_charge_options = config_simulation['flow_charge_options']
    simulator1.frequent_flow_enabled = config_simulation['frequent_flow_enabled']
    if 'frequent_flows' in config_simulation:
        for ff in config_simulation['frequent_flows']:
            simulator1.frequent_flows[device.Flows(ff['flow'])] = device.FrequentFlowOptions(
                ff['delay_seconds'],
                ff['count']
            )
    simulator1.initialize()
    await simulator1.lifecycle_start(is_interactive=config_simulation['is_interactive'])
    simulator1.end()


yaml.add_multi_constructor('', any_constructor, Loader=yaml.SafeLoader)
asyncio.run(main())
