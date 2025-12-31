import datetime
from unittest.mock import patch


class TestDeviceEnstoChargeMeterValue:
    """Tests for DeviceEnsto.charge_meter_value_current method.

    Like OCPP-S, Ensto uses instance variables (charge_start_time, charge_meter_start)
    instead of the options dict for tracking charge state.
    """

    def test_meter_value_no_time_elapsed(self, device_ensto):
        """Test meter value when no time has elapsed."""
        start_time = datetime.datetime(2025, 1, 15, 12, 0, 0)
        device_ensto.charge_start_time = start_time
        device_ensto.charge_meter_start = 1000

        with patch('datetime.datetime') as mock_datetime:
            mock_datetime.utcnow.return_value = start_time
            result = device_ensto.charge_meter_value_current({})

        assert result == 1000

    def test_meter_value_after_one_minute(self, device_ensto):
        """Test meter value after 1 minute at default rate (1 kWh/min)."""
        start_time = datetime.datetime(2025, 1, 15, 12, 0, 0)
        current_time = datetime.datetime(2025, 1, 15, 12, 1, 0)
        device_ensto.charge_start_time = start_time
        device_ensto.charge_meter_start = 1000

        with patch('datetime.datetime') as mock_datetime:
            mock_datetime.utcnow.return_value = current_time
            result = device_ensto.charge_meter_value_current({})

        # 1000 + (1 min * 1 kWh/min * 1000) = 2000
        assert result == 2000

    def test_progressive_meter_values(self, device_ensto):
        """Test that progressive calls return increasing values."""
        start_time = datetime.datetime(2025, 1, 15, 12, 0, 0)
        device_ensto.charge_start_time = start_time
        device_ensto.charge_meter_start = 1000

        results = []
        for minutes in [0, 1, 2, 3]:
            current_time = start_time + datetime.timedelta(minutes=minutes)
            with patch('datetime.datetime') as mock_datetime:
                mock_datetime.utcnow.return_value = current_time
                results.append(device_ensto.charge_meter_value_current({"chargedKwhPerMinute": 1}))

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
        assert "rfid" not in options  # popped from options

    def test_extracts_idtag_when_no_rfid(self, device_ensto):
        """Test that idTag is extracted when rfid is not present."""
        json_payload = {"id": 10}
        options = {"idTag": "ABC123"}

        device_ensto.prepare_authorize_params(json_payload, options)

        assert json_payload["idtag"] == "ABC123"  # Note: lowercase 'idtag'
        assert "idTag" not in options  # popped from options

    def test_rfid_takes_precedence_over_idtag(self, device_ensto):
        """Test that rfid is used when both rfid and idTag are present."""
        json_payload = {"id": 10}
        options = {"rfid": "RFID123", "idTag": "TAG456"}

        device_ensto.prepare_authorize_params(json_payload, options)

        assert json_payload["rfid"] == "RFID123"
        assert "idtag" not in json_payload  # idTag not extracted
        assert "rfid" not in options  # popped
        assert "idTag" in options  # NOT popped (rfid took precedence)

    def test_no_auth_params_when_empty_options(self, device_ensto):
        """Test behavior when options has neither rfid nor idTag."""
        json_payload = {"id": 10}
        options = {}

        device_ensto.prepare_authorize_params(json_payload, options)

        assert "rfid" not in json_payload
        assert "idtag" not in json_payload

    def test_options_dict_is_modified(self, device_ensto):
        """Test that the options dict is modified (values popped)."""
        json_payload = {}
        original_options = {"rfid": "TEST", "other_key": "value"}
        options = original_options.copy()
        options = {"rfid": "TEST", "other_key": "value"}

        device_ensto.prepare_authorize_params(json_payload, options)

        # rfid should be removed, other_key should remain
        assert "rfid" not in options
        assert options["other_key"] == "value"
