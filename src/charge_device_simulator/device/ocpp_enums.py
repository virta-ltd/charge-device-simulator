"""Canonical OCPP enum value lists used by the interactive UI pickers.

Hand-coded per the official OCPP 1.6 / 2.0.1 specs and the OCPP 1.5 SOAP WSDL
(virta-ltd/charge-device-simulator/.../wsdl/server-201206.wsdl). Hand-coding
keeps these usable when no WSDL is available (OCPP-J) and avoids parsing at
runtime. If the spec adds a value, append it here — `select_from_list`
also accepts custom input as a fallback.
"""
import typing

# --- OCPP 1.6 (and structurally-identical OCPP-S 1.5/1.6 SOAP) -----------------

OCPP_16_CONNECTOR_STATUSES: typing.Tuple[str, ...] = (
    "Available",
    "Preparing",
    "Charging",
    "SuspendedEVSE",
    "SuspendedEV",
    "Finishing",
    "Reserved",
    "Unavailable",
    "Faulted",
)

OCPP_16_ERROR_CODES: typing.Tuple[str, ...] = (
    "ConnectorLockFailure",
    "EVCommunicationError",
    "GroundFailure",
    "HighTemperature",
    "InternalError",
    "LocalListConflict",
    "NoError",
    "OtherError",
    "OverCurrentFailure",
    "OverVoltage",
    "PowerMeterFailure",
    "PowerSwitchFailure",
    "ReaderFailure",
    "ResetFailure",
    "UnderVoltage",
    "WeakSignal",
)

OCPP_16_AVAILABILITY_TYPES: typing.Tuple[str, ...] = (
    "Inoperative",
    "Operative",
)

OCPP_16_RESET_TYPES: typing.Tuple[str, ...] = (
    "Hard",
    "Soft",
)

OCPP_16_CHARGING_PROFILE_PURPOSES: typing.Tuple[str, ...] = (
    "ChargePointMaxProfile",
    "TxDefaultProfile",
    "TxProfile",
)

# --- OCPP 2.0.1 ----------------------------------------------------------------

OCPP_201_CONNECTOR_STATUSES: typing.Tuple[str, ...] = (
    "Available",
    "Occupied",
    "Reserved",
    "Unavailable",
    "Faulted",
)

OCPP_201_ID_TOKEN_TYPES: typing.Tuple[str, ...] = (
    "Central",
    "eMAID",
    "ISO14443",
    "ISO15693",
    "KeyCode",
    "Local",
    "MacAddress",
    "NoAuthorization",
)

OCPP_201_RESET_TYPES: typing.Tuple[str, ...] = (
    "Immediate",
    "OnIdle",
)

# --- OCPP 1.5/1.6 SOAP (Authorize) ---------------------------------------------

OCPP_S_AUTHORIZATION_STATUSES: typing.Tuple[str, ...] = (
    "Accepted",
    "Blocked",
    "Expired",
    "Invalid",
    "ConcurrentTx",
)
