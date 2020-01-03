import asyncio
import logging

import coloredlogs

import device


def device_test_ocpp_j_1():
    result = device.DeviceOcppJ("charge_device_test_0001")
    result.spec_chargeBoxSerialNumber = "1234"
    result.spec_chargePointModel = "Model_X"
    result.spec_chargePointVendor = "Vendor_X"
    result.spec_firmwareVersion = "1.1.1"
    result.spec_iccid = "4321"
    result.spec_imsi = "5678"
    result.spec_meterType = "MeterType_X"
    result.spec_meterSerialNumber = "NO_ID"
    return result


def device_test_ocpp_j_2():
    result = device.DeviceOcppJ("charge_device_test_0002")
    result.register_on_initialize = False
    return result


def device_test_ensto_1():
    result = device.DeviceEnsto("charge_device_test_0003")
    result.spec_model = "Model_X"
    result.spec_sw = "SW_X"
    result.spec_vendor = "Vendor_X"
    result.register_on_initialize = True
    return result


async def main():
    coloredlogs.install(logging.DEBUG)
    # dev1 = device_test_ocpp_j_1()
    dev1 = device_test_ensto_1()
    # dev1.server_address = "ws://sample-server.com:80"
    dev1.server_host = "sample-server.com"
    dev1.server_port = 3000

    simulator1 = device.Simulator(dev1)
    simulator1.flow_charge_options = {
        "idTag": "FAKE_RFID"
    }

    simulator1.initialize()
    simulator1.frequent_flows[device.Flows.Heartbeat] = device.FrequentFlowOptions(30, -1)
    # simulator1.frequent_flows[device.Flows.Authorize] = device.FrequentFlowOptions(30, -1)
    # simulator1.frequent_flows[device.Flows.Charge] = device.FrequentFlowOptions(120, 2)
    simulator1.frequent_flow_enabled = True
    await simulator1.lifecycle_start(is_interactive=False)
    simulator1.end()


asyncio.run(main())
