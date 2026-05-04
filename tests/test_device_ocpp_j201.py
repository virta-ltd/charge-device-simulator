from unittest.mock import AsyncMock

import pytest


def _stub_authorize_response(id_tag: str, group_id_tag: str = None):
    info = {"status": "Accepted"}
    if group_id_tag is not None:
        info["groupIdToken"] = {"idToken": group_id_tag, "type": "Central"}
    return [3, "req-1", {"idTokenInfo": info}]


def _stub_transaction_event_response():
    return [3, "req-1", {"idTokenInfo": {"status": "Accepted"}}]


def _seed_reservation(device, *, reservation_id=42, connector_id=1,
                      id_tag="RFID-A", parent_id_tag=None):
    device.reservation_set(
        reservation_id=reservation_id,
        connector_id=connector_id,
        id_tag=id_tag,
        parent_id_tag=parent_id_tag,
        expiry_date="2025-01-15T13:00:00+00:00",
    )


class TestJ201AuthorizeStashesGroup:
    @pytest.mark.asyncio
    async def test_group_id_token_captured_from_response(self, device_ocpp_j201):
        device_ocpp_j201.by_device_req_send = AsyncMock(
            return_value=_stub_authorize_response("RFID-A", group_id_tag="GROUP-X"))

        ok = await device_ocpp_j201.action_authorize({"idTag": "RFID-A"})

        assert ok is True
        assert device_ocpp_j201._last_authorize_info["parent_id_tag"] == "GROUP-X"

    @pytest.mark.asyncio
    async def test_no_group_id_token_yields_none_parent(self, device_ocpp_j201):
        device_ocpp_j201.by_device_req_send = AsyncMock(
            return_value=_stub_authorize_response("RFID-A"))

        await device_ocpp_j201.action_authorize({"idTag": "RFID-A"})

        assert device_ocpp_j201._last_authorize_info["parent_id_tag"] is None


class TestJ201TransactionEventWithReservation:
    @pytest.mark.asyncio
    async def test_id_tag_match_includes_reservation_id_at_top_level(self, device_ocpp_j201):
        _seed_reservation(device_ocpp_j201, reservation_id=77, connector_id=1, id_tag="RFID-A")
        device_ocpp_j201._last_authorize_info = {"id_tag": "RFID-A", "parent_id_tag": None}
        captured = {}

        async def fake_send(action, payload):
            captured[action] = payload
            return _stub_transaction_event_response()

        device_ocpp_j201.by_device_req_send = AsyncMock(side_effect=fake_send)

        options = {"connectorId": 1, "idTag": "RFID-A"}
        assert device_ocpp_j201._pre_charge_reservation_gate(options) is True
        assert await device_ocpp_j201.action_charge_start(options) is True
        device_ocpp_j201._consume_reservation_if_used(options)

        assert captured["TransactionEvent"]["reservationId"] == 77
        # reservationId is at the top level of TransactionEvent in 2.0.1, not inside transactionInfo
        assert "reservationId" not in captured["TransactionEvent"]["transactionInfo"]
        assert not device_ocpp_j201.reservation_is_active()

    @pytest.mark.asyncio
    async def test_group_match_includes_reservation_id(self, device_ocpp_j201):
        _seed_reservation(device_ocpp_j201, reservation_id=78, connector_id=1,
                          id_tag="OWNER", parent_id_tag="GROUP-X")
        device_ocpp_j201._last_authorize_info = {"id_tag": "FRIEND", "parent_id_tag": "GROUP-X"}
        captured = {}

        async def fake_send(action, payload):
            captured[action] = payload
            return _stub_transaction_event_response()

        device_ocpp_j201.by_device_req_send = AsyncMock(side_effect=fake_send)

        options = {"connectorId": 1, "idTag": "FRIEND"}
        assert device_ocpp_j201._pre_charge_reservation_gate(options) is True
        assert await device_ocpp_j201.action_charge_start(options) is True

        assert captured["TransactionEvent"]["reservationId"] == 78

class TestJ201ReserveNowOptionsFromPayload:
    def test_maps_2_0_1_payload_shape(self, device_ocpp_j201):
        options = device_ocpp_j201._reserve_now_options_from_payload({
            "id": 42,
            "expiryDateTime": "2025-01-15T13:00:00+00:00",
            "evseId": 2,
            "idToken": {"idToken": "RFID-A", "type": "ISO14443"},
            "groupIdToken": {"idToken": "GROUP-X", "type": "Central"},
        })

        assert options == {
            "reservationId": 42,
            "connectorId": 2,
            "evseId": 2,
            "idTag": "RFID-A",
            "parentIdTag": "GROUP-X",
            "expiryDate": "2025-01-15T13:00:00+00:00",
        }


class TestJ201FlowChargeReservationGate:
    @pytest.mark.asyncio
    async def test_flow_charge_aborts_when_authorize_does_not_match_reservation(
            self, device_ocpp_j201):
        _seed_reservation(device_ocpp_j201, reservation_id=42, connector_id=1,
                          id_tag="OWNER", parent_id_tag="GROUP-X")
        sent = []

        async def fake_send(action, payload):
            sent.append(action)
            if action == "Authorize":
                return [3, "req-1", {"idTokenInfo": {
                    "status": "Accepted",
                    "groupIdToken": {"idToken": "GROUP-Y", "type": "Central"},
                }}]
            return [3, "req-1", {"idTokenInfo": {"status": "Accepted"}}]

        device_ocpp_j201.by_device_req_send = AsyncMock(side_effect=fake_send)

        ok = await device_ocpp_j201.flow_charge(True, {"connectorId": 1, "idTag": "INTRUDER"})

        assert ok is False
        assert "Authorize" in sent
        # j201 sends StatusNotification("Occupied") AFTER the gate, so neither it nor
        # the TransactionEvent should be sent on a gate rejection
        assert "TransactionEvent" not in sent
        assert "StatusNotification" not in sent
        assert device_ocpp_j201.reservation_is_active()


class TestJ201FlowReserveStatusPayload:
    @pytest.mark.asyncio
    async def test_reserved_status_uses_2_0_1_connector_status_field(self, device_ocpp_j201):
        captured = {}

        async def fake_send(action, payload):
            captured[action] = payload
            return [3, "req-1", {}]

        device_ocpp_j201.by_device_req_send = AsyncMock(side_effect=fake_send)

        ok = await device_ocpp_j201.flow_reserve({
            "reservationId": 5, "connectorId": 1, "evseId": 1, "idTag": "X"
        })

        assert ok is True
        assert captured["StatusNotification"]["connectorStatus"] == "Reserved"
        assert captured["StatusNotification"]["evseId"] == 1
