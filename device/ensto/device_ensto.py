import asyncio
import datetime
import json
import logging
import math
import sys
import typing
from urllib import parse

import aioconsole
import device.abstract
from device import utility
from device.ensto.pending_req import PendingReq


# noinspection DuplicatedCode
class DeviceEnsto(device.abstract.DeviceAbstract):
    server_host = ""
    server_port = 3000
    __logger = logging.getLogger(__name__)
    __loop_internal_task: asyncio.Task = None
    __socketWriter: asyncio.StreamWriter = None
    __socketReader: asyncio.StreamReader = None
    __pending_by_device_reqs: typing.Dict[str, PendingReq] = {}

    def __init__(self, device_id):
        super().__init__(device_id)
        self.flow_frequent_delay_seconds = 30
        self.spec_sw = None
        self.spec_model = None
        self.spec_vendor = None

    @property
    def logger(self) -> logging:
        return self.__logger

    # noinspection PyBroadException
    async def initialize(self) -> bool:
        try:
            self.__socketReader, self.__socketWriter = await asyncio.open_connection(self.server_host, self.server_port)
            self.__loop_internal_task = asyncio.create_task(self.__loop_internal())

            await asyncio.sleep(1)
            self.logger.info("Connected")

            if self.register_on_initialize:
                await self.action_register()
            await self.action_heart_beat()
            return True
        except ValueError as err:
            await self.handle_error(str(err))
            return False
        except:
            await self.handle_error(str(sys.exc_info()[0]))
            return False

    async def end(self):
        if self.__loop_internal_task is not None:
            self.__loop_internal_task.cancel()
        if self.__socketWriter is not None:
            self.__socketWriter.close()
            await self.__socketWriter.wait_closed()
        pass

    async def action_register(self) -> bool:
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
        resp_json = await self.by_device_req_send(action, json_payload)
        if resp_json is None or 'chk' not in resp_json or 'uv' not in resp_json:
            await self.handle_error(f"Action {action} Response Failed")
            return False
        self.logger.info(f"Action {action} End")
        return True

    async def action_heart_beat(self) -> bool:
        action = "heart_beat"
        self.logger.info(f"Action {action} Start")
        json_payload = {
            'id': 24,
            'time': 1,
        }
        resp_json = await self.by_device_req_send(action, json_payload)
        if resp_json is None or 'chk' not in resp_json or 'time' not in resp_json:
            await self.handle_error(f"Action {action} Response Failed:\n{json.dumps(resp_json)}")
            return False
        self.logger.info(f"Action {action} End")
        return True

    async def action_status_update(self, status, **options) -> bool:
        action = "status_update"
        self.logger.info(f"Action {action} Start")
        json_payload = {
            'id': 2,
            'ping': None,
            "status": status
        }
        resp_json = await self.by_device_req_send(action, json_payload)
        if resp_json is None or 'chk' not in resp_json or 'ack' not in resp_json:
            await self.handle_error(f"Action {action} Response Failed:\n{json.dumps(resp_json)}")
            return False
        self.logger.info(f"Action {action} End")
        return True

    async def action_authorize(self, **options) -> bool:
        action = "authorize"
        self.logger.info(f"Action {action} Start")
        json_payload = {
            'id': 10,
            "rfid": options.pop("idTag", "-")
        }
        resp_json = await self.by_device_req_send(action, json_payload)
        if resp_json is None or 'chk' not in resp_json or 'success' not in resp_json:
            await self.handle_error(f"Action {action} Response Failed:\n{json.dumps(resp_json)}")
            return False
        self.logger.info(f"Action {action} End")
        return True

    charge_start_time = datetime.datetime.utcnow()
    charge_meter_start = 1000

    async def action_charge_start(self, **options) -> bool:
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
        resp_json = await self.by_device_req_send(action, json_payload)
        if resp_json is None or 'chk' not in resp_json or 'ack' not in resp_json:
            await self.handle_error(f"Action {action} Response Failed:\n{json.dumps(resp_json)}")
            return False
        self.charge_in_progress = True
        self.logger.info(f"Action {action} End")
        return True

    def charge_meter_value_current(self, **options):
        return math.floor(self.charge_meter_start + (
                (datetime.datetime.utcnow() - self.charge_start_time).total_seconds() / 60
                * options.pop("chargedKwhPerMinute", 1)
                * 1000
        ))

    async def action_meter_value(self, **options) -> bool:
        action = "meter_value"
        self.logger.info(f"Action {action} Start")
        json_payload = {
            'id': 43,
            "out": options.pop("connectorId", 1),
            "time": datetime.datetime.utcnow().timestamp(),
            "t": 382,
            "eem": self.charge_meter_value_current(**options) - self.charge_meter_start,
        }
        resp_json = await self.by_device_req_send(action, json_payload)
        if resp_json is None or 'chk' not in resp_json or 'ack' not in resp_json:
            await self.handle_error(f"Action {action} (Response Failed:\n{json.dumps(resp_json)}") / 1000
            return False
        self.logger.info(f"Action {action} End")
        return True

    async def action_charge_stop(self, **options) -> bool:
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
        resp_json = await self.by_device_req_send(action, json_payload)
        if resp_json is None or 'chk' not in resp_json or 'ack' not in resp_json:
            await self.handle_error(f"Action {action} (Response Failed:\n{json.dumps(resp_json)}") / 1000
            return False
        self.logger.info(f"Action {action} End")
        return True

    async def flow_heartbeat(self) -> bool:
        log_title = self.flow_heartbeat.__name__
        self.logger.info(f"Flow {log_title} Start")
        if not await self.action_heart_beat():
            return False
        self.logger.info(f"Flow {log_title} End")
        return True

    async def flow_authorize(self, **options) -> bool:
        log_title = self.flow_authorize.__name__
        self.logger.info(f"Flow {log_title} Start")
        if not await self.action_authorize(**options):
            return False
        self.logger.info(f"Flow {log_title} End")
        return True

    async def flow_charge(self, auto_stop: bool, **options) -> bool:
        log_title = self.flow_charge.__name__
        self.logger.info(f"Flow {log_title} Start")
        if not await self.action_authorize(**options):
            self.charge_in_progress = False
            return False
        if not await self.action_status_update("1", **options):
            self.charge_in_progress = False
            return False
        if not await self.action_charge_start(**options):
            self.charge_in_progress = False
            return False
        if not await self.action_status_update("1", **options):
            self.charge_in_progress = False
            return False
        if not await self.flow_charge_ongoing_loop(auto_stop, **options):
            self.charge_in_progress = False
            return False
        if not await self.action_status_update("0", **options):
            self.charge_in_progress = False
            return False
        if not await self.action_charge_stop(**options):
            self.charge_in_progress = False
            return False
        self.logger.info(f"Flow {log_title} End")
        self.charge_in_progress = False
        return True

    async def flow_charge_ongoing_actions(self, **options) -> bool:
        return await self.action_meter_value(**options) and await self.action_status_update("1", **options)

    async def by_device_req_send(self, action, json_payload, valid_ids: typing.Sequence = None):
        result = asyncio.get_running_loop().create_future()
        req_id = str(json_payload['id'])
        req = self.__socket_message(json_payload)
        self.__pending_by_device_reqs[req_id] = PendingReq(valid_ids, lambda resp_json: self.__by_device_req_resp_ready(result, action, resp_json))
        self.__socketWriter.write(req.encode())
        await self.__socketWriter.drain()
        self.logger.debug(f"By Device Req ({action}):\n{req}")
        return await result

    def __socket_message(self, payload_dict) -> str:
        req = f"""imei={self.deviceId}"""
        for key, value in payload_dict.items():
            req += f"&{parse.quote_plus(key)}"
            if value is not None:
                value_s = f"{value}"
                req += f"={parse.quote_plus(value_s)}"
        return req

    def __by_device_req_resp_ready(self, future: asyncio.Future, action, resp_json):
        resp = json.dumps(resp_json)
        self.logger.debug(f"By Device Req ({action}) Resp:\n{resp}")
        future.set_result(resp_json)
        pass

    async def __loop_internal(self):
        try:
            while True:
                read_raw = (await self.__socketReader.readline()).decode()
                read_as_json = {}
                for term in read_raw.split('&'):
                    term_break = term.split('=')
                    read_as_json[term_break[0]] = term_break[1] if len(term_break) > 1 else None
                read_id = str(read_as_json['id'])

                # Find possible pending req by its id (dict)
                pending_req = self.__pending_by_device_reqs.pop(read_id, None)
                # If not found, try finding in valid_ids
                if pending_req is None:
                    key = next(
                        (item_key for item_key, item_value in self.__pending_by_device_reqs.items() if read_id in item_value.valid_ids),
                        None
                    )
                    pending_req = self.__pending_by_device_reqs.pop(key, None)

                if pending_req is not None:  # Received a response from middleware for a request we sent to it previously
                    pending_req.resp_callable(read_as_json)
                elif not await self.by_middleware_req(read_id, read_as_json):
                    self.logger.warning(f"Device Read, Unhandled, Message:\n{read_raw}")
        except asyncio.CancelledError:
            return
        pass

    async def by_middleware_req(self, req_action: str, req_payload: typing.Any) -> bool:
        self.logger.debug(f"Device Read, Request, Message:\n{req_payload}")
        resp_payload = None
        if req_action in map(lambda x: str(x).lower(), [
            "20",  # OutOfOrder
            "11",  # ChargingRequestByServer
            "17",  # HatchOpen
            "42",  # Restart
        ]):
            resp_payload = {
                "ack": "1"
            }

        if req_action == "11".lower():
            req_scmd = str(req_payload["scmd"] if "scmd" in req_payload else -1)
            if req_scmd == "1":
                if not self.charge_can_start():
                    del resp_payload["ack"]
                    resp_payload["nack"] = "1"
                else:
                    options = {
                        "idTag": req_payload["idtag"] if "idtag" in req_payload else "-",
                    }
                    self.logger.info(f"Device, Read, Request, RemoteStart, Options: {json.dumps(options)}")
                    asyncio.create_task(utility.run_with_delay(self.flow_charge(False, **options), 2))
            elif req_scmd == "0":
                if not self.charge_can_stop(-1):
                    del resp_payload["ack"]
                    resp_payload["nack"] = "1"
                else:
                    asyncio.create_task(utility.run_with_delay(self.flow_charge_stop(), 2))
            else:
                del resp_payload["ack"]
                resp_payload["nack"] = "1"

        # "14", SettingsGprs
        # "15", SettingsByServer
        if req_action == "14".lower() or req_action == "15".lower():
            if ("gprs" in req_payload and str(req_payload["gprs"]) == "2") or ("settings" in req_payload and str(req_payload["settings"]) == "2"):  # Try to change config
                if "upd" in req_payload and str(req_payload["upd"]) == "1":
                    resp_payload = {
                        "upd": "1"
                    }
                else:
                    resp_payload = {
                        "ack": "1"
                    }
            else:  # Try to get config
                resp_payload = {
                    "type": "device-simulator",
                    "server_host": self.server_host,
                    "server_port": self.server_port,
                    "identifier": self.deviceId,
                }

        # Restart
        if req_action == "42".lower():
            asyncio.create_task(utility.run_with_delay(self.re_initialize(), 2))

        if resp_payload is not None:
            resp_payload["id"] = req_action
            resp = self.__socket_message(resp_payload)
            self.__socketWriter.write(resp.encode())
            await self.__socketWriter.drain()
            self.logger.debug(f"Device Read, Request, Responded:\n{resp}")
            return True
        else:
            self.logger.warning(f"Device Read, Request, Unknown or not supported: {req_action}")
            return False

    async def flow_charge_stop(self):
        self.charge_in_progress = False
        pass

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
                await self.action_heart_beat()
            elif input1 == "2":
                input1 = await aioconsole.ainput("Which status?\n")
                await self.action_status_update(input1)
        pass
