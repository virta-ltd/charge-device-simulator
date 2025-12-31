import datetime
import math
from unittest.mock import patch

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
