import datetime
import readline

import aioconsole
from device.ocpp_j.abstract_device_ocpp_j import AbstractDeviceOcppJ

from device.error_reasons import ErrorReasons

# Fake call to readline module to make sure it is loaded
# we need this since on OS-X if the readline module is not loaded, the input
# from terminal using input() will be limited to small number of characters
readline.get_completion_type()

class DeviceOcppJ16(AbstractDeviceOcppJ):
    def __init__(self, device_id):
        super().__init__(device_id)
        self.protocols = ['ocpp1.6', 'ocpp1.5']

    async def action_register(self) -> bool:
        action = "BootNotification"
        self.logger.info(f"Action {action} Start")
        json_payload = {}
        if self.spec_chargePointVendor is not None:
            json_payload['chargePointVendor'] = self.spec_chargePointVendor
        if self.spec_chargePointModel is not None:
            json_payload['chargePointModel'] = self.spec_chargePointModel
        if self.spec_chargeBoxSerialNumber is not None:
            json_payload['chargeBoxSerialNumber'] = self.spec_chargeBoxSerialNumber
        if self.spec_firmwareVersion is not None:
            json_payload['firmwareVersion'] = self.spec_firmwareVersion
        if self.spec_iccid is not None:
            json_payload['iccid'] = self.spec_iccid
        if self.spec_imsi is not None:
            json_payload['imsi'] = self.spec_imsi
        if self.spec_meterType is not None:
            json_payload['meterType'] = self.spec_meterType
        if self.spec_meterSerialNumber is not None:
            json_payload['meterSerialNumber'] = self.spec_meterSerialNumber
        if self.spec_chargePointSerialNumber is not None:
            json_payload['chargePointSerialNumber'] = self.spec_chargePointSerialNumber
        resp_json = await self.by_device_req_send(action, json_payload)
        if resp_json is None or resp_json[2]['status'] != 'Accepted':
            await self.handle_error(f"Action {action} Response Failed", ErrorReasons.InvalidResponse)
            return False
        self.logger.info(f"Action {action} End")
        return True

    async def action_status_update(self, status, **options) -> bool:
        return await self.action_status_update_ocpp(status, "NoError", **options)

    async def action_status_update_ocpp(self, status, errorCode, **options) -> bool:
        action = "StatusNotification"
        self.logger.info(f"Action {action} Start")
        json_payload = {
            "connectorId": options.pop("connectorId", 1),
            "errorCode": errorCode,
            "status": status
        }
        if await self.by_device_req_send(action, json_payload) is None:
            return False
        self.logger.info(f"Action {action} End")
        return True

    async def action_authorize(self, **options) -> bool:
        action = "Authorize"
        self.logger.info(f"Action {action} Start")
        id_tag = options.pop("idTag", "-")
        key_name = "idTagInfo"
        json_payload = {
            "idTag": id_tag
        }
        resp_json = await self.by_device_req_send(action, json_payload)

        if resp_json is None or resp_json[2][key_name]['status'] != 'Accepted':
            await self.handle_error(f"Action {action} Response Failed", ErrorReasons.InvalidResponse)
            return False
        self.logger.info(f"Action {action} End")
        return True

    charge_start_time = datetime.datetime.utcnow()
    charge_meter_start = 1000

    async def action_charge_start(self, **options) -> bool:
        action = "StartTransaction"
        self.logger.info(f"Action {action} Start")
        self.charge_start_time = datetime.datetime.utcnow()
        self.charge_meter_start = options.pop("meterStart", self.charge_meter_start)
        key_name = "idTagInfo"
        id_tag = options.pop("idTag", "-")
        conenctor_id = options.pop("connectorId", 1)
        json_payload = {
            "timestamp": self.utcnow_iso(),
            "connectorId": conenctor_id,
            "meterStart": self.charge_meter_start,
            "idTag": id_tag
        }
        resp_json = await self.by_device_req_send(action, json_payload)
        if resp_json is None or resp_json[2][key_name]['status'] != 'Accepted':
            await self.handle_error(f"Action {action} Response Failed", ErrorReasons.InvalidResponse)
            return False
        self.charge_id = resp_json[2]['transactionId']
        self.charge_in_progress = True
        self.logger.info(f"Action {action} End")
        return True

    async def action_meter_value(self, **options) -> bool:
        action = "MeterValues"
        self.logger.info(f"Action {action} Start")
        conenctor_id = options.pop("connectorId", 1)
        json_payload = {
            "connectorId": conenctor_id,
            "transactionId": self.charge_id,
            "meterValue": [{
                "timestamp": self.utcnow_iso(),
                "sampledValue": [{
                    "value": self.charge_meter_value_current(**options),
                    "context": "Sample.Periodic",
                    "measurand": "Energy.Active.Import.Register",
                    "location": "Outlet",
                    "unit": "kWh"
                }]
            }]
        }
        resp_json = await self.by_device_req_send(action, json_payload)
        if resp_json is None:
            return False
        self.logger.info(f"Action {action} End")
        return True

    async def action_charge_stop(self, **options) -> bool:
        action = "StopTransaction"
        self.logger.info(f"Action {action} Start")
        key_name = "idTagInfo"
        id_tag = options.pop("idTag", "-")
        json_payload = {
            "timestamp": self.utcnow_iso(),
            "transactionId": self.charge_id,
            "meterStop": self.charge_meter_value_current(**options),
            "idTag": id_tag,
            "reason": options.pop("stopReason", "Local")
        }        
        resp_json = await self.by_device_req_send(action, json_payload)
        if resp_json is None or resp_json[2][key_name]['status'] != 'Accepted':
            await self.handle_error(f"Action {action} Response Failed", ErrorReasons.InvalidResponse)
            return False
        self.logger.info(f"Action {action} End")
        return True

    async def flow_charge(self, auto_stop: bool, **options) -> bool:
        log_title = self.flow_charge.__name__
        self.logger.info(f"Flow {log_title} Start")
        if not await self.action_authorize(**options):
            self.charge_in_progress = False
            return False
        if not await self.action_charge_start(**options):
            self.charge_in_progress = False
            return False
        if not await self.action_status_update("Preparing", **options):
            self.charge_in_progress = False
            return False
        if not await self.action_status_update("Charging", **options):
            self.charge_in_progress = False
            return False
        if not await self.flow_charge_ongoing_loop(auto_stop, **options):
            self.charge_in_progress = False
            return False
        if not await self.action_status_update("Finishing", **options):
            self.charge_in_progress = False
            return False
        if not await self.action_charge_stop(**options):
            self.charge_in_progress = False
            return False
        if not await self.action_status_update("Available", **options):
            self.charge_in_progress = False
            return False
        self.logger.info(f"Flow {log_title} End")
        self.charge_in_progress = False
        return True

    async def loop_interactive_custom(self):
        is_back = False
        while not is_back:
            input1 = await aioconsole.ainput("""
What should I do? (enter the number + enter)
0: Back
1: HeartBeat
2: StatusUpdate
99: Full custom
""")
            if input1 == "0":
                is_back = True
            elif input1 == "1":
                await self.action_heart_beat()
            elif input1 == "2":
                input1 = await aioconsole.ainput("Which status?\n")
                input2 = await aioconsole.ainput("Which errorCode?\n")
                input3 = await aioconsole.ainput("Which connector?\n")
                await self.action_status_update_ocpp(input1, input2, ** {
                    'connectorId': input3,
                })
            elif input1 == "99":
                input1 = input("Enter full custom message:\n")
                await self.by_device_req_send_raw(input1, "Custom")
        pass