import datetime
import json
import sys
import typing
import uuid

from .abstract_device_ocpp_j import AbstractDeviceOcppJ
from .. import utility
from ..error_reasons import ErrorReasons
from ..ocpp_enums import OCPP_201_CONNECTOR_STATUSES

if sys.platform != "win32":
    # Fake call to readline module to make sure it is loaded
    # we need this since on OS-X if the readline module is not loaded, the input
    # from terminal using input() will be limited to small number of characters
    import readline
    readline.get_completion_type()

class DeviceOcppJ201(AbstractDeviceOcppJ):
    def __init__(self, device_id):
        super().__init__(device_id)
        self.protocols = ['ocpp2.0.1']
        self.charge_seq_no = 0
    
    async def action_register(self) -> bool:
        action = "BootNotification"
        self.logger.info(f"Action {action} Start")
        json_payload = {}
        json_payload['chargingStation'] = {}
        json_payload['reason'] = 'RemoteReset'
        if self.spec_chargePointVendor is not None:
            json_payload['chargingStation']['vendorName'] = self.spec_chargePointVendor
        if self.spec_chargePointModel is not None:
            json_payload['chargingStation']['model'] = self.spec_chargePointModel
        if self.spec_chargeBoxSerialNumber is not None:
            json_payload['chargingStation']['serialNumber'] = self.spec_chargeBoxSerialNumber
        if self.spec_firmwareVersion is not None:
            json_payload['chargingStation']['firmwareVersion'] = self.spec_firmwareVersion
        if self.spec_iccid is not None:
            if 'modem' not in json_payload['chargingStation']:
                json_payload['chargingStation']['modem'] = {}
            json_payload['chargingStation']['modem']['iccid'] = self.spec_iccid
        if self.spec_imsi is not None:
            if 'modem' not in json_payload['chargingStation']:
                json_payload['chargingStation']['modem'] = {}
            json_payload['chargingStation']['modem']['imsi'] = self.spec_imsi
        resp_json = await self.by_device_req_send(action, json_payload)
        if resp_json is None or resp_json[2]['status'] != 'Accepted':
            await self.handle_error(
                f"Action {action} Response Failed:\n{json.dumps(resp_json)}",
                ErrorReasons.InvalidResponse)
            return False
        self.logger.info(f"Action {action} End")
        return True

    async def action_status_update(self, status, options: dict) -> bool:
        return await self.action_status_update_ocpp(status, options)

    async def action_status_update_ocpp(self, status, options: dict) -> bool:
        action = "StatusNotification"
        self.logger.info(f"Action {action} Start")
        json_payload = {
            "connectorId": options.get("connectorId", 1),
            "evseId": options.get("evseId", 1),
            "connectorStatus": status,
            "timestamp": self.utcnow_iso()
        }
        if await self.by_device_req_send(action, json_payload) is None:
            return False
        self.logger.info(f"Action {action} End")
        return True

    async def action_authorize(self, options: dict) -> bool:
        action = "Authorize"
        self.logger.info(f"Action {action} Start")
        id_tag = options.get("idTag", "-")
        json_payload = {
            "idToken": {
                "idToken": id_tag,
                "type":"ISO14443"
            }
        }
        key_name = "idTokenInfo"
        resp_json = await self.by_device_req_send(action, json_payload)

        if resp_json is None or resp_json[2][key_name]['status'] != 'Accepted':
            await self.handle_error(
                f"Action {action} Response Failed:\n{json.dumps(resp_json)}",
                ErrorReasons.InvalidResponse)
            return False
        id_token_info: typing.Dict[str, typing.Any] = resp_json[2][key_name]
        group_id_token: typing.Dict[str, typing.Any] = id_token_info.get("groupIdToken") or {}
        self._last_authorize_info = {
            "id_tag": id_tag,
            "parent_id_tag": group_id_token.get("idToken"),
        }
        self.logger.info(f"Action {action} End")
        return True

    async def action_charge_start(self, options: dict) -> bool:
        self.fill_missing_options_charge_start(options)
        action = "StartTransaction"
        self.logger.info(f"Action {action} Start")
        id_tag = options.get("idTag", "-")
        evse_id = options.get("evseId", 1)
        conenctor_id = options.get("connectorId", 1)
        transaction_id = str(uuid.uuid4())
        action = "TransactionEvent"
        json_payload = {
            "eventType": "Started",
            "timestamp": options["chargeStartTime"],
            "triggerReason": "Authorized",
            "seqNo":0,
            "transactionInfo": {
                "transactionId": transaction_id,
                "chargingState":"Idle"
            },
            **({"reservationId": options["reservationId"]} if "reservationId" in options else {}),
            "meterValue":[
                {
                    "sampledValue": [
                        {
                            "value": options["meterStart"],
                            "context":"Transaction.Begin",
                            "unitOfMeasure": {
                                "unit":"Wh"
                            }
                        }
                    ],
                "timestamp":options["chargeStartTime"]
                }
            ],
            "evse": {
                "id": evse_id,
                "connectorId": conenctor_id
            },
            "idToken": {
                "idToken": id_tag,
                "type":"ISO14443"
                }
            }
        key_name = "idTokenInfo"
        resp_json = await self.by_device_req_send(action, json_payload)
        if resp_json is None or resp_json[2][key_name]['status'] != 'Accepted':
            await self.handle_error(
                f"Action {action} Response Failed:\n{json.dumps(resp_json)}",
                ErrorReasons.InvalidResponse)
            return False
        self.charge_id = transaction_id
        self.charge_in_progress = True
        self.logger.info(f"Action {action} End")
        return True

    async def action_meter_value(self, options: dict, meter_value: int = None, time_stamp: datetime = None) -> bool:
        action = "MeterValues"
        self.logger.info(f"Action {action} Start")
        evse_id = options.get("evseId", 1)
        conenctor_id = options.get("connectorId", 1)
        self.charge_seq_no += 1
        action = "TransactionEvent"
        json_payload = {
            "eventType": "Updated",
            "timestamp": time_stamp if time_stamp else self.utcnow_iso(),
            "triggerReason": "ChargingStateChanged",
            "seqNo": self.charge_seq_no,
            "transactionInfo": {
                "transactionId": self.charge_id,
                "chargingState":"Charging"
            },
            "meterValue":[
                {
                    "sampledValue": [
                        {
                            "value": meter_value if meter_value else self.charge_meter_value_current(options),
                            "context":"Sample.Periodic",
                            "measurand": "Energy.Active.Import.Register",
                            "location": "Outlet",
                            "unitOfMeasure": {
                                "unit":"Wh"
                            }
                        }
                    ],
                "timestamp":time_stamp if time_stamp else self.utcnow_iso(),
                }
            ],
            "evse": {
                "id": evse_id,
                "connectorId": conenctor_id
            }
        }
        resp_json = await self.by_device_req_send(action, json_payload)
        if resp_json is None:
            return False
        self.logger.info(f"Action {action} End")
        return True

    async def action_charge_stop(self, options: dict) -> bool:
        self.fill_missing_options_charge_stop(options)
        action = "StopTransaction"
        self.logger.info(f"Action {action} Start")
        id_tag = options.get("idTag", "-")
        evse_id = options.get("evseId", 1)
        conenctor_id = options.get("connectorId", 1)
        self.charge_seq_no += 1
        action = "TransactionEvent"
        key_name = "idTokenInfo"
        json_payload = {
            "eventType": "Ended",
            "timestamp": options["chargeStopTime"],
            "triggerReason": "ChargingStateChanged",
            "seqNo": self.charge_seq_no,
            "transactionInfo": {
                "transactionId": self.charge_id,
                "chargingState":"Transaction.Ended"
            },
            "meterValue":[
                {
                    "sampledValue": [
                        {
                            "value": options["meterStop"],
                            "context":"Sample.Periodic",
                            "measurand": "Energy.Active.Import.Register",
                            "location": "Outlet",
                            "unitOfMeasure": {
                                "unit":"kWh"
                            }
                        }
                    ],
                "timestamp":options["chargeStopTime"],
                }
            ],
            "evse": {
                "id": evse_id,
                "connectorId": conenctor_id
            },
            "idToken": {
                "idToken": id_tag,
                "type":"ISO14443"
            }
        }
        resp_json = await self.by_device_req_send(action, json_payload)
        if resp_json is None or resp_json[2][key_name]['status'] != 'Accepted':
            await self.handle_error(
                f"Action {action} Response Failed:\n{json.dumps(resp_json)}",
                ErrorReasons.InvalidResponse)
            return False
        self.logger.info(f"Action {action} End")
        return True

    async def flow_preparing(self) -> bool:
        log_title = self.flow_preparing.__name__
        self.logger.info(f"Flow {log_title} Start")
        if self.charge_in_progress:
            self.logger.info(f"Flow {log_title} Skipped, charge in progress")
        else:
            self.is_preparing = True
            if not await self.action_status_update("Occupied", {}):
                self.is_preparing = False
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
        if not await self.action_status_update("Occupied", options):
            self.charge_in_progress = False
            return False
        if not await self.action_charge_start(options):
            self.charge_in_progress = False
            return False
        self._consume_reservation_if_used(options)
        if not await self.flow_charge_ongoing_loop(auto_stop, options):
            self.charge_in_progress = False
            return False
        if not await self.action_charge_stop(options):
            self.charge_in_progress = False
            return False
        if self.is_preparing:
            if not await self.action_status_update("Occupied", options):
                self.charge_in_progress = False
                return False
        else:
            if not await self.action_status_update("Available", options):
                self.charge_in_progress = False
                return False
        self.logger.info(f"Flow {log_title} End")
        self.charge_in_progress = False
        return True

    def _reserve_now_options_from_payload(
        self, req_payload: typing.Dict[str, typing.Any],
    ) -> typing.Dict[str, typing.Any]:
        id_token: typing.Dict[str, typing.Any] = req_payload.get("idToken") or {}
        group_id_token: typing.Dict[str, typing.Any] = req_payload.get("groupIdToken") or {}
        evse_id: typing.Optional[int] = req_payload.get("evseId")
        return {
            "reservationId": req_payload.get("id"),
            "connectorId": evse_id if evse_id is not None else 1,
            "evseId": evse_id if evse_id is not None else 1,
            "idTag": id_token.get("idToken"),
            "parentIdTag": group_id_token.get("idToken"),
            "expiryDate": req_payload.get("expiryDateTime"),
        }

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
            "Which status?", OCPP_201_CONNECTOR_STATUSES)
        evse_id: str = await utility.prompt_text("Which evseId?")
        connector: str = await utility.prompt_text("Which connector?")
        await self.action_status_update_ocpp(status, {
            'evseId': int(evse_id),
            'connectorId': int(connector),
        })

    async def _interactive_full_custom(self) -> None:
        message: str = await utility.prompt_text("Enter full custom message:")
        await self.by_device_req_send_raw(message, "Custom")