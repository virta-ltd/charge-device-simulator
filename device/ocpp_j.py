import asyncio
import datetime
import json
import logging
import math
import sys
import uuid

import aioconsole
from websocket import create_connection

import device.abstract


class DeviceOcppJ(device.abstract.DeviceAbstract):
    server_address = ""
    __logger = logging.getLogger(__name__)
    _ws = None

    def __init__(self, device_id):
        super().__init__(device_id)
        self.flow_frequent_delay_seconds = 30
        self.spec_meterSerialNumber = None
        self.spec_meterType = None
        self.spec_imsi = None
        self.spec_iccid = None
        self.spec_firmwareVersion = None
        self.spec_chargeBoxSerialNumber = None
        self.spec_chargePointModel = None
        self.spec_chargePointVendor = None

    @property
    def logger(self) -> logging:
        return self.__logger

    def initialize(self) -> bool:
        try:
            self._ws = create_connection(f"{self.server_address}/{self.deviceId}", subprotocols=['ocpp1.6'])
            self.logger.info("Connected")
            if self.register_on_initialize:
                self.action_register()
            self.action_heart_beat()
            return True
        except ValueError as err:
            self.handle_error(str(err))
            return False
        except:
            self.handle_error(str(sys.exc_info()[0]))
            return False

    def end(self):
        self._ws.close()
        pass

    def action_register(self) -> bool:
        action = "BootNotification"
        self.logger.info(f"Action {action} Start")
        json_payload = {
            'chargePointVendor': self.spec_chargePointVendor,
            'chargePointModel': self.spec_chargePointModel,
            'chargeBoxSerialNumber': self.spec_chargeBoxSerialNumber,
            'firmwareVersion': self.spec_firmwareVersion,
            'iccid': self.spec_iccid,
            'imsi': self.spec_imsi,
            'meterType': self.spec_meterType,
            'meterSerialNumber': self.spec_meterSerialNumber,
            'chargePointSerialNumber': "Not set",
        }
        resp_json = self.by_device_req_send(action, json_payload)
        if resp_json is None or resp_json[2]['status'] != 'Accepted':
            self.handle_error(f"Action {action} Response Failed")
            return False
        self.logger.info(f"Action {action} End")
        return True

    def action_heart_beat(self) -> bool:
        action = "HeartBeat"
        self.logger.info(f"Action {action} Start")
        if self.by_device_req_send(action, {}) is None:
            return False
        self.logger.info(f"Action {action} End")
        return True

    def action_status_update(self, status, **options) -> bool:
        action = "StatusNotification"
        self.logger.info(f"Action {action} Start")
        json_payload = {
            "connectorId": options.pop("connectorId", 1),
            "errorCode": "NoError",
            "status": status
        }
        if self.by_device_req_send(action, json_payload) is None:
            return False
        self.logger.info(f"Action {action} End")
        return True

    def action_authorize(self, **options) -> bool:
        action = "Authorize"
        self.logger.info(f"Action {action} Start")
        json_payload = {
            "idTag": options.pop("idTag", "-")
        }
        resp_json = self.by_device_req_send(action, json_payload)
        if resp_json is None or resp_json[2]['idTagInfo']['status'] != 'Accepted':
            self.handle_error(f"Action {action} Response Failed")
            return False
        self.logger.info(f"Action {action} End")
        return True

    charge_start_time = datetime.datetime.utcnow()
    charge_meter_start = 1000
    charge_transaction_id = -1

    def action_charge_start(self, **options) -> bool:
        action = "StartTransaction"
        self.logger.info(f"Action {action} Start")
        self.charge_start_time = datetime.datetime.utcnow()
        self.charge_meter_start = options.pop("meterStart", self.charge_meter_start)
        json_payload = {
            "timestamp": self.utcnow_iso(),
            "connectorId": options.pop("connectorId", 1),
            "meterStart": self.charge_meter_start,
            "idTag": options.pop("idTag", "-")
        }
        resp_json = self.by_device_req_send(action, json_payload)
        if resp_json is None or resp_json[2]['idTagInfo']['status'] != 'Accepted':
            self.handle_error(f"Action {action} Response Failed")
            return False
        self.charge_transaction_id = resp_json[2]['transactionId']
        self.logger.info(f"Action {action} End")
        return True

    def charge_meter_value_current(self, **options):
        return math.floor(self.charge_meter_start + (
            (datetime.datetime.utcnow() - self.charge_start_time).total_seconds() / 60
            * options.pop("chargedKwhPerMinute", 1)
            * 1000
        ))

    def action_meter_value(self, **options) -> bool:
        action = "MeterValues"
        self.logger.info(f"Action {action} Start")
        json_payload = {
            "connectorId": options.pop("connectorId", 1),
            "transactionId": self.charge_transaction_id,
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
        if self.by_device_req_send(action, json_payload) is None:
            return False
        self.logger.info(f"Action {action} End")
        return True

    def action_charge_stop(self, **options) -> bool:
        action = "StopTransaction"
        self.logger.info(f"Action {action} Start")
        json_payload = {
            "timestamp": self.utcnow_iso(),
            "transactionId": self.charge_transaction_id,
            "meterStop": self.charge_meter_value_current(**options),
            "idTag": options.pop("idTag", "-"),
            "reason": options.pop("stopReason", "Local")
        }
        resp_json = self.by_device_req_send(action, json_payload)
        if resp_json is None or resp_json[2]['idTagInfo']['status'] != 'Accepted':
            self.handle_error(f"Action {action} Response Failed")
            return False
        self.logger.info(f"Action {action} End")
        return True

    async def flow_heartbeat(self) -> bool:
        log_title = self.flow_heartbeat.__name__
        self.logger.info(f"Flow {log_title} Start")
        if not self.action_heart_beat():
            return False
        self.logger.info(f"Flow {log_title} End")
        return True

    async def flow_authorize(self, **options) -> bool:
        log_title = self.flow_authorize.__name__
        self.logger.info(f"Flow {log_title} Start")
        if not self.action_authorize(**options):
            return False
        self.logger.info(f"Flow {log_title} End")
        return True

    async def flow_charge(self, **options) -> bool:
        log_title = self.flow_charge.__name__
        self.logger.info(f"Flow {log_title} Start")
        if not self.action_authorize(**options):
            return False
        if not self.action_charge_start(**options):
            return False
        if not self.action_status_update("Preparing", **options):
            return False
        if not self.action_status_update("Charging", **options):
            return False
        for i in range(6):
            await asyncio.sleep(15)
            if not self.action_meter_value(**options):
                return False
        await asyncio.sleep(5)
        if not self.action_status_update("Finishing", **options):
            return False
        if not self.action_charge_stop(**options):
            return False
        if not self.action_status_update("Available", **options):
            return False
        self.logger.info(f"Flow {log_title} End")
        return True

    def by_device_req_send(self, action, json_payload):
        req_id = uuid.uuid4()
        req = f"""[2,"{req_id}","{action}",{json.dumps(json_payload)}]"""
        self._ws.send(req)
        self.logger.debug(f"By Device Req ({action}):\n{req}")
        resp = self._ws.recv()
        self.logger.debug(f"By Device Req ({action}) Resp:\n{resp}")
        resp_json = json.loads(resp)
        if resp_json[1] != f"{req_id}":
            self.handle_error(f"Action `{action}` Req and Resp Id does not match")
            return None
        return resp_json

    async def loop_interactive_custom(self):
        is_back = False
        while not is_back:
            input1 = await aioconsole.ainput("""
What should I do? (enter the number + enter)
0: Back
1: HeartBeat
2: StatusUpdate
""")
            if input1 == "0":
                is_back = True
            elif input1 == "1":
                self.action_heart_beat()
            elif input1 == "2":
                input1 = await aioconsole.ainput("Which status?\n")
                self.action_status_update(input1)
        pass
