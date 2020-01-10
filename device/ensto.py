import asyncio
import datetime
import json
import logging
import math
import socket
import sys
from urllib import parse

import aioconsole

import device.abstract


# noinspection DuplicatedCode
class DeviceEnsto(device.abstract.DeviceAbstract):
    server_host = ""
    server_port = 3000
    __logger = logging.getLogger(__name__)
    _socket = None

    def __init__(self, device_id):
        super().__init__(device_id)
        self.flow_frequent_delay_seconds = 30
        self.spec_sw = None
        self.spec_model = None
        self.spec_vendor = None

    @property
    def logger(self) -> logging:
        return self.__logger

    def initialize(self) -> bool:
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.connect((self.server_host, self.server_port))
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
        self._socket.close()
        pass

    def action_register(self) -> bool:
        action = "register"
        self.logger.info(f"Action {action} Start")
        json_payload = {
            'id': 1,
            'settings': None,
            'vendor': self.spec_vendor,
            'model': self.spec_model,
            'sw': self.spec_sw,
            'isLoadTest': 1
        }
        resp_json = self.by_device_req_send(action, json_payload)
        if resp_json is None or 'chk' not in resp_json or 'uv' not in resp_json:
            self.handle_error(f"Action {action} Response Failed")
            return False
        self.logger.info(f"Action {action} End")
        return True

    def action_heart_beat(self) -> bool:
        action = "heart_beat"
        self.logger.info(f"Action {action} Start")
        json_payload = {
            'id': 24,
            'time': 1,
        }
        resp_json = self.by_device_req_send(action, json_payload)
        if resp_json is None or 'chk' not in resp_json or 'time' not in resp_json:
            self.handle_error(f"Action {action} Response Failed:\n{json.dumps(resp_json)}")
            return False
        self.logger.info(f"Action {action} End")
        return True

    def action_status_update(self, status, **options) -> bool:
        action = "status_update"
        self.logger.info(f"Action {action} Start")
        json_payload = {
            'id': 2,
            'ping': None,
            "status": status
        }
        resp_json = self.by_device_req_send(action, json_payload)
        if resp_json is None or 'chk' not in resp_json or 'ack' not in resp_json:
            self.handle_error(f"Action {action} Response Failed:\n{json.dumps(resp_json)}")
            return False
        self.logger.info(f"Action {action} End")
        return True

    def action_authorize(self, **options) -> bool:
        action = "authorize"
        self.logger.info(f"Action {action} Start")
        json_payload = {
            'id': 10,
            "rfid": options.pop("idTag", "-")
        }
        resp_json = self.by_device_req_send(action, json_payload)
        if resp_json is None or 'chk' not in resp_json or 'success' not in resp_json:
            self.handle_error(f"Action {action} Response Failed:\n{json.dumps(resp_json)}")
            return False
        self.logger.info(f"Action {action} End")
        return True

    charge_start_time = datetime.datetime.utcnow()
    charge_meter_start = 1000

    def action_charge_start(self, **options) -> bool:
        action = "charge_start"
        self.logger.info(f"Action {action} Start")
        self.charge_start_time = datetime.datetime.utcnow()
        self.charge_meter_start = options.pop("meterStart", self.charge_meter_start)
        json_payload = {
            'id': 5,
            "rfid": options.pop("idTag", "-"),
            "chg": 2,
            "out": options.pop("connectorId", 1),
        }
        resp_json = self.by_device_req_send(action, json_payload)
        if resp_json is None or 'chk' not in resp_json or 'ack' not in resp_json:
            self.handle_error(f"Action {action} Response Failed:\n{json.dumps(resp_json)}")
            return False
        self.logger.info(f"Action {action} End")
        return True

    def charge_meter_value_current(self, **options):
        return math.floor(self.charge_meter_start + (
            (datetime.datetime.utcnow() - self.charge_start_time).total_seconds() / 60
            * options.pop("chargedKwhPerMinute", 1)
            * 1000
        ))

    def action_meter_value(self, **options) -> bool:
        action = "meter_value"
        self.logger.info(f"Action {action} Start")
        json_payload = {
            'id': 43,
            "out": options.pop("connectorId", 1),
            "time": datetime.datetime.utcnow().timestamp(),
            "t": 382,
            "eem": self.charge_meter_value_current(**options) - self.charge_meter_start,
        }
        resp_json = self.by_device_req_send(action, json_payload)
        if resp_json is None or 'chk' not in resp_json or 'ack' not in resp_json:
            self.handle_error(f"Action {action} (Response Failed:\n{json.dumps(resp_json)}") / 1000
            return False
        self.logger.info(f"Action {action} End")
        return True

    def action_charge_stop(self, **options) -> bool:
        action = "charge_stop"
        self.logger.info(f"Action {action} Start")
        json_payload = {
            'id': 6,
            "rfid": options.pop("idTag", "-"),
            "chg": 0,
            "out": options.pop("connectorId", 1),
            "kwh": (self.charge_meter_value_current(**options) - self.charge_meter_start) / 1000,
            "timestamp": self.utcnow_iso(),
        }
        resp_json = self.by_device_req_send(action, json_payload)
        if resp_json is None or 'chk' not in resp_json or 'ack' not in resp_json:
            self.handle_error(f"Action {action} (Response Failed:\n{json.dumps(resp_json)}") / 1000
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
        if not self.action_status_update("1", **options):
            return False
        if not self.action_charge_start(**options):
            return False
        if not self.action_status_update("1", **options):
            return False
        for i in range(6):
            await asyncio.sleep(15)
            if not self.action_meter_value(**options):
                return False
            if not self.action_status_update("1", **options):
                return False
        await asyncio.sleep(5)
        if not self.action_status_update("0", **options):
            return False
        if not self.action_charge_stop(**options):
            return False
        self.logger.info(f"Flow {log_title} End")
        return True

    def by_device_req_send(self, action, json_payload, valid_ids=None):
        req = f"""imei={self.deviceId}"""
        for key, value in json_payload.items():
            req += f"&{parse.quote_plus(key)}"
            if value is not None:
                value_s = f"{value}"
                req += f"={parse.quote_plus(value_s)}"
        self._socket.send(req.encode())
        self.logger.debug(f"By Device Req ({action}):\n{req}")
        resp = self._socket.recv(1024).decode()
        self.logger.debug(f"By Device Req ({action}) Resp:\n{resp}")
        resp_json = {}
        for term in resp.split('&'):
            term_break = term.split('=')
            resp_json[term_break[0]] = term_break[1] if len(term_break) > 1 else None
        resp_id = f"{resp_json['id']}"
        if resp_id != f"{json_payload['id']}" and (valid_ids is None or resp_id not in valid_ids):
            self.handle_error(f"Action `{action}` Req and Resp id does not match, Resp:\n{json.dumps(resp_json)}")
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
