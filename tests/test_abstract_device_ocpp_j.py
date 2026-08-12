import asyncio
import datetime
import json
import math
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from charge_device_simulator.device.ocpp_j.abstract_device_ocpp_j import AbstractDeviceOcppJ


class TestChargeMeterValueCurrent:
    """Tests for the charge_meter_value_current method."""

    def test_with_explicit_values_no_time_elapsed(self, ocpp_j_device, fixed_time):
        """Test with explicit meterStart and chargeStartTime at current time."""
        with patch.object(AbstractDeviceOcppJ, 'utcnow', return_value=fixed_time):
            result = ocpp_j_device.charge_meter_value_current({
                "meterStart": 1000,
                "chargeStartTime": fixed_time.isoformat()
            })

        assert result == 1000

    def test_with_one_minute_elapsed(self, ocpp_j_device, fixed_time):
        """Test meter value after 1 minute of charging at default rate (1 kWh/min)."""
        current_time = fixed_time + datetime.timedelta(minutes=1)

        with patch.object(AbstractDeviceOcppJ, 'utcnow', return_value=current_time):
            result = ocpp_j_device.charge_meter_value_current({
                "meterStart": 1000,
                "chargeStartTime": fixed_time.isoformat()
            })

        # 1000 + (1 minute * 1 kWh/min * 1000) = 2000
        assert result == 2000

    def test_with_custom_charge_rate(self, ocpp_j_device, fixed_time):
        """Test meter value with custom chargedKwhPerMinute."""
        current_time = fixed_time + datetime.timedelta(minutes=1)

        with patch.object(AbstractDeviceOcppJ, 'utcnow', return_value=current_time):
            result = ocpp_j_device.charge_meter_value_current({
                "meterStart": 1000,
                "chargeStartTime": fixed_time.isoformat(),
                "chargedKwhPerMinute": 0.5
            })

        # 1000 + (1 minute * 0.5 kWh/min * 1000) = 1500
        assert result == 1500

    def test_with_30_seconds_elapsed(self, ocpp_j_device, fixed_time):
        """Test meter value after 30 seconds of charging."""
        current_time = fixed_time + datetime.timedelta(seconds=30)

        with patch.object(AbstractDeviceOcppJ, 'utcnow', return_value=current_time):
            result = ocpp_j_device.charge_meter_value_current({
                "meterStart": 1000,
                "chargeStartTime": fixed_time.isoformat()
            })

        # 1000 + (0.5 minute * 1 kWh/min * 1000) = 1500
        assert result == 1500

    def test_result_is_floored(self, ocpp_j_device, fixed_time):
        """Test that the result is floored (no decimals)."""
        # 45 seconds = 0.75 minutes
        current_time = fixed_time + datetime.timedelta(seconds=45)

        with patch.object(AbstractDeviceOcppJ, 'utcnow', return_value=current_time):
            result = ocpp_j_device.charge_meter_value_current({
                "meterStart": 1000,
                "chargeStartTime": fixed_time.isoformat(),
                "chargedKwhPerMinute": 0.33
            })

        # 1000 + (0.75 * 0.33 * 1000) = 1000 + 247.5 = 1247.5 -> floor = 1247
        expected = math.floor(1000 + (0.75 * 0.33 * 1000))
        assert result == expected

    def test_fills_missing_options(self, ocpp_j_device, fixed_time):
        """Test that fill_missing_options_charge_start is called and defaults are used."""
        with patch.object(AbstractDeviceOcppJ, 'utcnow', return_value=fixed_time), \
             patch.object(AbstractDeviceOcppJ, 'utcnow_iso', return_value=fixed_time.isoformat()):
            # Call with empty options dict - should use defaults
            result = ocpp_j_device.charge_meter_value_current({})

        # With defaults: meterStart=1000, chargeStartTime=now, no elapsed time
        # Result should be 1000
        assert result == 1000

    def test_progressive_calls_with_shared_options(self, ocpp_j_device, fixed_time, time_after_5_minutes):
        """Test two successive calls where chargeStartTime is auto-filled on first call and reused.

        With the fixed implementation, the options dict is now properly modified
        by charge_meter_value_current, so chargeStartTime persists across calls.
        """
        # Shared options dict - chargeStartTime will be filled by first call
        options = {"meterStart": 1000, "chargedKwhPerMinute": 1}

        # First call - chargeStartTime should be auto-filled
        with patch.object(AbstractDeviceOcppJ, 'utcnow', return_value=fixed_time), \
             patch.object(AbstractDeviceOcppJ, 'utcnow_iso', return_value=fixed_time.isoformat()):
            first_result = ocpp_j_device.charge_meter_value_current(options)

        # Verify chargeStartTime was added to options
        assert "chargeStartTime" in options
        assert options["chargeStartTime"] == fixed_time.isoformat()

        # First call: no elapsed time, should return meterStart
        assert first_result == 1000

        # Second call - 5 minutes later, same options dict (chargeStartTime preserved)
        # chargedKwhPerMinute should still be in options (not popped)
        with patch.object(AbstractDeviceOcppJ, 'utcnow', return_value=time_after_5_minutes):
            second_result = ocpp_j_device.charge_meter_value_current(options)

        # 1000 + (5 minutes * 1 kWh/min * 1000) = 6000 Wh
        assert second_result == 6000

        # Verify the meter value increased
        assert second_result > first_result


