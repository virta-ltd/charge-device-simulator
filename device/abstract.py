import abc
import asyncio
import datetime
import logging
import sys


class DeviceAbstract(abc.ABC):
    def __init__(self, device_id):
        self.register_on_initialize = True
        self.deviceId = device_id

    @property
    @abc.abstractmethod
    def logger(self) -> logging:
        pass

    @abc.abstractmethod
    def initialize(self):
        pass

    @abc.abstractmethod
    def end(self):
        pass

    error_exit = True

    def handle_error(self, desc) -> bool:
        self.logger.error(desc)
        if self.error_exit:
            loop = asyncio.get_event_loop()
            loop.call_soon_threadsafe(loop.stop)
            sys.exit(1)
        pass

    @abc.abstractmethod
    def action_register(self) -> bool:
        pass

    @abc.abstractmethod
    def action_heart_beat(self) -> bool:
        pass

    @abc.abstractmethod
    def action_authorize(self, **options) -> bool:
        pass

    @abc.abstractmethod
    def action_status_update(self, status, **options) -> bool:
        pass

    @abc.abstractmethod
    def action_charge_start(self, **options) -> bool:
        pass

    @abc.abstractmethod
    def action_meter_value(self, **options) -> bool:
        pass

    @abc.abstractmethod
    def action_charge_stop(self, **options) -> bool:
        pass

    @abc.abstractmethod
    async def flow_heartbeat(self) -> bool:
        pass

    @abc.abstractmethod
    async def flow_authorize(self, **options) -> bool:
        pass

    @abc.abstractmethod
    async def flow_charge(self, **options) -> bool:
        pass

    @staticmethod
    def utcnow_iso() -> str:
        return datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc).isoformat()

    @abc.abstractmethod
    async def loop_interactive_custom(self):
        pass
