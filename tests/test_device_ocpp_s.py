import datetime
import math
from unittest.mock import patch


class TestDeviceOcppSChargeMeterValue:
    """Tests for DeviceOcppS.charge_meter_value_current method.

    Unlike OCPP-J, OCPP-S uses instance variables (charge_start_time, charge_meter_start)
    instead of the options dict for tracking charge state.
    """

    def test_meter_value_no_time_elapsed(self, device_ocpp_s):
        """Test meter value when no time has elapsed."""
        start_time = datetime.datetime(2025, 1, 15, 12, 0, 0)
        device_ocpp_s.charge_start_time = start_time
        device_ocpp_s.charge_meter_start = 1000

        with patch('datetime.datetime') as mock_datetime:
            mock_datetime.utcnow.return_value = start_time
            result = device_ocpp_s.charge_meter_value_current({})

        assert result == 1000

    def test_meter_value_after_one_minute(self, device_ocpp_s):
        """Test meter value after 1 minute at default rate (1 kWh/min)."""
        start_time = datetime.datetime(2025, 1, 15, 12, 0, 0)
        current_time = datetime.datetime(2025, 1, 15, 12, 1, 0)
        device_ocpp_s.charge_start_time = start_time
        device_ocpp_s.charge_meter_start = 1000

        with patch('datetime.datetime') as mock_datetime:
            mock_datetime.utcnow.return_value = current_time
            result = device_ocpp_s.charge_meter_value_current({})

        # 1000 + (1 min * 1 kWh/min * 1000) = 2000
        assert result == 2000

    def test_meter_value_with_custom_charge_rate(self, device_ocpp_s):
        """Test meter value with custom chargedKwhPerMinute."""
        start_time = datetime.datetime(2025, 1, 15, 12, 0, 0)
        current_time = datetime.datetime(2025, 1, 15, 12, 2, 0)
        device_ocpp_s.charge_start_time = start_time
        device_ocpp_s.charge_meter_start = 1000

        with patch('datetime.datetime') as mock_datetime:
            mock_datetime.utcnow.return_value = current_time
            result = device_ocpp_s.charge_meter_value_current({"chargedKwhPerMinute": 0.5})

        # 1000 + (2 min * 0.5 kWh/min * 1000) = 2000
        assert result == 2000

    def test_progressive_meter_values(self, device_ocpp_s):
        """Test that progressive calls return increasing values."""
        start_time = datetime.datetime(2025, 1, 15, 12, 0, 0)
        device_ocpp_s.charge_start_time = start_time
        device_ocpp_s.charge_meter_start = 1000

        results = []
        for minutes in [0, 1, 2, 3]:
            current_time = start_time + datetime.timedelta(minutes=minutes)
            with patch('datetime.datetime') as mock_datetime:
                mock_datetime.utcnow.return_value = current_time
                results.append(device_ocpp_s.charge_meter_value_current({"chargedKwhPerMinute": 1}))

        assert results == [1000, 2000, 3000, 4000]

    def test_result_is_floored(self, device_ocpp_s):
        """Test that result is floored to integer."""
        start_time = datetime.datetime(2025, 1, 15, 12, 0, 0)
        current_time = datetime.datetime(2025, 1, 15, 12, 0, 45)  # 45 seconds = 0.75 min
        device_ocpp_s.charge_start_time = start_time
        device_ocpp_s.charge_meter_start = 1000

        with patch('datetime.datetime') as mock_datetime:
            mock_datetime.utcnow.return_value = current_time
            result = device_ocpp_s.charge_meter_value_current({"chargedKwhPerMinute": 0.33})

        expected = math.floor(1000 + (0.75 * 0.33 * 1000))
        assert result == expected

    def test_uses_instance_variables_not_options(self, device_ocpp_s):
        """Test that instance variables are used, not options dict."""
        start_time = datetime.datetime(2025, 1, 15, 12, 0, 0)
        current_time = datetime.datetime(2025, 1, 15, 12, 1, 0)

        # Set instance variables
        device_ocpp_s.charge_start_time = start_time
        device_ocpp_s.charge_meter_start = 5000

        # Options dict has no effect on meterStart (unlike OCPP-J)
        with patch('datetime.datetime') as mock_datetime:
            mock_datetime.utcnow.return_value = current_time
            result = device_ocpp_s.charge_meter_value_current({})

        # Uses instance var (5000), not default (1000)
        # 5000 + (1 min * 1 kWh/min * 1000) = 6000
        assert result == 6000
