import datetime
import sys
import uuid

import aioconsole
from device.ocpp_j.abstract_device_ocpp_j import AbstractDeviceOcppJ
from device.error_reasons import ErrorReasons

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
            await self.handle_error(f"Action {action} Response Failed", ErrorReasons.InvalidResponse)
            return False
        self.logger.info(f"Action {action} End")
        return True

    async def action_status_update(self, status, **options) -> bool:
        return await self.action_status_update_ocpp(status, **options)
        
    async def action_status_update_ocpp(self, status, **options) -> bool:
        action = "StatusNotification"
        self.logger.info(f"Action {action} Start")
        json_payload = {
            "connectorId": options.pop("connectorId", 1),
            "evseId": options.pop("evseId", 1),
            "connectorStatus": status,
            "timestamp": self.utcnow_iso()
        }
        if await self.by_device_req_send(action, json_payload) is None:
            return False
        self.logger.info(f"Action {action} End")
        return True

    async def action_authorize(self, **options) -> bool:
        action = "Authorize"
        self.logger.info(f"Action {action} Start")
        id_tag = options.pop("idTag", "-")
        json_payload = {
            "idToken": {
                "idToken": id_tag,
                "type":"ISO14443"
            }
        }
        key_name = "idTokenInfo"
        resp_json = await self.by_device_req_send(action, json_payload)

        if resp_json is None or resp_json[2][key_name]['status'] != 'Accepted':
            await self.handle_error(f"Action {action} Response Failed", ErrorReasons.InvalidResponse)
            return False
        self.logger.info(f"Action {action} End")
        return True

    async def action_charge_start(self, **options) -> bool:
        self.fill_missing_options_charge_start(options)
        action = "StartTransaction"
        self.logger.info(f"Action {action} Start")
        id_tag = options.pop("idTag", "-")
        evse_id = options.pop("evseId", 1)
        conenctor_id = options.pop("connectorId", 1)
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
            await self.handle_error(f"Action {action} Response Failed", ErrorReasons.InvalidResponse)
            return False
        self.charge_id = transaction_id
        self.charge_in_progress = True
        self.logger.info(f"Action {action} End")
        return True

    async def action_meter_value(self, meter_value: int = None, time_stamp: datetime = None, **options) -> bool:
        action = "MeterValues"
        self.logger.info(f"Action {action} Start")
        evse_id = options.pop("evseId", 1)
        conenctor_id = options.pop("connectorId", 1)
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
                            "value": meter_value if meter_value else self.charge_meter_value_current(**options),
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

    async def action_charge_stop(self, **options) -> bool:
        self.fill_missing_options_charge_stop(options)
        action = "StopTransaction"
        self.logger.info(f"Action {action} Start")
        id_tag = options.pop("idTag", "-")
        evse_id = options.pop("evseId", 1)
        conenctor_id = options.pop("connectorId", 1)
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
        if not await self.action_status_update("Occupied", **options):
            self.charge_in_progress = False
            return False
        if not await self.action_charge_start(**options):
            self.charge_in_progress = False
            return False
        if not await self.flow_charge_ongoing_loop(auto_stop, **options):
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
                input2 = await aioconsole.ainput("Which evseId?\n")
                input3 = await aioconsole.ainput("Which connector?\n")
                await self.action_status_update_ocpp(input1, ** {
                    'evseId': int(input2),
                    'connectorId': int(input3),
                })
            elif input1 == "99":
                input1 = input("Enter full custom message:\n")
                await self.by_device_req_send_raw(input1, "Custom")
        pass