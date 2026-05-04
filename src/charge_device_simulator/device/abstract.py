import abc
import asyncio
import datetime
import logging
import os
import sys

import aioconsole

from .error_reasons import ErrorReasons


class DeviceAbstract(abc.ABC):
    on_error = []

    def __init__(self, device_id):
        self.register_on_initialize = True
        self.deviceId = device_id
        self.name = ''
        self.charge_in_progress = False
        self.charge_id = -1
        self.reservation_id = None
        self.reservation_connector_id = None
        self.reservation_id_tag = None
        self.reservation_parent_id_tag = None
        self.reservation_expiry_date = None
        self._last_authorize_info = None
        envKey = 'RESPONSE_TIMEOUT_SECONDS'
        self.response_timeout_seconds = int(os.environ[envKey]) if envKey in os.environ else 15

    @property
    @abc.abstractmethod
    def logger(self) -> logging.Logger:
        pass

    @abc.abstractmethod
    async def initialize(self) -> bool:
        pass

    @abc.abstractmethod
    async def end(self):
        pass

    async def re_initialize(self) -> bool:
        await self.end()
        return await self.initialize()

    error_exit = True

    async def handle_error(self, desc, reason: ErrorReasons) -> bool:
        self.logger.exception(desc)
        for event in self.on_error:
            await event(desc, reason)
        if self.error_exit:
            loop = asyncio.get_event_loop()
            loop.call_soon_threadsafe(loop.stop)
            sys.exit(1)
        else:
            return False
        pass

    def by_device_req_resp_timeout(self) -> str:
        return f'"response timeout, {self.response_timeout_seconds} seconds passed"'

    @abc.abstractmethod
    async def action_register(self) -> bool:
        pass

    @abc.abstractmethod
    async def action_heart_beat(self) -> bool:
        pass

    @abc.abstractmethod
    async def action_authorize(self, options: dict) -> bool:
        pass

    @abc.abstractmethod
    async def action_status_update(self, status, options: dict) -> bool:
        pass

    @abc.abstractmethod
    async def action_charge_start(self, options: dict) -> bool:
        pass

    @abc.abstractmethod
    async def action_meter_value(self, options: dict, meter_value: int = None, time_stamp: str = None) -> bool:
        pass

    @abc.abstractmethod
    async def action_charge_stop(self, options: dict) -> bool:
        pass

    @abc.abstractmethod
    async def action_data_transfer(self, options: dict) -> bool:
        pass

    @abc.abstractmethod
    async def flow_heartbeat(self) -> bool:
        pass

    @abc.abstractmethod
    async def flow_authorize(self, options: dict) -> bool:
        pass

    @abc.abstractmethod
    async def flow_charge(self, auto_stop: bool, options: dict) -> bool:
        pass

    @abc.abstractmethod
    async def flow_charge_ongoing_actions(self, options: dict) -> bool:
        pass

    async def flow_charge_ongoing_loop(self, auto_stop: bool, options: dict):
        if "meterValues" in options:
            meter_values = options["meterValues"]
            if (not isinstance(meter_values, list)
                    or not all(isinstance(i, dict)
                               and 'meterValue' in i
                               and 'timestamp' in i
                               and 'secondsToSleep' in i
                               for i in meter_values)):
                raise ValueError("meterValues must be a list of dictionaries with 'meterValue', 'timestamp' and 'secondsToSleep' keys.")
            for i in meter_values:
                await asyncio.sleep(i["secondsToSleep"])
                if not await self.action_meter_value(options, meter_value=i["meterValue"], time_stamp=i["timestamp"]):
                    return False
            return True
        else:
            charge_loop_wait_seconds = options.get("autoActionsLoopDelayInSeconds", 15)
            charge_loop_max = options.get("autoActionsLoopCount", 5)
            charge_loop_counter = 0
            while self.charge_in_progress:
                await asyncio.sleep(charge_loop_wait_seconds)
                charge_loop_counter += 1
                if not await self.flow_charge_ongoing_actions(options):
                    return False
                if auto_stop and charge_loop_counter >= charge_loop_max:
                    break
            await asyncio.sleep(5)
            return True

    @staticmethod
    def utcnow_iso() -> str:
        return datetime.datetime.now(datetime.timezone.utc).isoformat()

    @staticmethod
    def utcnow() -> datetime.datetime:
        return datetime.datetime.now(datetime.timezone.utc)

    @abc.abstractmethod
    async def loop_interactive_custom(self):
        pass

    def charge_can_start(self):
        return not self.charge_in_progress

    def charge_can_stop(self, req_id):
        return self.charge_in_progress and self.charge_id == req_id

    def reservation_is_active(self) -> bool:
        return self.reservation_id is not None

    def reserve_can_accept(self, connector_id) -> bool:
        if self.charge_in_progress:
            return False
        if self.reservation_is_active() and self.reservation_connector_id == connector_id:
            return False
        return True

    def reserve_can_cancel(self, reservation_id) -> bool:
        return self.reservation_is_active() and self.reservation_id == reservation_id

    def reservation_set(self, reservation_id, connector_id, id_tag, parent_id_tag, expiry_date):
        self.reservation_id = reservation_id
        self.reservation_connector_id = connector_id
        self.reservation_id_tag = id_tag
        self.reservation_parent_id_tag = parent_id_tag
        self.reservation_expiry_date = expiry_date

    def reservation_clear(self):
        self.reservation_id = None
        self.reservation_connector_id = None
        self.reservation_id_tag = None
        self.reservation_parent_id_tag = None
        self.reservation_expiry_date = None

    def _pre_charge_reservation_gate(self, options: dict) -> bool:
        """If the connector has an active reservation, validate the most recent
        authorize info against it (direct idTag or parent/group match). On match,
        injects reservationId into options so the start payload carries it."""
        connector_id = options.get("connectorId")
        if not self.reservation_is_active() or self.reservation_connector_id != connector_id:
            return True
        requested_id_tag = options.get("idTag")
        if requested_id_tag is not None and requested_id_tag == self.reservation_id_tag:
            options["reservationId"] = self.reservation_id
            return True
        last_parent = (self._last_authorize_info or {}).get("parent_id_tag")
        if (last_parent is not None
                and self.reservation_parent_id_tag is not None
                and last_parent == self.reservation_parent_id_tag):
            options["reservationId"] = self.reservation_id
            return True
        self.logger.info(
            f"Reservation gate rejected charge: requested idTag/parent did not match reservation "
            f"{self.reservation_id} on connector {connector_id}")
        return False

    def _consume_reservation_if_used(self, options: dict):
        if "reservationId" in options and self.reservation_is_active() \
                and options["reservationId"] == self.reservation_id:
            self.logger.info(f"Reservation {self.reservation_id} consumed by charge start")
            self.reservation_clear()

    def _reserve_now_options_from_payload(self, req_payload: dict) -> dict:
        """Convert an inbound ReserveNow.req payload into the dict shape
        flow_reserve expects. Default covers OCPP 1.6 / OCPP-S 1.5 SOAP.
        Overridden for OCPP 2.0.1."""
        return {
            "reservationId": req_payload.get("reservationId"),
            "connectorId": req_payload.get("connectorId"),
            "idTag": req_payload.get("idTag"),
            "parentIdTag": req_payload.get("parentIdTag"),
            "expiryDate": req_payload.get("expiryDate"),
        }

    async def flow_reserve(self, options: dict) -> bool:
        """Apply a ReserveNow request: validate, store state, send Reserved
        StatusNotification. Returns True if reservation was accepted."""
        log_title = self.flow_reserve.__name__
        self.logger.info(f"Flow {log_title} Start: connectorId={options.get('connectorId')}, "
                         f"reservationId={options.get('reservationId')}")
        connector_id = options.get("connectorId")
        if not self.reserve_can_accept(connector_id):
            self.logger.info(f"Flow {log_title} Rejected (connector busy or already reserved)")
            return False
        self.reservation_set(
            reservation_id=options.get("reservationId"),
            connector_id=connector_id,
            id_tag=options.get("idTag"),
            parent_id_tag=options.get("parentIdTag"),
            expiry_date=options.get("expiryDate"),
        )
        if not await self.action_status_update("Reserved", options):
            return False
        self.logger.info(f"Flow {log_title} End")
        return True

    interactive_reservation_menu = """3: Show reservation state
4: Make reservation (simulate ReserveNow)
5: Cancel reservation (simulate CancelReservation)
"""

    async def interactive_reservation_handle(self, input_choice: str) -> bool:
        """Handle reservation-related entries from a device's interactive menu.
        Returns True if the input was handled."""
        if input_choice == "3":
            self.logger.info(
                f"Reservation state: id={self.reservation_id}, "
                f"connectorId={self.reservation_connector_id}, "
                f"idTag={self.reservation_id_tag}, "
                f"parentIdTag={self.reservation_parent_id_tag}, "
                f"expiryDate={self.reservation_expiry_date}")
            return True
        if input_choice == "4":
            reservation_id = await aioconsole.ainput("reservationId (integer):\n")
            connector_id = await aioconsole.ainput("connectorId:\n")
            id_tag = await aioconsole.ainput("idTag:\n")
            parent_id_tag = await aioconsole.ainput("parentIdTag (blank to skip):\n")
            expiry_date = await aioconsole.ainput("expiryDate ISO (blank for now+1h):\n")
            options = {
                "reservationId": int(reservation_id) if reservation_id else None,
                "connectorId": int(connector_id) if connector_id else None,
                "evseId": int(connector_id) if connector_id else None,
                "idTag": id_tag or None,
                "parentIdTag": parent_id_tag or None,
                "expiryDate": expiry_date or (
                    self.utcnow() + datetime.timedelta(hours=1)).isoformat(),
            }
            await self.flow_reserve(options)
            return True
        if input_choice == "5":
            reservation_id_input = await aioconsole.ainput(
                "reservationId (blank uses stored):\n")
            reservation_id = (int(reservation_id_input)
                              if reservation_id_input
                              else self.reservation_id)
            await self.flow_reservation_cancel(reservation_id)
            return True
        return False

    async def flow_reservation_cancel(self, reservation_id, options: dict = None) -> bool:
        log_title = self.flow_reservation_cancel.__name__
        self.logger.info(f"Flow {log_title} Start: reservationId={reservation_id}")
        if not self.reserve_can_cancel(reservation_id):
            self.logger.info(f"Flow {log_title} Rejected (no matching reservation)")
            return False
        notify_options = dict(options) if options else {}
        notify_options.setdefault("connectorId", self.reservation_connector_id)
        self.reservation_clear()
        if not await self.action_status_update("Available", notify_options):
            return False
        self.logger.info(f"Flow {log_title} End")
        return True

    @abc.abstractmethod
    def charge_meter_value_current(self, options: dict):
        pass
