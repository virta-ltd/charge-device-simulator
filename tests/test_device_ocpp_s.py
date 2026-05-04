import datetime
import math
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from charge_device_simulator.device.ocpp_s.device_ocpp_s import DeviceOcppS


class TestDeviceOcppSChargeMeterValue:
    """Tests for DeviceOcppS.charge_meter_value_current method.

    Now uses options dict pattern (like OCPP-J) instead of instance variables.
    """

    def test_meter_value_no_time_elapsed(self, device_ocpp_s, fixed_time):
        """Test meter value when no time has elapsed."""
        with patch.object(DeviceOcppS, 'utcnow', return_value=fixed_time):
            result = device_ocpp_s.charge_meter_value_current({
                "meterStart": 1000,
                "chargeStartTime": fixed_time.isoformat()
            })

        assert result == 1000

    def test_meter_value_after_one_minute(self, device_ocpp_s, fixed_time):
        """Test meter value after 1 minute at default rate (1 kWh/min)."""
        current_time = fixed_time + datetime.timedelta(minutes=1)

        with patch.object(DeviceOcppS, 'utcnow', return_value=current_time):
            result = device_ocpp_s.charge_meter_value_current({
                "meterStart": 1000,
                "chargeStartTime": fixed_time.isoformat()
            })

        # 1000 + (1 min * 1 kWh/min * 1000) = 2000
        assert result == 2000

    def test_meter_value_with_custom_charge_rate(self, device_ocpp_s, fixed_time):
        """Test meter value with custom chargedKwhPerMinute."""
        current_time = fixed_time + datetime.timedelta(minutes=2)

        with patch.object(DeviceOcppS, 'utcnow', return_value=current_time):
            result = device_ocpp_s.charge_meter_value_current({
                "meterStart": 1000,
                "chargeStartTime": fixed_time.isoformat(),
                "chargedKwhPerMinute": 0.5
            })

        # 1000 + (2 min * 0.5 kWh/min * 1000) = 2000
        assert result == 2000

    def test_progressive_meter_values(self, device_ocpp_s, fixed_time):
        """Test that progressive calls return increasing values."""
        options = {"meterStart": 1000, "chargedKwhPerMinute": 1}

        # First call - sets chargeStartTime
        with patch.object(DeviceOcppS, 'utcnow', return_value=fixed_time), \
             patch.object(DeviceOcppS, 'utcnow_iso', return_value=fixed_time.isoformat()):
            result1 = device_ocpp_s.charge_meter_value_current(options)

        assert result1 == 1000
        assert "chargeStartTime" in options

        results = [result1]
        for minutes in [1, 2, 3]:
            current_time = fixed_time + datetime.timedelta(minutes=minutes)
            with patch.object(DeviceOcppS, 'utcnow', return_value=current_time):
                results.append(device_ocpp_s.charge_meter_value_current(options))

        assert results == [1000, 2000, 3000, 4000]

    def test_result_is_floored(self, device_ocpp_s, fixed_time):
        """Test that result is floored to integer."""
        current_time = fixed_time + datetime.timedelta(seconds=45)  # 45 seconds = 0.75 min

        with patch.object(DeviceOcppS, 'utcnow', return_value=current_time):
            result = device_ocpp_s.charge_meter_value_current({
                "meterStart": 1000,
                "chargeStartTime": fixed_time.isoformat(),
                "chargedKwhPerMinute": 0.33
            })

        expected = math.floor(1000 + (0.75 * 0.33 * 1000))
        assert result == expected

    def test_fills_missing_options(self, device_ocpp_s, fixed_time):
        """Test that fill_missing_options_charge_start is called and defaults are used."""
        with patch.object(DeviceOcppS, 'utcnow', return_value=fixed_time), \
             patch.object(DeviceOcppS, 'utcnow_iso', return_value=fixed_time.isoformat()):
            # Call with empty options dict - should use defaults
            result = device_ocpp_s.charge_meter_value_current({})

        # With defaults: meterStart=1000, chargeStartTime=now, no elapsed time
        # Result should be 1000
        assert result == 1000


class TestDeviceOcppSOptionsPersistence:
    """Tests to verify that options dict modifications persist to caller."""

    def test_fill_missing_options_charge_start_persists(self, device_ocpp_s, fixed_time):
        """Test that fill_missing_options_charge_start modifies the original dict."""
        options = {}

        with patch.object(DeviceOcppS, 'utcnow_iso', return_value=fixed_time.isoformat()):
            device_ocpp_s.fill_missing_options_charge_start(options)

        # Verify the options dict was modified
        assert "chargeStartTime" in options
        assert options["chargeStartTime"] == fixed_time.isoformat()
        assert "meterStart" in options
        assert options["meterStart"] == 1000

    def test_fill_missing_options_charge_stop_persists(self, device_ocpp_s, fixed_time):
        """Test that fill_missing_options_charge_stop modifies the original dict."""
        options = {"meterStart": 1000, "chargeStartTime": fixed_time.isoformat()}

        with patch.object(DeviceOcppS, 'utcnow', return_value=fixed_time), \
             patch.object(DeviceOcppS, 'utcnow_iso', return_value=fixed_time.isoformat()):
            device_ocpp_s.fill_missing_options_charge_stop(options)

        # Verify meterStop was added
        assert "meterStop" in options
        assert "chargeStopTime" in options


def _seed_reservation(device, *, reservation_id=42, connector_id=1,
                      id_tag="RFID-A", parent_id_tag=None):
    device.reservation_set(
        reservation_id=reservation_id,
        connector_id=connector_id,
        id_tag=id_tag,
        parent_id_tag=parent_id_tag,
        expiry_date="2025-01-15T13:00:00+00:00",
    )