class TestOptionsPersistence:
    """Tests to verify that options dict modifications persist to caller."""

    def test_fill_missing_options_charge_start_persists(self, ocpp_j_device, fixed_time):
        """Test that fill_missing_options_charge_start modifies the original dict."""
        options = {}

        with patch.object(AbstractDeviceOcppJ, 'utcnow_iso', return_value=fixed_time.isoformat()):
            ocpp_j_device.fill_missing_options_charge_start(options)

        # Verify the options dict was modified
        assert "chargeStartTime" in options
        assert options["chargeStartTime"] == fixed_time.isoformat()
        assert "meterStart" in options
        assert options["meterStart"] == 1000

    def test_fill_missing_options_charge_stop_persists(self, ocpp_j_device, fixed_time):
        """Test that fill_missing_options_charge_stop modifies the original dict."""
        options = {"meterStart": 1000, "chargeStartTime": fixed_time.isoformat()}

        with patch.object(AbstractDeviceOcppJ, 'utcnow', return_value=fixed_time), \
             patch.object(AbstractDeviceOcppJ, 'utcnow_iso', return_value=fixed_time.isoformat()):
            ocpp_j_device.fill_missing_options_charge_stop(options)

        # Verify meterStop was added
        assert "meterStop" in options
        assert "chargeStopTime" in options

    def test_options_not_unpacked_creates_reference(self, ocpp_j_device, fixed_time):
        """Verify that options: dict signature allows modifications to persist.

        This test ensures the fix for **options unpacking is working correctly.
        Before the fix, modifications in called functions wouldn't persist.
        """
        # Create options without chargeStartTime
        original_options = {"meterStart": 2000}

        with patch.object(AbstractDeviceOcppJ, 'utcnow', return_value=fixed_time), \
             patch.object(AbstractDeviceOcppJ, 'utcnow_iso', return_value=fixed_time.isoformat()):
            # This calls fill_missing_options_charge_start internally
            result = ocpp_j_device.charge_meter_value_current(original_options)

        # The original_options dict should have been modified
        assert "chargeStartTime" in original_options
        assert original_options["chargeStartTime"] == fixed_time.isoformat()
        # meterStart should still be there
        assert original_options["meterStart"] == 2000

    def test_multiple_meter_value_calls_consistent(self, ocpp_j_device, fixed_time):
        """Test that multiple calls use consistent chargeStartTime."""
        time_1min = fixed_time + datetime.timedelta(minutes=1)
        time_2min = fixed_time + datetime.timedelta(minutes=2)
        time_3min = fixed_time + datetime.timedelta(minutes=3)

        options = {"meterStart": 1000, "chargedKwhPerMinute": 1}

        # First call at fixed_time - sets chargeStartTime
        with patch.object(AbstractDeviceOcppJ, 'utcnow', return_value=fixed_time), \
             patch.object(AbstractDeviceOcppJ, 'utcnow_iso', return_value=fixed_time.isoformat()):
            result1 = ocpp_j_device.charge_meter_value_current(options)

        stored_start_time = options["chargeStartTime"]
        assert result1 == 1000

        # Second call at 1 minute - chargedKwhPerMinute should still be in options
        with patch.object(AbstractDeviceOcppJ, 'utcnow', return_value=time_1min):
            result2 = ocpp_j_device.charge_meter_value_current(options)

        assert options["chargeStartTime"] == stored_start_time
        assert result2 == 2000

        # Third call at 2 minutes - chargedKwhPerMinute should still be in options
        with patch.object(AbstractDeviceOcppJ, 'utcnow', return_value=time_2min):
            result3 = ocpp_j_device.charge_meter_value_current(options)

        assert options["chargeStartTime"] == stored_start_time
        assert result3 == 3000

        # Fourth call at 3 minutes - chargedKwhPerMinute should still be in options
        with patch.object(AbstractDeviceOcppJ, 'utcnow', return_value=time_3min):
            result4 = ocpp_j_device.charge_meter_value_current(options)

        assert options["chargeStartTime"] == stored_start_time
        assert result4 == 4000

        # All results should be increasing
        assert result1 < result2 < result3 < result4


