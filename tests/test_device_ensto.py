import datetime
from unittest.mock import patch

from charge_device_simulator.device.ensto.device_ensto import DeviceEnsto


class TestDeviceEnstoChargeMeterValue:
    """Tests for DeviceEnsto.charge_meter_value_current method.

    Now uses options dict pattern (like OCPP-J) instead of instance variables.
    """

    def test_meter_value_no_time_elapsed(self, device_ensto, fixed_time):
        """Test meter value when no time has elapsed."""
        with patch.object(DeviceEnsto, 'utcnow', return_value=fixed_time):
            result = device_ensto.charge_meter_value_current({
                "meterStart": 1000,
                "chargeStartTime": fixed_time.isoformat()
            })

        assert result == 1000

    def test_meter_value_after_one_minute(self, device_ensto, fixed_time):
        """Test meter value after 1 minute at default rate (1 kWh/min)."""
        current_time = fixed_time + datetime.timedelta(minutes=1)

        with patch.object(DeviceEnsto, 'utcnow', return_value=current_time):
            result = device_ensto.charge_meter_value_current({
                "meterStart": 1000,
                "chargeStartTime": fixed_time.isoformat()
            })

        # 1000 + (1 min * 1 kWh/min * 1000) = 2000
        assert result == 2000

    def test_progressive_meter_values(self, device_ensto, fixed_time):
        """Test that progressive calls return increasing values."""
        options = {"meterStart": 1000, "chargedKwhPerMinute": 1}

        # First call - sets chargeStartTime
        with patch.object(DeviceEnsto, 'utcnow', return_value=fixed_time), \
             patch.object(DeviceEnsto, 'utcnow_iso', return_value=fixed_time.isoformat()):
            result1 = device_ensto.charge_meter_value_current(options)

        assert result1 == 1000
        assert "chargeStartTime" in options

        results = [result1]
        for minutes in [1, 2, 3]:
            current_time = fixed_time + datetime.timedelta(minutes=minutes)
            with patch.object(DeviceEnsto, 'utcnow', return_value=current_time):
                results.append(device_ensto.charge_meter_value_current(options))

        assert results == [1000, 2000, 3000, 4000]


class TestDeviceEnstoPrepareAuthorizeParams:
    """Tests for DeviceEnsto.prepare_authorize_params method.

    This method modifies the json_payload dict by extracting values from options.
    """

    def test_extracts_rfid_from_options(self, device_ensto):
        """Test that rfid is extracted from options and added to json_payload."""
        json_payload = {"id": 10}
        options = {"rfid": "12345678"}

        device_ensto.prepare_authorize_params(json_payload, options)

        assert json_payload["rfid"] == "12345678"
        assert "rfid" in options  # NOT removed from options (using get, not pop)

    def test_extracts_idtag_when_no_rfid(self, device_ensto):
        """Test that idTag is extracted when rfid is not present."""
        json_payload = {"id": 10}
        options = {"idTag": "ABC123"}

        device_ensto.prepare_authorize_params(json_payload, options)

        assert json_payload["idtag"] == "ABC123"  # Note: lowercase 'idtag'
        assert "idTag" in options  # NOT removed from options (using get, not pop)

    def test_rfid_takes_precedence_over_idtag(self, device_ensto):
        """Test that rfid is used when both rfid and idTag are present."""
        json_payload = {"id": 10}
        options = {"rfid": "RFID123", "idTag": "TAG456"}

        device_ensto.prepare_authorize_params(json_payload, options)

        assert json_payload["rfid"] == "RFID123"
        assert "idtag" not in json_payload  # idTag not extracted
        assert "rfid" in options  # NOT removed (using get, not pop)
        assert "idTag" in options  # NOT removed (using get, not pop)

    def test_no_auth_params_when_empty_options(self, device_ensto):
        """Test behavior when options has neither rfid nor idTag."""
        json_payload = {"id": 10}
        options = {}

        device_ensto.prepare_authorize_params(json_payload, options)

        assert "rfid" not in json_payload
        assert "idtag" not in json_payload

    def test_options_dict_not_modified(self, device_ensto):
        """Test that the options dict is NOT modified (values NOT popped)."""
        json_payload = {}
        options = {"rfid": "TEST", "other_key": "value"}

        device_ensto.prepare_authorize_params(json_payload, options)

        # Both keys should remain in options (using get, not pop)
        assert "rfid" in options
        assert options["rfid"] == "TEST"
        assert options["other_key"] == "value"


class TestDeviceEnstoOptionsPersistence:
    """Tests to verify that options dict modifications persist to caller."""

    def test_fill_missing_options_charge_start_persists(self, device_ensto, fixed_time):
        """Test that fill_missing_options_charge_start modifies the original dict."""
        options = {}

        with patch.object(DeviceEnsto, 'utcnow_iso', return_value=fixed_time.isoformat()):
            device_ensto.fill_missing_options_charge_start(options)

        # Verify the options dict was modified
        assert "chargeStartTime" in options
        assert options["chargeStartTime"] == fixed_time.isoformat()
        assert "meterStart" in options
        assert options["meterStart"] == 1000

    def test_fill_missing_options_charge_stop_persists(self, device_ensto, fixed_time):
        """Test that fill_missing_options_charge_stop modifies the original dict."""
        options = {"meterStart": 1000, "chargeStartTime": fixed_time.isoformat()}

        with patch.object(DeviceEnsto, 'utcnow', return_value=fixed_time), \
             patch.object(DeviceEnsto, 'utcnow_iso', return_value=fixed_time.isoformat()):
            device_ensto.fill_missing_options_charge_stop(options)

        # Verify meterStop was added
        assert "meterStop" in options
        assert "chargeStopTime" in options
