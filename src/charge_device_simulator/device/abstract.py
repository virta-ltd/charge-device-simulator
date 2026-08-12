import abc
import asyncio
import datetime
import logging
import os
import sys
import typing

from . import utility
from .error_reasons import ErrorReasons


class DeviceAbstract(abc.ABC):
    on_error = []

    def __init__(self, device_id: str):
        self.register_on_initialize: bool = True
        self.deviceId: str = device_id
        self.name: str = ''
        self.charge_in_progress: bool = False
        self.charge_id: typing.Any = -1
        self.reservation_id: typing.Optional[int] = None
        self.reservation_connector_id: typing.Optional[int] = None
        self.reservation_id_tag: typing.Optional[str] = None
        self.reservation_parent_id_tag: typing.Optional[str] = None
        self.reservation_expiry_date: typing.Optional[str] = None
        self._last_authorize_info: typing.Optional[typing.Dict[str, typing.Optional[str]]] = None
        envKey = 'RESPONSE_TIMEOUT_SECONDS'
        self.response_timeout_seconds: int = int(os.environ[envKey]) if envKey in os.environ else 15

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
        # Only log a traceback when there's actually a live exception. Plain
        # `logger.exception` would otherwise render "NoneType: None" for
        # protocol-level rejections that don't originate in an except block.
        if sys.exc_info()[0] is not None:
            self.logger.exception(desc)
        else:
            self.logger.error(desc)
        for event in self.on_error:
            await event(desc, reason)
        if self.error_exit:
            loop = asyncio.get_event_loop()
            loop.call_soon_threadsafe(loop.stop)
            sys.exit(1)
        else:
            return False
        pass

    def by_device_req_resp_timeout(self) -> None:
        # None makes callers treat the timeout as a failed request; anything
        # truthy would let actions that only check `is None` log success for
        # a request the middleware never answered.
        self.logger.warning(f"Response timeout, {self.response_timeout_seconds} seconds passed")
        return None

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
            # Baseline for the delivered-sample record: with zero samples
            # delivered the session reported no energy beyond meterStart.
            options[self._LAST_SENT_SCRIPTED_METER_VALUE] = options.get("meterStart")
            for i in meter_values:
                await asyncio.sleep(i["secondsToSleep"])
                if not await self.action_meter_value(options, meter_value=i["meterValue"], time_stamp=i["timestamp"]):
                    return False
                options[self._LAST_SENT_SCRIPTED_METER_VALUE] = i["meterValue"]
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

    def reserve_can_accept(self, connector_id: typing.Optional[int]) -> bool:
        if self.charge_in_progress:
            return False
        # The device stores a single reservation, so accepting another while
        # one is active — same connector, a different one, or connector 0,
        # which reserves the charge point as a whole — would silently
        # overwrite the stored record and drop the protection the first
        # Accepted promised.
        if self.reservation_is_active():
            return False
        return True

    def reserve_can_cancel(self, reservation_id: typing.Optional[int]) -> bool:
        return self.reservation_is_active() and self.reservation_id == reservation_id

    def reservation_set(
        self,
        reservation_id: typing.Optional[int],
        connector_id: typing.Optional[int],
        id_tag: typing.Optional[str],
        parent_id_tag: typing.Optional[str],
        expiry_date: typing.Optional[str],
    ) -> None:
        self.reservation_id = reservation_id
        self.reservation_connector_id = connector_id
        self.reservation_id_tag = id_tag
        self.reservation_parent_id_tag = parent_id_tag
        self.reservation_expiry_date = expiry_date

    def reservation_clear(self) -> None:
        self.reservation_id = None
        self.reservation_connector_id = None
        self.reservation_id_tag = None
        self.reservation_parent_id_tag = None
        self.reservation_expiry_date = None

    def _pre_charge_reservation_gate(self, options: typing.Dict[str, typing.Any]) -> bool:
        """If an active reservation covers the requested connector — stored on
        that connector, or on connector 0, which in OCPP 1.6 reserves the
        charge point as a whole and so applies to every connector — validate
        the most recent authorize info against it (direct idTag or
        parent/group match). On match, injects reservationId into options so
        the start payload carries it."""
        # Mirror action_charge_start's default — a missing connectorId would
        # otherwise compare None against the stored connector and silently
        # skip the gate (letting a non-matching tag through on a reserved
        # connector).
        connector_id = options.get("connectorId", 1)
        if not self.reservation_is_active() or self.reservation_connector_id not in (0, connector_id):
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

    @staticmethod
    def _scripted_final_meter_value(options: typing.Dict[str, typing.Any]) -> typing.Optional[int]:
        """Last register reading of a scripted meterValues list, if one is
        configured. The stop reading must repeat it — a meterStop computed
        from wall-clock time would contradict the samples already sent."""
        meter_values = options.get("meterValues")
        if isinstance(meter_values, list) and meter_values:
            last = meter_values[-1]
            if isinstance(last, dict) and "meterValue" in last:
                return last["meterValue"]
        return None

    def _scripted_stop_meter_value(self, options: typing.Dict[str, typing.Any]) -> typing.Optional[int]:
        """Register reading the stop payload should carry for a scripted
        meterValues session, or None when no script is configured. Prefers the
        last sample the ongoing loop actually delivered: when a send fails
        mid-script the remaining samples never went out, and a meterStop above
        the last delivered reading would bill energy the session never
        reported. Falls back to the script's final value when the loop hasn't
        run (direct action_charge_stop calls)."""
        scripted_final = self._scripted_final_meter_value(options)
        if scripted_final is None:
            return None
        last_sent = options.get(self._LAST_SENT_SCRIPTED_METER_VALUE)
        return last_sent if last_sent is not None else scripted_final

    # Recorded inside the options dict itself so the record travels with the
    # dict shared across cycles. Payload builders read specific keys only, so
    # the extra entry never reaches the wire.
    _PINNED_CHARGE_CYCLE_KEYS = "_pinnedChargeCycleKeys"
    _LAST_SENT_SCRIPTED_METER_VALUE = "_lastSentScriptedMeterValue"
    _CHARGE_CYCLE_EPHEMERAL_KEYS = ("chargeStartTime", "chargeStopTime", "meterStop", "meterStart")

    def _reset_charge_cycle_options(self, options: typing.Dict[str, typing.Any]) -> None:
        """Drop the previous cycle's auto-filled values so every flow_charge
        run picks up fresh start/stop timestamps and a recomputed meterStop,
        while preserving values the operator configured. The options dict is
        shared across runs (frequent flows pass the configured dict by
        reference), so without the reset every cycle after the first replays
        the first cycle's chargeStartTime/chargeStopTime/meterStop — producing
        overlapping transactions whose meterStop contradicts the periodic
        meter values, which billing backends reject. But the operator may pin
        any of those keys (plus meterStart) up front to replay a deterministic
        session: the first call records which ephemeral keys are already
        present, and every call drops only the unpinned ones. The previous
        cycle's meterStop is carried into meterStart so the energy register
        stays monotonic like a real meter — skipped when either meter key is
        pinned (the configured session shape wins) or a scripted meterValues
        list is configured: its readings are absolute and replay identically
        each cycle, so carrying the stop forward would put meterStart above
        the replayed samples (a register rewind). reservationId is always
        dropped: the reservation gate injects it per cycle, and replaying it
        would attach an already-consumed reservation to the next
        StartTransaction."""
        pinned = options.get(self._PINNED_CHARGE_CYCLE_KEYS)
        if pinned is None:
            pinned = tuple(key for key in self._CHARGE_CYCLE_EPHEMERAL_KEYS if key in options)
            options[self._PINNED_CHARGE_CYCLE_KEYS] = pinned
        if ("meterStop" in options
                and "meterStop" not in pinned and "meterStart" not in pinned
                and self._scripted_final_meter_value(options) is None):
            options["meterStart"] = options["meterStop"]
        for key in ("chargeStartTime", "chargeStopTime", "meterStop"):
            if key not in pinned:
                options.pop(key, None)
        options.pop("reservationId", None)
        # Per-cycle delivery record; a stale value would make the next cycle's
        # stop reading repeat the previous cycle's last delivered sample.
        options.pop(self._LAST_SENT_SCRIPTED_METER_VALUE, None)

    def _consume_reservation_if_used(self, options: typing.Dict[str, typing.Any]) -> None:
        if "reservationId" in options and self.reservation_is_active() \
                and options["reservationId"] == self.reservation_id:
            self.logger.info(f"Reservation {self.reservation_id} consumed by charge start")
            self.reservation_clear()

    def _reserve_now_options_from_payload(
        self, req_payload: typing.Dict[str, typing.Any],
    ) -> typing.Dict[str, typing.Any]:
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

    async def flow_reserve(self, options: typing.Dict[str, typing.Any]) -> bool:
        """Apply a ReserveNow request: validate, store state, send Reserved
        StatusNotification. Returns True if reservation was accepted."""
        log_title = self.flow_reserve.__name__
        self.logger.info(f"Flow {log_title} Start: connectorId={options.get('connectorId')}, "
                         f"reservationId={options.get('reservationId')}")
        connector_id: typing.Optional[int] = options.get("connectorId")
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

    async def interactive_reservation_show(self) -> None:
        """Print the device's current reservation state."""
        self.logger.info(
            f"Reservation state: id={self.reservation_id}, "
            f"connectorId={self.reservation_connector_id}, "
            f"idTag={self.reservation_id_tag}, "
            f"parentIdTag={self.reservation_parent_id_tag}, "
            f"expiryDate={self.reservation_expiry_date}")

    async def interactive_reservation_make(self) -> None:
        """Prompt for ReserveNow fields and run flow_reserve."""
        reservation_id_input: str = await utility.prompt_text("reservationId (integer):")
        connector_id_input: str = await utility.prompt_text("connectorId:")
        id_tag_input: str = await utility.prompt_text("idTag:")
        parent_id_tag_input: str = await utility.prompt_text("parentIdTag (blank to skip):")
        expiry_date_input: str = await utility.prompt_text(
            "expiryDate ISO (blank for now+1h):")
        options: typing.Dict[str, typing.Any] = {
            "reservationId": int(reservation_id_input) if reservation_id_input else None,
            "connectorId": int(connector_id_input) if connector_id_input else None,
            "evseId": int(connector_id_input) if connector_id_input else None,
            "idTag": id_tag_input or None,
            "parentIdTag": parent_id_tag_input or None,
            "expiryDate": expiry_date_input or (
                self.utcnow() + datetime.timedelta(hours=1)).isoformat(),
        }
        await self.flow_reserve(options)

    async def interactive_reservation_cancel(self) -> None:
        """Prompt for a reservationId (blank uses stored) and run flow_reservation_cancel."""
        cancel_input: str = await utility.prompt_text(
            "reservationId (blank uses stored):")
        cancel_reservation_id: typing.Optional[int] = (
            int(cancel_input) if cancel_input else self.reservation_id)
        await self.flow_reservation_cancel(cancel_reservation_id)

    async def flow_reservation_cancel(
        self,
        reservation_id: typing.Optional[int],
        options: typing.Optional[typing.Dict[str, typing.Any]] = None,
    ) -> bool:
        log_title = self.flow_reservation_cancel.__name__
        self.logger.info(f"Flow {log_title} Start: reservationId={reservation_id}")
        if not self.reserve_can_cancel(reservation_id):
            self.logger.info(f"Flow {log_title} Rejected (no matching reservation)")
            return False
        notify_options: typing.Dict[str, typing.Any] = dict(options) if options else {}
        notify_options.setdefault("connectorId", self.reservation_connector_id)
        self.reservation_clear()
        if not await self.action_status_update("Available", notify_options):
            return False
        self.logger.info(f"Flow {log_title} End")
        return True

    @abc.abstractmethod
    def charge_meter_value_current(self, options: dict):
        pass