def _seed_reservation(device, *, reservation_id=42, connector_id=1,
                      id_tag="RFID-A", parent_id_tag=None,
                      expiry_date="2025-01-15T13:00:00+00:00"):
    device.reservation_set(
        reservation_id=reservation_id,
        connector_id=connector_id,
        id_tag=id_tag,
        parent_id_tag=parent_id_tag,
        expiry_date=expiry_date,
    )


class TestFlowReserve:
    @pytest.mark.asyncio
    async def test_accepted_stores_state_and_sends_reserved_status(self, ocpp_j_device):
        ocpp_j_device.action_status_update = AsyncMock(return_value=True)

        result = await ocpp_j_device.flow_reserve({
            "reservationId": 7,
            "connectorId": 2,
            "idTag": "RFID-A",
            "parentIdTag": "GROUP-X",
            "expiryDate": "2025-01-15T13:00:00+00:00",
        })

        assert result is True
        assert ocpp_j_device.reservation_id == 7
        assert ocpp_j_device.reservation_connector_id == 2
        assert ocpp_j_device.reservation_id_tag == "RFID-A"
        assert ocpp_j_device.reservation_parent_id_tag == "GROUP-X"
        ocpp_j_device.action_status_update.assert_awaited_once()
        assert ocpp_j_device.action_status_update.await_args.args[0] == "Reserved"

    @pytest.mark.asyncio
    async def test_rejected_when_charging(self, ocpp_j_device):
        ocpp_j_device.charge_in_progress = True
        ocpp_j_device.action_status_update = AsyncMock(return_value=True)

        result = await ocpp_j_device.flow_reserve({
            "reservationId": 7, "connectorId": 1, "idTag": "RFID-A"
        })

        assert result is False
        assert not ocpp_j_device.reservation_is_active()
        ocpp_j_device.action_status_update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_rejected_when_connector_already_reserved(self, ocpp_j_device):
        _seed_reservation(ocpp_j_device, reservation_id=1, connector_id=1)
        ocpp_j_device.action_status_update = AsyncMock(return_value=True)

        result = await ocpp_j_device.flow_reserve({
            "reservationId": 99, "connectorId": 1, "idTag": "OTHER"
        })

        assert result is False
        # Existing reservation untouched
        assert ocpp_j_device.reservation_id == 1
        ocpp_j_device.action_status_update.assert_not_awaited()


class TestFlowReservationCancel:
    @pytest.mark.asyncio
    async def test_accepted_clears_state_and_sends_available(self, ocpp_j_device):
        _seed_reservation(ocpp_j_device, reservation_id=42, connector_id=3)
        ocpp_j_device.action_status_update = AsyncMock(return_value=True)

        result = await ocpp_j_device.flow_reservation_cancel(42)

        assert result is True
        assert not ocpp_j_device.reservation_is_active()
        ocpp_j_device.action_status_update.assert_awaited_once()
        args = ocpp_j_device.action_status_update.await_args.args
        assert args[0] == "Available"
        assert args[1]["connectorId"] == 3

    @pytest.mark.asyncio
    async def test_rejected_for_unknown_id_keeps_state(self, ocpp_j_device):
        _seed_reservation(ocpp_j_device, reservation_id=42, connector_id=3)
        ocpp_j_device.action_status_update = AsyncMock(return_value=True)

        result = await ocpp_j_device.flow_reservation_cancel(999)

        assert result is False
        assert ocpp_j_device.reservation_id == 42
        ocpp_j_device.action_status_update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_explicit_options_are_passed_through_to_status_update(self, ocpp_j_device):
        _seed_reservation(ocpp_j_device, reservation_id=42, connector_id=3)
        ocpp_j_device.action_status_update = AsyncMock(return_value=True)

        result = await ocpp_j_device.flow_reservation_cancel(
            42, {"evseId": 7, "connectorId": 9})

        assert result is True
        passed = ocpp_j_device.action_status_update.await_args.args[1]
        # Caller-provided connectorId must be preserved (not overwritten by setdefault)
        assert passed["connectorId"] == 9
        assert passed["evseId"] == 7


