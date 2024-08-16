from typing import Optional

import device


class ConfigParser:

    @staticmethod
    def parse_simulator(device_target: device.DeviceAbstract, config) -> Optional[device.Simulator]:
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
        if 'name' in config:
            result.name = config['name']
        return result

    @staticmethod
    def parse_device(config) -> device.DeviceAbstract:
        result: Optional[device.DeviceAbstract] = None
        if config['type'] == 'ocpp-j':
            dev1 = ConfigParser.create_ocppj_device(config=config)
            if 'server_address' in config:
                dev1.server_address = config['server_address']
            if 'protocols' in config:
                dev1.protocols = config['protocols']
            if 'spec_chargeBoxSerialNumber' in config:
                dev1.spec_chargeBoxSerialNumber = config['spec_chargeBoxSerialNumber']
            if 'spec_chargePointSerialNumber' in config:
                dev1.spec_chargePointSerialNumber = config['spec_chargePointSerialNumber']
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
        if config['type'] == 'ocpp-s':
            dev1 = device.DeviceOcppS(config['spec_identifier'])
            if 'server_address' in config:
                dev1.server_address = config['server_address']
            if 'from_address' in config:
                dev1.from_address = config['from_address']
            if 'protocols' in config:
                dev1.protocols = config['protocols']
            if 'spec_chargeBoxSerialNumber' in config:
                dev1.spec_chargeBoxSerialNumber = config['spec_chargeBoxSerialNumber']
            if 'spec_chargePointSerialNumber' in config:
                dev1.spec_chargePointSerialNumber = config['spec_chargePointSerialNumber']
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
            if 'server_host' in config:
                dev1.server_host = config['server_host']
            if 'server_port' in config:
                dev1.server_port = config['server_port']
            if 'spec_vendor' in config:
                dev1.spec_vendor = config['spec_vendor']
            if 'spec_model' in config:
                dev1.spec_model = config['spec_model']
            if 'spec_sw' in config:
                dev1.spec_sw = config['spec_sw']
            result = dev1

        if 'name' in config:
            result.name = config['name']
        if 'register_on_initialize' in config:
            result.register_on_initialize = config['register_on_initialize']
        if 'error_exit' in config:
            result.error_exit = config['error_exit']
        if 'response_timeout_seconds' in config:
            result.response_timeout_seconds = config['response_timeout_seconds']

        return result

    @staticmethod
    def create_ocppj_device(config) -> device.DeviceAbstract:
        if 'ocpp2.0.1' in config['protocols']:
            return device.DeviceOcppJ201(config['spec_identifier'])
        else:
            return device.DeviceOcppJ16(config['spec_identifier'])