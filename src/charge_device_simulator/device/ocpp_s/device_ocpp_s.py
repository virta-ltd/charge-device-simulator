import asyncio
import datetime
import json
import logging
import math
import os
import typing
import uuid

from .. import utility
from ..abstract import DeviceAbstract
from ..error_reasons import ErrorReasons
from ..ocpp_enums import OCPP_16_CONNECTOR_STATUSES, OCPP_16_ERROR_CODES
from ..ocpp_j.message_types import MessageTypes
from .wsa_extension_plugin import WsAddressingExtensionPlugin
from ...model.error_message import ErrorMessage
from zeep import xsd
from zeep.client import AsyncClient, Client
from zeep.proxy import ServiceProxy
from zeep.settings import Settings


class DeviceOcppS(DeviceAbstract):
    server_address = ""
    from_address = "http://localhost/ChargePointService"
    __logger = logging.getLogger(__name__)
    _client: AsyncClient = None
    _client_service: ServiceProxy = None
    __server_url = ""

    def __init__(self, device_id):
        super().__init__(device_id)
        self.flow_frequent_delay_seconds = 30
        self.protocols = ['ocpp1.5']
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
    def logger(self) -> logging.Logger:
        return self.__logger

    async def initialize(self) -> bool:
        try:
            logging.getLogger('urllib3.connectionpool').setLevel(logging.WARNING)
            logging.getLogger('zeep.wsdl.wsdl').setLevel(logging.WARNING)
            logging.getLogger('zeep.xsd.schema').setLevel(logging.WARNING)
            logging.getLogger('zeep.transports').setLevel(logging.WARNING)
            self.__server_url = f"{self.server_address}"
            self.logger.info(
                f"Trying to connect.\nURL: {self.__server_url}\nClient supported protocols: {json.dumps(self.protocols)}"
            )
            wsdl_file_path = f"{os.path.dirname(os.path.realpath(__file__))}/wsdl/server-201206.wsdl"
            self._client = Client(
                wsdl=wsdl_file_path,
                settings=Settings(
                    raw_response=False,
                ),
                plugins=[WsAddressingExtensionPlugin(self.from_address)]
            )

            self._client_service = self._client.create_service(
                '{urn://Ocpp/Cs/2012/06/}CentralSystemServiceSoap',
                self.__server_url
            )

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
        pass

    async def start_soap_server(self):
        # TODO: need to be implemented
        # if resp_payload is not None:
        #     resp = f"""[{MessageTypes.Resp.value},"{req_id}",{json.dumps(resp_payload)}]"""
        #     await self._ws.send(resp)
        #     self.logger.debug(f"Device Read, Request, Responded:\n{resp}")
        # else:
        #     self.logger.warning(f"Device Read, Request, Unknown or not supported: {req_action}")
        pass

    async def action_register(self) -> bool:
        action = "BootNotification"
        self.logger.info(f"Action {action} Start")
        req_payload = {}
        if self.spec_chargePointVendor is not None:
            req_payload['chargePointVendor'] = self.spec_chargePointVendor
        if self.spec_chargePointModel is not None:
            req_payload['chargePointModel'] = self.spec_chargePointModel
        if self.spec_chargeBoxSerialNumber is not None:
            req_payload['chargeBoxSerialNumber'] = self.spec_chargeBoxSerialNumber
        if self.spec_firmwareVersion is not None:
            req_payload['firmwareVersion'] = self.spec_firmwareVersion
        if self.spec_iccid is not None:
            req_payload['iccid'] = self.spec_iccid
        if self.spec_imsi is not None:
            req_payload['imsi'] = self.spec_imsi
        if self.spec_meterType is not None:
            req_payload['meterType'] = self.spec_meterType
        if self.spec_meterSerialNumber is not None:
            req_payload['meterSerialNumber'] = self.spec_meterSerialNumber
        if self.spec_chargePointSerialNumber is not None:
            req_payload['chargePointSerialNumber'] = self.spec_chargePointSerialNumber
        resp_payload = await self.by_device_req_send(action, req_payload)
        if resp_payload is None or resp_payload['status'] != 'Accepted':
            await self.handle_error(
                f"Action {action} Response Failed:\n{resp_payload!r}",
                ErrorReasons.InvalidResponse)
            return False
        self.logger.info(f"Action {action} End")
        return True

    async def action_heart_beat(self) -> bool:
        action = "Heartbeat"
        self.logger.info(f"Action {action} Start")
        if await self.by_device_req_send(action, {}) is None:
            return False
        self.logger.info(f"Action {action} End")
        return True

    async def action_status_update(self, status, options: dict) -> bool:
        return await self.action_status_update_ocpp(status, "NoError", options)

    async def action_status_update_ocpp(self, status, errorCode, options: dict) -> bool:
        action = "StatusNotification"
        self.logger.info(f"Action {action} Start")
        req_payload = {
            "connectorId": options.get("connectorId", 1),
            "errorCode": errorCode,
            "status": status
        }
        try:
            await self.by_device_req_send(action, req_payload)
        except:
            return False
        self.logger.info(f"Action {action} End")
        return True

    async def action_authorize(self, options: dict) -> bool:
        action = "Authorize"
        self.logger.info(f"Action {action} Start")
        id_tag = options.get("idTag", "-")
        req_payload = {
            "idTag": id_tag
        }
        resp_payload = await self.by_device_req_send(action, req_payload)
        if resp_payload is None or resp_payload['status'] != 'Accepted':
            await self.handle_error(
                f"Action {action} Response Failed:\n{resp_payload!r}",
                ErrorReasons.InvalidResponse)
            return False
        # Per the OCPP 1.5/1.6 SOAP schema, parentIdTag lives inside idTagInfo.
        # Fall back to the top level for tolerance with non-standard responses.
        def _lookup(obj: typing.Any, key: str) -> typing.Any:
            if obj is None:
                return None
            if hasattr(obj, "get"):
                try:
                    return obj.get(key)
                except Exception:
                    return None
            return getattr(obj, key, None)

        info: typing.Any = _lookup(resp_payload, "idTagInfo") or resp_payload
        parent_id_tag: typing.Optional[str] = _lookup(info, "parentIdTag")
        self._last_authorize_info = {
            "id_tag": id_tag,
            "parent_id_tag": parent_id_tag,
        }
        self.logger.info(f"Action {action} End")
        return True

    async def action_data_transfer(self, options: dict) -> bool:
        action = "DataTransfer"
        self.logger.info(f"Action {action} Start")
        req_payload = options
        resp_payload = await self.by_device_req_send(action, req_payload)
        if resp_payload is None:
            return False
        self.logger.info(f"Action {action} End")
        return True

    def fill_missing_options_charge_start(self, options):
        if "chargeStartTime" not in options:
            options["chargeStartTime"] = self.utcnow_iso()
        if "meterStart" not in options:
            options["meterStart"] = 1000

    def fill_missing_options_charge_stop(self, options):
        if "chargeStopTime" not in options:
            options["chargeStopTime"] = self.utcnow_iso()
        if "meterStop" not in options:
            scripted_stop = self._scripted_stop_meter_value(options)
            options["meterStop"] = (scripted_stop if scripted_stop is not None
                                    else self.charge_meter_value_current(options))

    async def action_charge_start(self, options: dict) -> bool:
        action = "StartTransaction"
        self.logger.info(f"Action {action} Start")
        self.fill_missing_options_charge_start(options)
        req_payload = {
            "timestamp": options["chargeStartTime"],
            "connectorId": options.get("connectorId", 1),
            "meterStart": options["meterStart"],
            "idTag": options.get("idTag", "-")
        }
        if "reservationId" in options:
            req_payload["reservationId"] = options["reservationId"]
        resp_payload = await self.by_device_req_send(action, req_payload)
        if resp_payload is None or resp_payload['idTagInfo']['status'] != 'Accepted':
            await self.handle_error(
                f"Action {action} Response Failed:\n{resp_payload!r}",
                ErrorReasons.InvalidResponse)
            return False
        self.charge_id = resp_payload['transactionId']
        self.charge_in_progress = True
        self.logger.info(f"Action {action} End")
        return True

    def charge_meter_value_current(self, options: dict):
        self.fill_missing_options_charge_start(options)
        return math.floor(options["meterStart"] + (
            (self.utcnow() - datetime.datetime.fromisoformat(options["chargeStartTime"])).total_seconds() / 60
            * options.get("chargedKwhPerMinute", 1)
            * 1000
        ))

    async def action_meter_value(self, options: dict, meter_value: int = None, time_stamp: str = None) -> bool:
        action = "MeterValues"
        self.logger.info(f"Action {action} Start")
        req_payload = {
            "connectorId": options.get("connectorId", 1),
            "transactionId": self.charge_id,
            "values": [{
                "timestamp": time_stamp if time_stamp else self.utcnow_iso(),
                "value": [meter_value if meter_value is not None else self.charge_meter_value_current(options), {
                    "context": "Sample.Periodic",
                    "measurand": "Energy.Active.Import.Register",
                    "location": "Outlet",
                    "unit": "kWh"
                }]
            }]
        }

        try:
            await self.by_device_req_send(action, req_payload)
        except BaseException as err:
            await self.handle_error(ErrorMessage(err).get(), ErrorReasons.InvalidResponse)
            return False
        self.logger.info(f"Action {action} End")
        return True

    async def action_charge_stop(self, options: dict) -> bool:
        action = "StopTransaction"
        self.logger.info(f"Action {action} Start")
        req_payload = {
            "timestamp": self.utcnow_iso(),
            "transactionId": self.charge_id,
            "meterStop": self.charge_meter_value_current(options),
            "idTag": options.get("idTag", "-"),
        }
        resp_payload = await self.by_device_req_send(action, req_payload)
        if resp_payload is None or resp_payload['status'] != 'Accepted':
            await self.handle_error(
                f"Action {action} Response Failed:\n{resp_payload!r}",
                ErrorReasons.InvalidResponse)
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

    async def flow_authorize(self, options: dict) -> bool:
        log_title = self.flow_authorize.__name__
        self.logger.info(f"Flow {log_title} Start")
        if not await self.action_authorize(options):
            return False
        self.logger.info(f"Flow {log_title} End")
        return True

    async def flow_charge(self, auto_stop: bool, options: dict) -> bool:
        log_title = self.flow_charge.__name__
        self.logger.info(f"Flow {log_title} Start")
        self._reset_charge_cycle_options(options)
        if not await self.action_authorize(options):
            self.charge_in_progress = False
            return False
        if not self._pre_charge_reservation_gate(options):
            self.charge_in_progress = False
            return False
        if not await self.action_charge_start(options):
            self.charge_in_progress = False
            return False
        self._consume_reservation_if_used(options)
        if not await self.action_status_update("Preparing", options):
            self.charge_in_progress = False
            return False
        if not await self.action_status_update("Charging", options):
            self.charge_in_progress = False
            return False
        if not await self.flow_charge_ongoing_loop(auto_stop, options):
            self.charge_in_progress = False
            return False
        if not await self.action_status_update("Finishing", options):
            self.charge_in_progress = False
            return False
        if not await self.action_charge_stop(options):
            self.charge_in_progress = False
            return False
        if not await self.action_status_update("Available", options):
            self.charge_in_progress = False
            return False
        self.logger.info(f"Flow {log_title} End")
        self.charge_in_progress = False
        return True

    async def flow_charge_ongoing_actions(self, options: dict) -> bool:
        if options.get("autoActionsLoopDisableMeterValues", False):
            return True
        return await self.action_meter_value(options)

    async def by_device_req_send(self, action, req_payload) -> typing.Any:
        req_id = str(uuid.uuid4())
        req = req_payload
        return await self.by_device_req_send_raw(req, action, req_id)

    async def by_device_req_send_raw(self, raw, action, req_id=None) -> typing.Any:
        if req_id is None:
            req_id = str(uuid.uuid4())
        self.logger.debug(f"By Device Req ({action}):\n{raw}")
        try:
            result = self._client_service[action](**raw, _soapheaders={
                'ChargeBoxIdentity': self.deviceId,
            })
            self.logger.debug(f"By Device Resp ({action}):\n{result}")
            return result
        except asyncio.TimeoutError:
            return self.by_device_req_resp_timeout()

    async def by_middleware_req(self, req_id: str, req_action: str, req_payload: typing.Any):
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
            "Reset",
            "DataTransfer",
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

        if req_action == "RemoteStartTransaction".lower():
            if not self.charge_can_start():
                resp_payload["status"] = "Rejected"
            else:
                options = {
                    "connectorId": req_payload["connectorId"] if "connectorId" in req_payload else 0,
                    "idTag": req_payload["idTag"] if "idTag" in req_payload else "-",
                }
                self.logger.info(f"Device, Read, Request, RemoteStart, Options: {json.dumps(options)}")
                asyncio.create_task(utility.run_with_delay(self.flow_charge(False, options), 2))

        if req_action == "RemoteStopTransaction".lower():
            if not self.charge_can_stop(req_payload["transactionId"] if "transactionId" in req_payload else 0):
                resp_payload["status"] = "Rejected"
            else:
                asyncio.create_task(utility.run_with_delay(self.flow_charge_stop(), 2))

        if req_action == "ReserveNow".lower():
            reserve_options: typing.Dict[str, typing.Any] = self._reserve_now_options_from_payload(req_payload)
            if reserve_options.get("connectorId") is None:
                resp_payload = {"status": "Rejected"}
            elif not self.reserve_can_accept(reserve_options.get("connectorId")):
                resp_payload = {"status": "Occupied"}
            else:
                resp_payload = {"status": "Accepted"}
                asyncio.create_task(utility.run_with_delay(self.flow_reserve(reserve_options), 2))

        if req_action == "CancelReservation".lower():
            cancel_reservation_id: typing.Optional[int] = req_payload.get("reservationId")
            if not self.reserve_can_cancel(cancel_reservation_id):
                resp_payload = {"status": "Rejected"}
            else:
                resp_payload = {"status": "Accepted"}
                asyncio.create_task(utility.run_with_delay(
                    self.flow_reservation_cancel(cancel_reservation_id), 2))

        if req_action == "Reset".lower():
            asyncio.create_task(utility.run_with_delay(self.re_initialize(), 2))

        return resp_payload

    async def flow_charge_stop(self):
        self.charge_in_progress = False
        pass

    async def loop_interactive_custom(self):
        await utility.run_menu("What should I do?", [
            utility.MenuEntry("Back", is_back=True, shortcut="0"),
            utility.MenuEntry("HeartBeat", self.action_heart_beat, shortcut="1"),
            utility.MenuEntry("StatusUpdate", self._interactive_status_update, shortcut="2"),
            utility.MenuEntry("Show reservation state",
                              self.interactive_reservation_show, shortcut="3"),
            utility.MenuEntry("Make reservation (simulate ReserveNow)",
                              self.interactive_reservation_make, shortcut="4"),
            utility.MenuEntry("Cancel reservation (simulate CancelReservation)",
                              self.interactive_reservation_cancel, shortcut="5"),
            utility.MenuEntry("Full custom", self._interactive_full_custom, shortcut="s"),
        ])

    async def _interactive_status_update(self) -> None:
        status: str = await utility.select_from_list(
            "Which status?", OCPP_16_CONNECTOR_STATUSES)
        error_code: str = await utility.select_from_list(
            "Which errorCode?", OCPP_16_ERROR_CODES)
        connector: str = await utility.prompt_text("Which connector?")
        await self.action_status_update_ocpp(status, error_code, {
            'connectorId': connector,
        })

    async def _interactive_full_custom(self) -> None:
        input_action: str = await utility.prompt_text("Enter full custom action name:")
        input_payload: str = await utility.prompt_text("Enter full custom payload:")
        await self.by_device_req_send_raw(json.loads(input_payload), input_action)
