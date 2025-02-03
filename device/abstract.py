import abc
import asyncio
import datetime
import logging
import os
import sys

from device.error_reasons import ErrorReasons


class DeviceAbstract(abc.ABC):
    on_error = []

    def __init__(self, device_id):
        self.register_on_initialize = True
        self.deviceId = device_id
        self.name = ''
        self.charge_in_progress = False
        self.charge_id = -1
        envKey = 'RESPONSE_TIMEOUT_SECONDS'
        self.response_timeout_seconds = int(os.environ[envKey]) if envKey in os.environ else 10

    @property
    @abc.abstractmethod
    def logger(self) -> logging:
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
    async def action_authorize(self, **options) -> bool:
        pass

    @abc.abstractmethod
    async def action_status_update(self, status, **options) -> bool:
        pass

    @abc.abstractmethod
    async def action_charge_start(self, **options) -> bool:
        pass

    @abc.abstractmethod
    async def action_meter_value(self, **options) -> bool:
        pass

    @abc.abstractmethod
    async def action_charge_stop(self, **options) -> bool:
        pass

    @abc.abstractmethod
    async def action_data_transfer(self, **options) -> bool:
        pass

    @abc.abstractmethod
    async def flow_heartbeat(self) -> bool:
        pass

    @abc.abstractmethod
    async def flow_authorize(self, **options) -> bool:
        pass

    async def flow_charge(self, auto_stop: bool, **options) -> bool:
        pass

    @abc.abstractmethod
    async def flow_charge_ongoing_actions(self, **options) -> bool:
        pass

    async def flow_charge_ongoing_loop(self, auto_stop: bool, **options):
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
                if not await self.action_meter_value(meter_value=i["meterValue"], time_stamp=i["timestamp"], **options):
                    return False
            return True
        else:
            charge_loop_counter = 0
            while self.charge_in_progress:
                await asyncio.sleep(15)
                charge_loop_counter += 1
                if not await self.flow_charge_ongoing_actions(**options):
                    return False
                if auto_stop and charge_loop_counter >= 5:
                    break
            await asyncio.sleep(5)
            return True

    @staticmethod
    def utcnow_iso() -> str:
        return datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc).isoformat()

    @staticmethod
    def utcnow() -> datetime:
        return datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)

    @abc.abstractmethod
    async def loop_interactive_custom(self):
        pass

    def charge_can_start(self):
        return not self.charge_in_progress

    def charge_can_stop(self, req_id):
        return self.charge_in_progress and self.charge_id == req_id

    @abc.abstractmethod
    def charge_meter_value_current(self, **options):
        pass
