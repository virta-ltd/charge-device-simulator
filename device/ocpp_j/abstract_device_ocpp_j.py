import asyncio
import datetime
import json
import logging
import math
import sys
import typing
import uuid
import urllib.parse

import aioconsole
import websockets

from device import utility
from device.abstract import DeviceAbstract
from device.error_reasons import ErrorReasons
from device.ocpp_j.message_types import MessageTypes
from model.error_message import ErrorMessage

if sys.platform != "win32":
    # Fake call to readline module to make sure it is loaded
    # we need this since on OS-X if the readline module is not loaded, the input
    # from terminal using input() will be limited to small number of characters
    import readline
    readline.get_completion_type()


class AbstractDeviceOcppJ(DeviceAbstract):
    server_address = ""
    __logger = logging.getLogger(__name__)
    _ws: websockets.WebSocketClientProtocol = None
    __loop_internal_task: asyncio.Task = None
    __ws_close_task: asyncio.Task = None
    __pending_by_device_reqs: typing.Dict[str, typing.Callable[[typing.Any], None]] = {}

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
        self.spec_chargePointSerialNumber = None

    @property
    def logger(self) -> logging:
        return self.__logger

    async def initialize(self) -> bool:
        try:
            logging.getLogger('websockets.client').setLevel(logging.WARNING)
            logging.getLogger('websockets.server').setLevel(logging.WARNING)
            logging.getLogger('websockets.protocol').setLevel(logging.WARNING)
            server_url = f"{self.server_address}/{urllib.parse.quote(self.deviceId)}"
            self.logger.info(f"Trying to connect.\nURL: {server_url}\nClient supported protocols: {json.dumps(self.protocols)}")
            self._ws = await websockets.connect(
                server_url,
                subprotocols=[websockets.Subprotocol(p) for p in self.protocols]
            )
            self.logger.info(f"Connected with protocol: {self._ws.subprotocol}")
            self.__loop_internal_task = asyncio.create_task(self.__loop_internal())
            self.__ws_close_task = asyncio.create_task(self.__ws_close())

            await asyncio.sleep(1)

            if self.register_on_initialize:
                await self.action_register()
            await self.action_heart_beat()
            return True
        except ValueError as err:
            await self.handle_error(ErrorMessage(err).get(), ErrorReasons.InvalidResponse)
            return False
        except BaseException as err:
            await self.handle_error(ErrorMessage(err).get(), ErrorReasons.InvalidResponse)
            return False

    async def end(self):
        if self.__loop_internal_task is not None:
            self.__loop_internal_task.cancel()
        if self.__ws_close_task is not None:
            self.__ws_close_task.cancel()
        if self._ws is not None:
            await self._ws.close()
        pass

    async def __ws_close(self):
        await self._ws.wait_closed()
        await self.handle_error({
            "message": "Websocket connection closed",
            "code": getattr(self._ws, 'close_code', ''),
            "reason": getattr(self._ws, 'close_reason', '')
        }, ErrorReasons.ConnectionError)
        pass

    async def action_heart_beat(self) -> bool:
        action = "HeartBeat"
        self.logger.info(f"Action {action} Start")
        if await self.by_device_req_send(action, {}) is None:
            return False
        self.logger.info(f"Action {action} End")
        return True

    async def action_data_transfer(self, **options) -> bool:
        action = "DataTransfer"
        self.logger.info(f"Action {action} Start")
        json_payload = options
        resp_json = await self.by_device_req_send(action, json_payload)
        if resp_json is None:
            return False
        self.logger.info(f"Action {action} End")
        return True

    def charge_meter_value_current(self, **options):
        return math.floor(options["meterStart"] + (
            (self.utcnow() - datetime.datetime.fromisoformat(options["chargeStartTime"])).total_seconds() / 60
            * options.pop("chargedKwhPerMinute", 1)
            * 1000
        ))

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
        if "chargeStartTime" not in options:
            options["chargeStartTime"] = self.utcnow_iso()
        if "meterStart" not in options:
            options["meterStart"] = 1000
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
        if "chargeStopTime" not in options:
            options["chargeStopTime"] = self.utcnow_iso()
        if "meterStop" not in options:
            options["meterStop"] = self.charge_meter_value_current(**options)
        if not await self.action_charge_stop(**options):
            self.charge_in_progress = False
            return False
        if not await self.action_status_update("Available", **options):
            self.charge_in_progress = False
            return False
        self.logger.info(f"Flow {log_title} End")
        self.charge_in_progress = False
        return True

    async def flow_charge_ongoing_actions(self, **options) -> bool:
        return await self.action_meter_value(**options)

    async def by_device_req_send(self, action, json_payload) -> typing.Any:
        req_id = str(uuid.uuid4())
        req = f"""[{MessageTypes.Req.value},"{req_id}","{action}",{json.dumps(json_payload)}]"""
        return await self.by_device_req_send_raw(req, action, req_id)

    async def by_device_req_send_raw(self, raw, action, req_id=None) -> typing.Any:
        result = asyncio.get_running_loop().create_future()
        if req_id is None:
            req_id = str(uuid.uuid4())
        self.__pending_by_device_reqs[req_id] = lambda resp_json: self.__by_device_req_resp_ready(result, action, resp_json)
        await self._ws.send(raw)
        self.logger.debug(f"By Device Req ({action}):\n{raw}")
        try:
            return await asyncio.wait_for(result, timeout=self.response_timeout_seconds)
        except asyncio.TimeoutError:
            return self.by_device_req_resp_timeout()

    def __by_device_req_resp_ready(self, future: asyncio.Future, action, resp_json):
        resp = json.dumps(resp_json)
        self.logger.debug(f"By Device Req ({action}) Resp:\n{resp}")
        future.set_result(resp_json)
        pass

    async def __loop_internal(self):
        try:
            while True:
                read_raw = await self._ws.recv()
                read_as_json = json.loads(read_raw)
                if len(read_as_json) < 1:
                    self.logger.warning(f"Device Read, Invalid, Message:\n{read_raw}")
                    continue

                read_type = int(read_as_json[0])
                if read_type == MessageTypes.Req.value:  # Received a request initiated from middleware
                    if len(read_as_json) < 3:
                        self.logger.warning(f"Device Read, Request, Invalid, Message:\n{read_raw}")
                        continue
                    self.logger.debug(f"Device Read, Request, Message:\n{read_raw}")
                    req_id = str(read_as_json[1])
                    req_action = str(read_as_json[2]).lower()
                    req_payload = read_as_json[3]
                    await self.by_middleware_req(req_id, req_action, req_payload)
                elif read_type == MessageTypes.Resp.value:  # Received a response from middleware for a request we sent to it previously
                    if len(read_as_json) < 2:
                        self.logger.warning(f"Device Read, Response, Invalid, Message:\n{read_raw}")
                        continue
                    read_resp_id = str(read_as_json[1])
                    read_resp_callable = self.__pending_by_device_reqs.pop(read_resp_id, None)
                    if read_resp_callable is None:
                        self.logger.warning(f"Device Read, Response, Not found the request, Id: {read_resp_id}, Message:\n{read_raw}")
                        continue
                    read_resp_callable(read_as_json)
                else:
                    self.logger.debug(f"Device Read, Type Unknown, Message:\n{read_raw}")
        except asyncio.CancelledError:
            return
        pass

    async def by_middleware_req(self, req_id: str, req_action: str, req_payload: typing.Any):
        # We must not block the event loop here for anything beside sending a response
        # since this is the main event loop for the device checking for websocket messages
        # If we need to do something that blocks or takes time, we must create a new task for it
        next_async_task = None
        resp_payload = None
        if req_action in map(lambda x: str(x).lower(), [
            "ClearCache",
            "ChangeAvailability",
            "RemoteStartTransaction",
            "RemoteStopTransaction",
            "SetChargingProfile",
            "ChangeConfiguration",
            "UnlockConnector",
            "UpdateFirmware",
            "SendLocalList",
            "CancelReservation",
            "ReserveNow",
            "Reset",
            "DataTransfer",
            "RequestStartTransaction",
            "RequestStopTransaction"
        ]):
            resp_payload = {
                "status": "Accepted"
            }
        elif req_action == "GetConfiguration".lower():
            resp_payload = {
                "configurationKey": [
                    {"key": "type", "value": "device-simulator", "readonly": "true"},
                    {"key": "server_address", "value": self.server_address, "readonly": "true"},
                    {"key": "identifier", "value": self.deviceId, "readonly": "false"},
                ]
            }
        elif req_action == "GetDiagnostics".lower():
            resp_payload = {
                "fileName": "fake_file_name.log"
            }

        if req_action == "TriggerMessage".lower():
            if req_payload["requestedMessage"] == "MeterValues":
                options = {
                    "connectorId": req_payload["connectorId"] if "connectorId" in req_payload else 0,
                }
                resp_payload = {
                    "status": "Accepted"
                }
                next_async_task = self.action_meter_value(**options)
            if req_payload["requestedMessage"] == "BootNotification":
                resp_payload = {
                    "status": "Accepted"
                }
                next_async_task = self.action_register()
            if req_payload["requestedMessage"] == "Heartbeat":
                resp_payload = {
                    "status": "Accepted"
                }
                next_async_task = await self.action_heart_beat()
            if req_payload["requestedMessage"] == "StatusNotification":
                options = {
                    "connectorId": req_payload["connectorId"] if "connectorId" in req_payload else 0,
                }
                resp_payload = {
                    "status": "Accepted"
                }
                if self.charge_in_progress:
                    next_async_task = await self.action_status_update("Charging", **options)
                else:
                    next_async_task = await self.action_status_update("Available", **options)
        if req_action == "RemoteStartTransaction".lower():
            if not self.charge_can_start():
                resp_payload["status"] = "Rejected"
            else:
                options = {
                    "connectorId": req_payload["connectorId"] if "connectorId" in req_payload else 0,
                    "idTag": req_payload["idTag"] if "idTag" in req_payload else "-",
                }
                self.logger.info(f"Device, Read, Request, RemoteStart, Options: {json.dumps(options)}")
                next_async_task = utility.run_with_delay(self.flow_charge(False, **options), 2)

        if req_action == "RemoteStopTransaction".lower():
            if not self.charge_can_stop(req_payload["transactionId"] if "transactionId" in req_payload else 0):
                resp_payload["status"] = "Rejected"
            else:
                next_async_task = utility.run_with_delay(self.flow_charge_stop(), 2)

        if req_action == "Reset".lower():
            next_async_task = utility.run_with_delay(self.re_initialize(), 2)

        if resp_payload is None:
            self.logger.warning(f"Device Read, Request, Unknown or not supported: {req_action}")
            return
        await self.by_middleware_req_response_ready(req_id, resp_payload)
        if next_async_task is not None:
            asyncio.create_task(next_async_task)

    async def by_middleware_req_response_ready(self, req_id, resp_payload):
        if resp_payload is None:
            return
        resp = f"""[{MessageTypes.Resp.value},"{req_id}",{json.dumps(resp_payload)}]"""
        await self._ws.send(resp)
        self.logger.debug(f"Device Read, Request, Responded:\n{resp}")

    async def flow_charge_stop(self):
        self.charge_in_progress = False
        pass