class TestPreChargeReservationGate:
    def test_no_reservation_passes(self, ocpp_j_device):
        assert ocpp_j_device._pre_charge_reservation_gate({"connectorId": 1, "idTag": "X"}) is True

    def test_reservation_on_other_connector_does_not_apply(self, ocpp_j_device):
        _seed_reservation(ocpp_j_device, connector_id=2, id_tag="RES-TAG")
        options = {"connectorId": 1, "idTag": "OTHER"}

        assert ocpp_j_device._pre_charge_reservation_gate(options) is True
        assert "reservationId" not in options

    def test_id_tag_match_injects_reservation_id(self, ocpp_j_device):
        _seed_reservation(ocpp_j_device, reservation_id=11, connector_id=1, id_tag="RES-TAG")
        options = {"connectorId": 1, "idTag": "RES-TAG"}

        assert ocpp_j_device._pre_charge_reservation_gate(options) is True
        assert options["reservationId"] == 11

    def test_parent_match_injects_reservation_id(self, ocpp_j_device):
        _seed_reservation(ocpp_j_device, reservation_id=12, connector_id=1,
                          id_tag="OWNER", parent_id_tag="GROUP-X")
        ocpp_j_device._last_authorize_info = {"id_tag": "FRIEND", "parent_id_tag": "GROUP-X"}
        options = {"connectorId": 1, "idTag": "FRIEND"}

        assert ocpp_j_device._pre_charge_reservation_gate(options) is True
        assert options["reservationId"] == 12

    def test_no_match_blocks_charge(self, ocpp_j_device):
        _seed_reservation(ocpp_j_device, reservation_id=13, connector_id=1,
                          id_tag="OWNER", parent_id_tag="GROUP-X")
        ocpp_j_device._last_authorize_info = {"id_tag": "INTRUDER", "parent_id_tag": "GROUP-Y"}
        options = {"connectorId": 1, "idTag": "INTRUDER"}

        assert ocpp_j_device._pre_charge_reservation_gate(options) is False
        assert "reservationId" not in options

    def test_reservation_with_no_authorize_info_falls_through_to_id_tag_only(self, ocpp_j_device):
        _seed_reservation(ocpp_j_device, reservation_id=14, connector_id=1,
                          id_tag="OWNER", parent_id_tag="GROUP-X")
        ocpp_j_device._last_authorize_info = None
        options = {"connectorId": 1, "idTag": "INTRUDER"}

        assert ocpp_j_device._pre_charge_reservation_gate(options) is False

    def test_missing_connector_id_still_applies_gate_to_default_connector(self, ocpp_j_device):
        # Reservation is on connector 1; user's options omit connectorId.
        # Without the get-with-default, the gate would compare None vs 1 and
        # silently let the charge through.
        _seed_reservation(ocpp_j_device, reservation_id=15, connector_id=1,
                          id_tag="OWNER", parent_id_tag="GROUP-X")
        ocpp_j_device._last_authorize_info = {"id_tag": "INTRUDER", "parent_id_tag": "GROUP-Y"}
        options = {"idTag": "INTRUDER"}

        assert ocpp_j_device._pre_charge_reservation_gate(options) is False
        assert "reservationId" not in options

    def test_connector_zero_reservation_blocks_wrong_tag_on_any_connector(self, ocpp_j_device):
        # OCPP 1.6: connectorId 0 in ReserveNow reserves the charge point as
        # a whole, so the gate must apply it to whichever connector the
        # charge requests.
        _seed_reservation(ocpp_j_device, reservation_id=20, connector_id=0, id_tag="OWNER")
        options = {"connectorId": 1, "idTag": "INTRUDER"}

        assert ocpp_j_device._pre_charge_reservation_gate(options) is False
        assert "reservationId" not in options

    def test_connector_zero_reservation_blocks_wrong_tag_when_connector_id_missing(self, ocpp_j_device):
        _seed_reservation(ocpp_j_device, reservation_id=21, connector_id=0, id_tag="OWNER")
        options = {"idTag": "INTRUDER"}

        assert ocpp_j_device._pre_charge_reservation_gate(options) is False
        assert "reservationId" not in options

    def test_connector_zero_reservation_matching_tag_injects_reservation_id(self, ocpp_j_device):
        _seed_reservation(ocpp_j_device, reservation_id=22, connector_id=0, id_tag="OWNER")
        options = {"connectorId": 1, "idTag": "OWNER"}

        assert ocpp_j_device._pre_charge_reservation_gate(options) is True
        assert options["reservationId"] == 22
        # The requested connector still goes out in the start payload; the
        # gate must not rewrite it to the reservation's connector 0.
        assert options["connectorId"] == 1


