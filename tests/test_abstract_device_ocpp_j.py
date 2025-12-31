import datetime
import math
from unittest.mock import patch

from device.ocpp_j.abstract_device_ocpp_j import AbstractDeviceOcppJ


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
        # Re-add chargedKwhPerMinute since it gets popped
        options["chargedKwhPerMinute"] = 1
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

        # Second call at 1 minute
        options["chargedKwhPerMinute"] = 1
        with patch.object(AbstractDeviceOcppJ, 'utcnow', return_value=time_1min):
            result2 = ocpp_j_device.charge_meter_value_current(options)

        assert options["chargeStartTime"] == stored_start_time
        assert result2 == 2000

        # Third call at 2 minutes
        options["chargedKwhPerMinute"] = 1
        with patch.object(AbstractDeviceOcppJ, 'utcnow', return_value=time_2min):
            result3 = ocpp_j_device.charge_meter_value_current(options)

        assert options["chargeStartTime"] == stored_start_time
        assert result3 == 3000

        # Fourth call at 3 minutes
        options["chargedKwhPerMinute"] = 1
        with patch.object(AbstractDeviceOcppJ, 'utcnow', return_value=time_3min):
            result4 = ocpp_j_device.charge_meter_value_current(options)

        assert options["chargeStartTime"] == stored_start_time
        assert result4 == 4000

        # All results should be increasing
        assert result1 < result2 < result3 < result4
