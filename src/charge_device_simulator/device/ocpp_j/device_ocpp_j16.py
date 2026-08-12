import json
import sys
import typing

from .. import utility
from ..error_reasons import ErrorReasons
from ..ocpp_enums import OCPP_16_CONNECTOR_STATUSES, OCPP_16_ERROR_CODES
from .abstract_device_ocpp_j import AbstractDeviceOcppJ

if sys.platform != "win32":
    # Fake call to readline module to make sure it is loaded
    # we need this since on OS-X if the readline module is not loaded, the input
    # from terminal using input() will be limited to small number of characters
    import readline
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
            await self.handle_error(
                f"Action {action} Response Failed:\n{json.dumps(resp_json)}",
                ErrorReasons.InvalidResponse)
            return False
        self.logger.info(f"Action {action} End")
        return True

    async def action_status_update(self, status, options: dict) -> bool:
        return await self.action_status_update_ocpp(status, "NoError", options)

    async def action_status_update_ocpp(self, status, errorCode, options: dict) -> bool:
        action = "StatusNotification"
        self.logger.info(f"Action {action} Start")
        json_payload = {
            "connectorId": options.get("connectorId", 1),
            "errorCode": errorCode,
            "status": status
        }
        if await self.by_device_req_send(action, json_payload) is None:
            return False
        self.logger.info(f"Action {action} End")
        return True

    async def action_authorize(self, options: dict) -> bool:
        action = "Authorize"
        self.logger.info(f"Action {action} Start")
        id_tag = options.get("idTag", "-")
        key_name = "idTagInfo"
        json_payload = {
            "idTag": id_tag
        }
        resp_json = await self.by_device_req_send(action, json_payload)

        if resp_json is None or len(resp_json) != 3 or resp_json[2][key_name]['status'] != 'Accepted':
            await self.handle_error(
                f"Action {action} Response Failed:\n{json.dumps(resp_json)}",
                ErrorReasons.InvalidResponse)
            return False
        id_tag_info: typing.Dict[str, typing.Any] = resp_json[2][key_name]
        self._last_authorize_info = {
            "id_tag": id_tag,
            "parent_id_tag": id_tag_info.get("parentIdTag"),
        }
        self.logger.info(f"Action {action} End")
        return True

    async def action_charge_start(self, options: dict) -> bool:
        self.fill_missing_options_charge_start(options)
        action = "StartTransaction"
        self.logger.info(f"Action {action} Start")
        key_name = "idTagInfo"
        id_tag = options.get("idTag", "-")
        conenctor_id = options.get("connectorId", 1)
        json_payload = {
            "timestamp": options["chargeStartTime"],
            "connectorId": conenctor_id,
            "meterStart": options["meterStart"],
            "idTag": id_tag
        }
        if "reservationId" in options:
            json_payload["reservationId"] = options["reservationId"]
        resp_json = await self.by_device_req_send(action, json_payload)
        if resp_json is None or len(resp_json) != 3 or resp_json[2][key_name]['status'] != 'Accepted':
            await self.handle_error(
                f"Action {action} Response Failed:\n{json.dumps(resp_json)}",
                ErrorReasons.InvalidResponse)
            return False
        self.charge_id = resp_json[2]['transactionId']
        self.charge_in_progress = True
        self.logger.info(f"Action {action} End")
        return True

    async def action_meter_value(self, options: dict, meter_value: int = None, time_stamp: str = None) -> bool:
        action = "MeterValues"
        self.logger.info(f"Action {action} Start")
        conenctor_id = options.get("connectorId", 1)
        json_payload = {
            "connectorId": conenctor_id,
            "meterValue": [{
                "timestamp": time_stamp if time_stamp else self.utcnow_iso(),
                # OCPP 1.6J types sampledValue.value as a string; sending a
                # bare number makes schema-validating backends drop the sample.
                "sampledValue": [{
                    "value": str(meter_value if meter_value is not None else self.charge_meter_value_current(options)),
                    "context": "Sample.Periodic",
                    "measurand": "Energy.Active.Import.Register",
                    "location": "Outlet",
                    "unit": "Wh"
                }]
            }]
        }
        # transactionId is optional and only meaningful while a transaction is
        # open; outside one charge_id holds -1 or the previous session's id,
        # which schema-strict backends reject or misattribute.
        if self.charge_id != -1:
            json_payload["transactionId"] = self.charge_id
        resp_json = await self.by_device_req_send(action, json_payload)
        if resp_json is None:
            return False
        self.logger.info(f"Action {action} End")
        return True

    async def action_charge_stop(self, options: dict) -> bool:
        self.fill_missing_options_charge_stop(options)
        action = "StopTransaction"
        self.logger.info(f"Action {action} Start")
        key_name = "idTagInfo"
        id_tag = options.get("idTag", "-")
        json_payload = {
            "timestamp": options["chargeStopTime"],
            "transactionId": self.charge_id,
            "meterStop": options["meterStop"],
            "idTag": id_tag,
            "reason": options.get("stopReason", "Local"),
            # Backends build the CDR from the closing register reading; without
            # a Transaction.End sample some cannot price the session and leave
            # it closed-but-unbilled.
            "transactionData": [{
                "timestamp": options["chargeStopTime"],
                "sampledValue": [{
                    "value": str(options["meterStop"]),
                    "context": "Transaction.End",
                    "measurand": "Energy.Active.Import.Register",
                    "location": "Outlet",
                    "unit": "Wh"
                }]
            }]
        }
        resp_json = await self.by_device_req_send(action, json_payload)
        if resp_json is None or len(resp_json) != 3 or not isinstance(resp_json[2], dict):
            await self.handle_error(
                f"Action {action} Response Failed:\n{json.dumps(resp_json)}",
                ErrorReasons.InvalidResponse)
            return False
        # idTagInfo is optional in StopTransaction.conf, and its status is
        # authorization info about the idTag (e.g. Blocked for future use) —
        # not whether the stop was registered. The CSMS closes the transaction
        # the moment it answers the CALL, so any valid CALLRESULT is a
        # successful stop; treating `[3, id, {}]` as failure crashed the flow
        # and skipped the closing Available status.
        id_tag_info = resp_json[2].get(key_name)
        if id_tag_info is not None and id_tag_info.get('status') != 'Accepted':
            self.logger.warning(
                f"Action {action} idTagInfo status not Accepted (transaction still stopped):\n{json.dumps(id_tag_info)}")
        self.charge_id = -1
        self.logger.info(f"Action {action} End")
        return True

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
        message: str = await utility.prompt_text("Enter full custom message:")
        await self.by_device_req_send_raw(message, "Custom")