class TestConsumeReservationIfUsed:
    def test_clears_when_reservation_id_in_options_matches(self, ocpp_j_device):
        _seed_reservation(ocpp_j_device, reservation_id=99)
        options = {"reservationId": 99}

        ocpp_j_device._consume_reservation_if_used(options)

        assert not ocpp_j_device.reservation_is_active()

    def test_keeps_state_when_no_reservation_id_in_options(self, ocpp_j_device):
        _seed_reservation(ocpp_j_device, reservation_id=99)
        ocpp_j_device._consume_reservation_if_used({})
        assert ocpp_j_device.reservation_id == 99

    def test_does_not_clear_when_reservation_ids_mismatch(self, ocpp_j_device):
        _seed_reservation(ocpp_j_device, reservation_id=99)
        ocpp_j_device._consume_reservation_if_used({"reservationId": 100})
        assert ocpp_j_device.reservation_id == 99


class TestResetChargeCycleOptions:
    """Every `flow_charge` invocation must start a fresh cycle: replaying the
    previous cycle's start/stop time or meterStop produces overlapping
    transactions whose stop reading contradicts the periodic meter values."""

    def _stale_options(self):
        return {
            "idTag": "ABC",
            "connectorId": 1,
            "chargeStartTime": "2025-01-15T12:00:00+00:00",
            "chargeStopTime": "2025-01-15T12:30:00+00:00",
            "meterStop": 31000,
            "meterStart": 1000,
        }

    def test_drops_stale_charge_cycle_keys(self, ocpp_j_device):
        options = self._stale_options()

        ocpp_j_device._reset_charge_cycle_options(options)

        assert "chargeStartTime" not in options
        assert "chargeStopTime" not in options
        assert "meterStop" not in options
        assert options["idTag"] == "ABC"
        assert options["connectorId"] == 1

    def test_carries_previous_meter_stop_into_meter_start(self, ocpp_j_device):
        """The energy register never rewinds between sessions on real hardware."""
        options = self._stale_options()

        ocpp_j_device._reset_charge_cycle_options(options)

        assert options["meterStart"] == 31000

    def test_keeps_meter_start_on_first_cycle(self, ocpp_j_device):
        """No previous cycle (no meterStop) leaves the configured start alone."""
        options = {"idTag": "ABC", "connectorId": 1, "meterStart": 1000}

        ocpp_j_device._reset_charge_cycle_options(options)

        assert options == {"idTag": "ABC", "connectorId": 1, "meterStart": 1000}

    def test_drops_gate_injected_reservation_id(self, ocpp_j_device):
        """reservationId is per-cycle state injected by the reservation gate;
        replaying it would attach an already-consumed reservation to the next
        StartTransaction."""
        options = {"idTag": "ABC", "reservationId": 7}

        ocpp_j_device._reset_charge_cycle_options(options)

        assert "reservationId" not in options

    def test_scripted_meter_values_keep_configured_meter_start(self, ocpp_j_device):
        """Scripted registers are absolute and replay identically each cycle;
        carrying the previous stop into meterStart would put it above the
        replayed samples — a register rewind."""
        options = {
            "meterStart": 1000,
            "meterStop": 2000,
            "meterValues": [
                {"meterValue": 1500, "timestamp": "t1", "secondsToSleep": 0},
                {"meterValue": 2000, "timestamp": "t2", "secondsToSleep": 0},
            ],
        }

        ocpp_j_device._reset_charge_cycle_options(options)

        assert options["meterStart"] == 1000
        assert "meterStop" not in options


