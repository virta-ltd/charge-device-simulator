import datetime
from unittest.mock import MagicMock, AsyncMock

import pytest

from device.ensto.device_ensto import DeviceEnsto
from device.ocpp_j.abstract_device_ocpp_j import AbstractDeviceOcppJ
from device.ocpp_j.device_ocpp_j16 import DeviceOcppJ16
from device.ocpp_j.device_ocpp_j201 import DeviceOcppJ201
from device.ocpp_s.device_ocpp_s import DeviceOcppS

# Configure pytest-asyncio
pytest_plugins = ('pytest_asyncio',)


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "asyncio: mark test as an asyncio test."
    )


class ConcreteDeviceOcppJ(AbstractDeviceOcppJ):
    """Concrete implementation of AbstractDeviceOcppJ for testing purposes."""

    protocols = ["ocpp1.6"]

    async def action_register(self) -> bool:
        return True

    async def action_authorize(self, options: dict) -> bool:
        return True

    async def action_status_update(self, status, options: dict) -> bool:
        return True

    async def action_charge_start(self, options: dict) -> bool:
        return True

    async def action_meter_value(self, options: dict, meter_value: int = None, time_stamp: str = None) -> bool:
        return True

    async def action_charge_stop(self, options: dict) -> bool:
        return True

    async def loop_interactive_custom(self):
        pass


@pytest.fixture
def ocpp_j_device():
    """Creates a ConcreteDeviceOcppJ instance for testing abstract OCPP-J methods."""
    return ConcreteDeviceOcppJ("test-device-001")


@pytest.fixture
def device_ocpp_j16():
    """Creates a DeviceOcppJ16 instance for testing."""
    device = DeviceOcppJ16("test-device-16")
    device._ws = MagicMock()
    device._ws.send = AsyncMock()
    return device


@pytest.fixture
def device_ocpp_j201():
    """Creates a DeviceOcppJ201 instance for testing."""
    device = DeviceOcppJ201("test-device-201")
    device._ws = MagicMock()
    device._ws.send = AsyncMock()
    return device


@pytest.fixture
def fixed_time():
    """Returns a fixed datetime for consistent testing."""
    return datetime.datetime(2025, 1, 15, 12, 0, 0, tzinfo=datetime.timezone.utc)


@pytest.fixture
def time_after_5_minutes(fixed_time):
    """Returns fixed_time plus 5 minutes."""
    return fixed_time + datetime.timedelta(minutes=5)


@pytest.fixture
def device_ocpp_s():
    """Creates a DeviceOcppS instance for testing."""
    device = DeviceOcppS("test-device-s")
    device._client_service = MagicMock()
    return device


@pytest.fixture
def device_ensto():
    """Creates a DeviceEnsto instance for testing."""
    device = DeviceEnsto("test-device-ensto")
    return device
