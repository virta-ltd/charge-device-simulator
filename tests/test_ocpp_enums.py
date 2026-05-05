from charge_device_simulator.device import ocpp_enums


def _all_tuple_constants():
    return [
        ("OCPP_16_CONNECTOR_STATUSES", ocpp_enums.OCPP_16_CONNECTOR_STATUSES),
        ("OCPP_16_ERROR_CODES", ocpp_enums.OCPP_16_ERROR_CODES),
        ("OCPP_16_AVAILABILITY_TYPES", ocpp_enums.OCPP_16_AVAILABILITY_TYPES),
        ("OCPP_16_RESET_TYPES", ocpp_enums.OCPP_16_RESET_TYPES),
        ("OCPP_16_CHARGING_PROFILE_PURPOSES", ocpp_enums.OCPP_16_CHARGING_PROFILE_PURPOSES),
        ("OCPP_201_CONNECTOR_STATUSES", ocpp_enums.OCPP_201_CONNECTOR_STATUSES),
        ("OCPP_201_ID_TOKEN_TYPES", ocpp_enums.OCPP_201_ID_TOKEN_TYPES),
        ("OCPP_201_RESET_TYPES", ocpp_enums.OCPP_201_RESET_TYPES),
        ("OCPP_S_AUTHORIZATION_STATUSES", ocpp_enums.OCPP_S_AUTHORIZATION_STATUSES),
    ]


class TestEnumConstants:
    def test_each_constant_is_non_empty_tuple_with_no_duplicates(self):
        for name, values in _all_tuple_constants():
            assert isinstance(values, tuple), f"{name} must be a tuple"
            assert len(values) > 0, f"{name} must be non-empty"
            assert len(set(values)) == len(values), f"{name} contains duplicates"
            assert all(isinstance(v, str) for v in values), f"{name} must contain strings"

    def test_canonical_spec_values_present(self):
        # Spot-checks for values the wiring relies on
        assert "NoError" in ocpp_enums.OCPP_16_ERROR_CODES
        assert "SuspendedEVSE" in ocpp_enums.OCPP_16_CONNECTOR_STATUSES
        assert "SuspendedEV" in ocpp_enums.OCPP_16_CONNECTOR_STATUSES
        assert "Reserved" in ocpp_enums.OCPP_16_CONNECTOR_STATUSES
        assert "Occupied" in ocpp_enums.OCPP_201_CONNECTOR_STATUSES
        assert "ISO14443" in ocpp_enums.OCPP_201_ID_TOKEN_TYPES
        assert "ConcurrentTx" in ocpp_enums.OCPP_S_AUTHORIZATION_STATUSES