class TestScriptedMeterValuesStopReading:
    """The stop reading must repeat the script's final register value; a
    wall-clock-computed meterStop contradicts the samples already sent and
    makes the session unbillable."""

    def test_meter_stop_defaults_to_last_scripted_value(self, ocpp_j_device):
        options = {
            "meterStart": 1000,
            "chargeStartTime": "2025-01-15T12:00:00+00:00",
            "meterValues": [
                {"meterValue": 1500, "timestamp": "t1", "secondsToSleep": 0},
                {"meterValue": 2000, "timestamp": "t2", "secondsToSleep": 0},
            ],
        }

        ocpp_j_device.fill_missing_options_charge_stop(options)

        assert options["meterStop"] == 2000

    def test_explicit_meter_stop_still_wins_over_script(self, ocpp_j_device):
        options = {
            "meterStop": 9999,
            "chargeStopTime": "2025-01-15T12:30:00+00:00",
            "meterValues": [
                {"meterValue": 2000, "timestamp": "t", "secondsToSleep": 0},
            ],
        }

        ocpp_j_device.fill_missing_options_charge_stop(options)

        assert options["meterStop"] == 9999


class TestInteractiveReservationHandlers:
    @pytest.mark.asyncio
    async def test_show_state_does_not_invoke_flows(self, ocpp_j_device):
        _seed_reservation(ocpp_j_device, reservation_id=42)
        ocpp_j_device.flow_reserve = AsyncMock()
        ocpp_j_device.flow_reservation_cancel = AsyncMock()

        await ocpp_j_device.interactive_reservation_show()

        ocpp_j_device.flow_reserve.assert_not_awaited()
        ocpp_j_device.flow_reservation_cancel.assert_not_awaited()
        assert ocpp_j_device.reservation_id == 42

    @pytest.mark.asyncio
    async def test_make_reservation_collects_inputs_and_invokes_flow(self, ocpp_j_device):
        ocpp_j_device.flow_reserve = AsyncMock(return_value=True)
        with patch("aioconsole.ainput", new_callable=AsyncMock) as mock_input, \
             patch("charge_device_simulator.device.utility._is_tty", return_value=False):
            mock_input.side_effect = [
                "55",                 # reservationId
                "2",                  # connectorId
                "RFID-A",             # idTag
                "GROUP-X",            # parentIdTag
                "2025-01-15T13:00:00+00:00",  # expiryDate
            ]
            await ocpp_j_device.interactive_reservation_make()

        passed_options = ocpp_j_device.flow_reserve.await_args.args[0]
        assert passed_options["reservationId"] == 55
        assert passed_options["connectorId"] == 2
        assert passed_options["evseId"] == 2
        assert passed_options["idTag"] == "RFID-A"
        assert passed_options["parentIdTag"] == "GROUP-X"
        assert passed_options["expiryDate"] == "2025-01-15T13:00:00+00:00"

    @pytest.mark.asyncio
    async def test_make_reservation_blank_parent_and_expiry_use_defaults(self, ocpp_j_device):
        ocpp_j_device.flow_reserve = AsyncMock(return_value=True)
        with patch("aioconsole.ainput", new_callable=AsyncMock) as mock_input, \
             patch("charge_device_simulator.device.utility._is_tty", return_value=False):
            mock_input.side_effect = ["10", "1", "X", "", ""]
            await ocpp_j_device.interactive_reservation_make()

        passed_options = ocpp_j_device.flow_reserve.await_args.args[0]
        assert passed_options["parentIdTag"] is None
        # Blank expiry → ISO timestamp (defaulted now+1h)
        assert "T" in passed_options["expiryDate"]

    @pytest.mark.asyncio
    async def test_cancel_reservation_blank_uses_stored_id(self, ocpp_j_device):
        _seed_reservation(ocpp_j_device, reservation_id=42)
        ocpp_j_device.flow_reservation_cancel = AsyncMock(return_value=True)

        with patch("aioconsole.ainput", new_callable=AsyncMock) as mock_input, \
             patch("charge_device_simulator.device.utility._is_tty", return_value=False):
            mock_input.side_effect = [""]
            await ocpp_j_device.interactive_reservation_cancel()

        ocpp_j_device.flow_reservation_cancel.assert_awaited_once_with(42)

    @pytest.mark.asyncio
    async def test_cancel_reservation_uses_explicit_id(self, ocpp_j_device):
        _seed_reservation(ocpp_j_device, reservation_id=42)
        ocpp_j_device.flow_reservation_cancel = AsyncMock(return_value=True)

        with patch("aioconsole.ainput", new_callable=AsyncMock) as mock_input, \
             patch("charge_device_simulator.device.utility._is_tty", return_value=False):
            mock_input.side_effect = ["999"]
            await ocpp_j_device.interactive_reservation_cancel()

        ocpp_j_device.flow_reservation_cancel.assert_awaited_once_with(999)