class TestOcppSAuthorizeStashesParent:
    @pytest.mark.asyncio
    async def test_parent_id_tag_extracted_from_nested_id_tag_info(self, device_ocpp_s):
        device_ocpp_s.by_device_req_send = AsyncMock(return_value={
            "status": "Accepted",
            "idTagInfo": {"status": "Accepted", "parentIdTag": "GROUP-X"},
        })

        ok = await device_ocpp_s.action_authorize({"idTag": "RFID-A"})

        assert ok is True
        assert device_ocpp_s._last_authorize_info["parent_id_tag"] == "GROUP-X"

    @pytest.mark.asyncio
    async def test_parent_id_tag_falls_back_to_top_level(self, device_ocpp_s):
        device_ocpp_s.by_device_req_send = AsyncMock(return_value={
            "status": "Accepted",
            "parentIdTag": "GROUP-Y",
        })

        await device_ocpp_s.action_authorize({"idTag": "RFID-B"})

        assert device_ocpp_s._last_authorize_info["parent_id_tag"] == "GROUP-Y"


class TestOcppSStartTransactionWithReservation:
    @pytest.mark.asyncio
    async def test_id_tag_match_includes_reservation_id_in_start(self, device_ocpp_s):
        _seed_reservation(device_ocpp_s, reservation_id=42, connector_id=1, id_tag="RFID-A")
        device_ocpp_s._last_authorize_info = {"id_tag": "RFID-A", "parent_id_tag": None}
        captured = {}

        async def fake_send(action, payload):
            captured[action] = payload
            return {"idTagInfo": {"status": "Accepted"}, "transactionId": 555}

        device_ocpp_s.by_device_req_send = AsyncMock(side_effect=fake_send)

        options = {"connectorId": 1, "idTag": "RFID-A"}
        assert device_ocpp_s._pre_charge_reservation_gate(options) is True
        assert await device_ocpp_s.action_charge_start(options) is True
        device_ocpp_s._consume_reservation_if_used(options)

        assert captured["StartTransaction"]["reservationId"] == 42
        assert not device_ocpp_s.reservation_is_active()

    @pytest.mark.asyncio
    async def test_parent_match_includes_reservation_id_in_start(self, device_ocpp_s):
        _seed_reservation(device_ocpp_s, reservation_id=43, connector_id=1,
                          id_tag="OWNER", parent_id_tag="GROUP-X")
        device_ocpp_s._last_authorize_info = {"id_tag": "FRIEND", "parent_id_tag": "GROUP-X"}
        captured = {}

        async def fake_send(action, payload):
            captured[action] = payload
            return {"idTagInfo": {"status": "Accepted"}, "transactionId": 556}

        device_ocpp_s.by_device_req_send = AsyncMock(side_effect=fake_send)

        options = {"connectorId": 1, "idTag": "FRIEND"}
        assert device_ocpp_s._pre_charge_reservation_gate(options) is True
        assert await device_ocpp_s.action_charge_start(options) is True

        assert captured["StartTransaction"]["reservationId"] == 43


class TestOcppSInboundReserveAndCancel:
    """Replaces flow_reserve / flow_reservation_cancel with plain Mocks and stubs
    run_with_delay so the background task is not actually scheduled — keeps these
    focused on the inbound response decision."""

    @pytest.mark.asyncio
    async def test_reserve_now_accepted_and_schedules_flow(self, device_ocpp_s):
        device_ocpp_s.flow_reserve = MagicMock()

        with patch("charge_device_simulator.device.utility.run_with_delay", return_value=None):
            resp = await device_ocpp_s.by_middleware_req("req1", "reservenow", {
                "reservationId": 7, "connectorId": 1, "idTag": "X",
                "expiryDate": "2025-01-15T13:00:00+00:00"
            })

        assert resp == {"status": "Accepted"}
        device_ocpp_s.flow_reserve.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_reservation_accepted_when_id_matches(self, device_ocpp_s):
        _seed_reservation(device_ocpp_s, reservation_id=42)
        device_ocpp_s.flow_reservation_cancel = MagicMock()

        with patch("charge_device_simulator.device.utility.run_with_delay", return_value=None):
            resp = await device_ocpp_s.by_middleware_req("req1", "cancelreservation",
                                                         {"reservationId": 42})

        assert resp == {"status": "Accepted"}
        device_ocpp_s.flow_reservation_cancel.assert_called_once_with(42)

    @pytest.mark.asyncio
    async def test_cancel_reservation_rejected_for_unknown_id(self, device_ocpp_s):
        _seed_reservation(device_ocpp_s, reservation_id=42)

        resp = await device_ocpp_s.by_middleware_req("req1", "cancelreservation",
                                                     {"reservationId": 999})

        assert resp == {"status": "Rejected"}


class TestOcppSFlowReserveStatusPayload:
    @pytest.mark.asyncio
    async def test_reserved_status_uses_status_field(self, device_ocpp_s):
        captured = {}

        async def fake_send(action, payload):
            captured[action] = payload
            return {}

        device_ocpp_s.by_device_req_send = AsyncMock(side_effect=fake_send)

        ok = await device_ocpp_s.flow_reserve({
            "reservationId": 5, "connectorId": 1, "idTag": "X"
        })

        assert ok is True
        assert captured["StatusNotification"]["status"] == "Reserved"
        assert captured["StatusNotification"]["connectorId"] == 1
