import device
from typing import Dict, Any, Optional


class ConfigParser():

    def parse_simulator(self, device_target: device.DeviceAbstract, config) -> device.Simulator:
        if device_target is None:
            return None
        if 'error_exit' in config:
            device_target.error_exit = config['error_exit']

        result = device.Simulator(device_target)
        result.flow_charge_options = config['flow_charge_options']
        result.frequent_flow_enabled = config['frequent_flow_enabled']
        if 'frequent_flows' in config:
            for ff in config['frequent_flows']:
                result.frequent_flows[device.Flows(ff['flow'])] = device.FrequentFlowOptions(
                    ff['delay_seconds'],
                    ff['count']
                )
        result.is_interactive = config['is_interactive']
        return result

    def parse_device(self, config) -> device.DeviceAbstract:
        result: Optional[device.DeviceAbstract] = None
        if config['type'] == 'ocpp-j':
            dev1 = device.DeviceOcppJ(config['spec_identifier'])
            dev1.server_address = config['server_address']
            if 'spec_chargeBoxSerialNumber' in config:
                dev1.spec_chargeBoxSerialNumber = config['spec_chargeBoxSerialNumber']
            if 'spec_chargePointModel' in config:
                dev1.spec_chargePointModel = config['spec_chargePointModel']
            if 'spec_chargePointVendor' in config:
                dev1.spec_chargePointVendor = config['spec_chargePointVendor']
            if 'spec_firmwareVersion' in config:
                dev1.spec_firmwareVersion = config['spec_firmwareVersion']
            if 'spec_iccid' in config:
                dev1.spec_iccid = config['spec_iccid']
            if 'spec_imsi' in config:
                dev1.spec_imsi = config['spec_imsi']
            if 'spec_meterType' in config:
                dev1.spec_meterType = config['spec_meterType']
            if 'spec_meterSerialNumber' in config:
                dev1.spec_meterSerialNumber = config['spec_meterSerialNumber']
            result = dev1
        elif config['type'] == 'ensto':
            dev1 = device.DeviceEnsto(config['spec_identifier'])
            dev1.server_host = config['server_host']
            dev1.server_port = config['server_port']
            if 'spec_vendor' in config:
                dev1.spec_vendor = config['spec_vendor']
            if 'spec_model' in config:
                dev1.spec_model = config['spec_model']
            if 'spec_sw' in config:
                dev1.spec_sw = config['spec_sw']
            result = dev1

        if 'register_on_initialize' in config:
            result.register_on_initialize = config['register_on_initialize']

        return result