class TestCallErrorAndTimeoutAreFailures:
    """A CALLERROR (message type 4) used to fall through to the "Type Unknown"
    branch, leaving the request to time out; the timeout in turn returned a
    truthy string, so actions that only check `is None` logged success for
    messages the middleware had rejected."""

    def _pending(self, device):
        return device._AbstractDeviceOcppJ__pending_by_device_reqs

    async def _run_with_inbound(self, device, frame_for):
        """Send one request while a reader loop answers it with `frame_for(req_id)`."""
        device.response_timeout_seconds = 5
        sent = asyncio.Event()
        device._ws = MagicMock()
        device._ws.send = AsyncMock(side_effect=lambda raw: sent.set())

        answered = False

        async def fake_recv():
            nonlocal answered
            await sent.wait()
            if answered:
                await asyncio.Event().wait()  # nothing more to deliver
            answered = True
            return frame_for(next(iter(self._pending(device))))

        device._ws.recv = AsyncMock(side_effect=fake_recv)
        loop_task = asyncio.create_task(
            device._AbstractDeviceOcppJ__loop_internal())
        try:
            return await device.by_device_req_send("Heartbeat", {})
        finally:
            loop_task.cancel()

    @pytest.mark.asyncio
    async def test_call_error_resolves_request_as_none(self, ocpp_j_device):
        result = await self._run_with_inbound(
            ocpp_j_device,
            lambda req_id: json.dumps(
                [4, req_id, "SecurityError", "Rejected by CSMS", {}]),
        )

        assert result is None
        # The pending entry is cleared, not left to leak until timeout
        assert self._pending(ocpp_j_device) == {}

    @pytest.mark.asyncio
    async def test_call_result_still_resolves_normally(self, ocpp_j_device):
        result = await self._run_with_inbound(
            ocpp_j_device,
            lambda req_id: json.dumps([3, req_id, {"currentTime": "now"}]),
        )

        assert result is not None
        assert result[2] == {"currentTime": "now"}

    @pytest.mark.asyncio
    async def test_timeout_returns_none(self, ocpp_j_device):
        ocpp_j_device.response_timeout_seconds = 0
        ocpp_j_device._ws = MagicMock()
        ocpp_j_device._ws.send = AsyncMock()

        assert await ocpp_j_device.by_device_req_send("Heartbeat", {}) is None
        # The timed-out request must not leak its pending entry: a late reply
        # would find it and resolve a future wait_for already cancelled.
        assert self._pending(ocpp_j_device) == {}

    @pytest.mark.asyncio
    async def test_late_reply_after_timeout_does_not_kill_read_loop(self, ocpp_j_device):
        """A CALLRESULT/CALLERROR landing after the timeout is an orphan;
        resolving the cancelled future instead raised InvalidStateError inside
        the read loop, silently killing it while the socket stayed open."""
        ocpp_j_device.response_timeout_seconds = 0
        sent_frames = []
        ocpp_j_device._ws = MagicMock()
        ocpp_j_device._ws.send = AsyncMock(side_effect=lambda raw: sent_frames.append(raw))

        assert await ocpp_j_device.by_device_req_send("Heartbeat", {}) is None
        req_id = json.loads(sent_frames[0])[1]

        drained = asyncio.Event()
        late_frames = [
            json.dumps([3, req_id, {"currentTime": "now"}]),
            json.dumps([4, req_id, "GenericError", "late rejection", {}]),
        ]

        async def fake_recv():
            if late_frames:
                return late_frames.pop(0)
            drained.set()
            await asyncio.Event().wait()  # nothing more to deliver

        ocpp_j_device._ws.recv = AsyncMock(side_effect=fake_recv)
        loop_task = asyncio.create_task(
            ocpp_j_device._AbstractDeviceOcppJ__loop_internal())
        try:
            await asyncio.wait_for(drained.wait(), timeout=2)
            assert not loop_task.done()
        finally:
            loop_task.cancel()

    @pytest.mark.asyncio
    async def test_meter_values_reports_failure_on_timeout(self, device_ocpp_j16):
        """The action must not log success for an unanswered request."""
        device_ocpp_j16.response_timeout_seconds = 0

        ok = await device_ocpp_j16.action_meter_value({"connectorId": 1}, meter_value=100)

        assert ok is False

    @pytest.mark.asyncio
    async def test_status_notification_reports_failure_on_timeout(self, device_ocpp_j16):
        device_ocpp_j16.response_timeout_seconds = 0

        ok = await device_ocpp_j16.action_status_update("Charging", {"connectorId": 1})

        assert ok is False


class TestInboundReserveNowCancelReservation:
    """Tests for the by_middleware_req routing of ReserveNow / CancelReservation.

    The inbound handler schedules flow_reserve / flow_reservation_cancel via
    asyncio.create_task with a delay. We replace those methods with plain
    Mocks (not AsyncMock) and stub run_with_delay so no background coroutine
    is created — keeping these tests focused on the response payload only."""

    @pytest.mark.asyncio
    async def test_reserve_now_accepted_when_idle(self, ocpp_j_device):
        ocpp_j_device.by_middleware_req_response_ready = AsyncMock()
        ocpp_j_device.flow_reserve = MagicMock()

        with patch("charge_device_simulator.device.utility.run_with_delay", return_value=None):
            await ocpp_j_device.by_middleware_req("req1", "reservenow", {
                "reservationId": 1, "connectorId": 1, "idTag": "X",
                "expiryDate": "2025-01-15T13:00:00+00:00"
            })

        resp = ocpp_j_device.by_middleware_req_response_ready.await_args.args[1]
        assert resp == {"status": "Accepted"}
        ocpp_j_device.flow_reserve.assert_called_once()

    @pytest.mark.asyncio
    async def test_reserve_now_rejected_when_connector_id_missing(self, ocpp_j_device):
        ocpp_j_device.by_middleware_req_response_ready = AsyncMock()

        await ocpp_j_device.by_middleware_req("req1", "reservenow", {
            "reservationId": 1, "idTag": "X"  # connectorId missing — required in 1.6
        })

        resp = ocpp_j_device.by_middleware_req_response_ready.await_args.args[1]
        assert resp == {"status": "Rejected"}

    @pytest.mark.asyncio
    async def test_reserve_now_occupied_when_already_reserved(self, ocpp_j_device):
        _seed_reservation(ocpp_j_device, connector_id=1)
        ocpp_j_device.by_middleware_req_response_ready = AsyncMock()

        await ocpp_j_device.by_middleware_req("req1", "reservenow", {
            "reservationId": 2, "connectorId": 1, "idTag": "Y"
        })

        resp = ocpp_j_device.by_middleware_req_response_ready.await_args.args[1]
        assert resp == {"status": "Occupied"}

    @pytest.mark.asyncio
    async def test_cancel_reservation_accepted_when_id_matches(self, ocpp_j_device):
        _seed_reservation(ocpp_j_device, reservation_id=42)
        ocpp_j_device.by_middleware_req_response_ready = AsyncMock()
        ocpp_j_device.flow_reservation_cancel = MagicMock()

        with patch("charge_device_simulator.device.utility.run_with_delay", return_value=None):
            await ocpp_j_device.by_middleware_req("req1", "cancelreservation",
                                                  {"reservationId": 42})

        resp = ocpp_j_device.by_middleware_req_response_ready.await_args.args[1]
        assert resp == {"status": "Accepted"}
        ocpp_j_device.flow_reservation_cancel.assert_called_once_with(42)

    @pytest.mark.asyncio
    async def test_cancel_reservation_rejected_for_unknown_id(self, ocpp_j_device):
        _seed_reservation(ocpp_j_device, reservation_id=42)
        ocpp_j_device.by_middleware_req_response_ready = AsyncMock()

        await ocpp_j_device.by_middleware_req("req1", "cancelreservation",
                                              {"reservationId": 999})

        resp = ocpp_j_device.by_middleware_req_response_ready.await_args.args[1]
        assert resp == {"status": "Rejected"}
