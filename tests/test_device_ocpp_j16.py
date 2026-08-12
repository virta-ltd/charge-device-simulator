from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture
def no_sleep():
    """flow_charge waits out a fixed cool-down after the meter loop; skip it."""
    with patch("asyncio.sleep", new_callable=AsyncMock):
        yield


def _stub_authorize_response(id_tag: str, parent_id_tag: str = None):
    info = {"status": "Accepted"}
    if parent_id_tag is not None:
        info["parentIdTag"] = parent_id_tag
    return [3, "req-1", {"idTagInfo": info}]


def _stub_start_transaction_response(transaction_id: int = 555):
    return [3, "req-1", {"idTagInfo": {"status": "Accepted"}, "transactionId": transaction_id}]


def _seed_reservation(device, *, reservation_id=42, connector_id=1,
                      id_tag="RFID-A", parent_id_tag=None):
    device.reservation_set(
        reservation_id=reservation_id,
        connector_id=connector_id,
        id_tag=id_tag,
        parent_id_tag=parent_id_tag,
        expiry_date="2025-01-15T13:00:00+00:00",
    )


class TestJ16AuthorizeStashesParent:
    @pytest.mark.asyncio
    async def test_parent_id_tag_captured_from_response(self, device_ocpp_j16):
        device_ocpp_j16.by_device_req_send = AsyncMock(
            return_value=_stub_authorize_response("RFID-A", parent_id_tag="GROUP-X"))

        ok = await device_ocpp_j16.action_authorize({"idTag": "RFID-A"})

        assert ok is True
        assert device_ocpp_j16._last_authorize_info["parent_id_tag"] == "GROUP-X"


class TestJ16StartTransactionWithReservation:
    @pytest.mark.asyncio
    async def test_id_tag_match_includes_reservation_id_in_start(self, device_ocpp_j16):
        _seed_reservation(device_ocpp_j16, reservation_id=42, connector_id=1, id_tag="RFID-A")
        device_ocpp_j16._last_authorize_info = {"id_tag": "RFID-A", "parent_id_tag": None}
        captured = {}

        async def fake_send(action, payload):
            captured[action] = payload
            return _stub_start_transaction_response()

        device_ocpp_j16.by_device_req_send = AsyncMock(side_effect=fake_send)

        # Simulate the gate decision (would normally happen in flow_charge)
        options = {"connectorId": 1, "idTag": "RFID-A"}
        assert device_ocpp_j16._pre_charge_reservation_gate(options) is True
        assert await device_ocpp_j16.action_charge_start(options) is True
        device_ocpp_j16._consume_reservation_if_used(options)

        assert captured["StartTransaction"]["reservationId"] == 42
        assert not device_ocpp_j16.reservation_is_active()

    @pytest.mark.asyncio
    async def test_parent_match_includes_reservation_id_in_start(self, device_ocpp_j16):
        _seed_reservation(device_ocpp_j16, reservation_id=43, connector_id=1,
                          id_tag="OWNER", parent_id_tag="GROUP-X")
        device_ocpp_j16._last_authorize_info = {"id_tag": "FRIEND", "parent_id_tag": "GROUP-X"}
        captured = {}

        async def fake_send(action, payload):
            captured[action] = payload
            return _stub_start_transaction_response()

        device_ocpp_j16.by_device_req_send = AsyncMock(side_effect=fake_send)

        options = {"connectorId": 1, "idTag": "FRIEND"}
        assert device_ocpp_j16._pre_charge_reservation_gate(options) is True
        assert await device_ocpp_j16.action_charge_start(options) is True

        assert captured["StartTransaction"]["reservationId"] == 43

    @pytest.mark.asyncio
    async def test_no_reservation_id_when_no_active_reservation(self, device_ocpp_j16):
        captured = {}

        async def fake_send(action, payload):
            captured[action] = payload
            return _stub_start_transaction_response()

        device_ocpp_j16.by_device_req_send = AsyncMock(side_effect=fake_send)

        await device_ocpp_j16.action_charge_start({"connectorId": 1, "idTag": "X"})

        assert "reservationId" not in captured["StartTransaction"]


class TestJ16FlowChargeReservationGate:
    @pytest.mark.asyncio
    async def test_flow_charge_aborts_when_authorize_does_not_match_reservation(
            self, device_ocpp_j16):
        _seed_reservation(device_ocpp_j16, reservation_id=42, connector_id=1,
                          id_tag="OWNER", parent_id_tag="GROUP-X")
        sent = []

        async def fake_send(action, payload):
            sent.append(action)
            if action == "Authorize":
                # Returned tag has neither idTag nor parentIdTag matching the reservation
                return [3, "req-1", {
                    "idTagInfo": {"status": "Accepted", "parentIdTag": "GROUP-Y"}}]
            return [3, "req-1", {"idTagInfo": {"status": "Accepted"}, "transactionId": 1}]

        device_ocpp_j16.by_device_req_send = AsyncMock(side_effect=fake_send)

        ok = await device_ocpp_j16.flow_charge(True, {"connectorId": 1, "idTag": "INTRUDER"})

        assert ok is False
        # Authorize was sent, but no StartTransaction or status updates followed
        assert "Authorize" in sent
        assert "StartTransaction" not in sent
        assert "StatusNotification" not in sent
        # Reservation preserved
        assert device_ocpp_j16.reservation_is_active()


class TestJ16ChargeCycleIsolation:
    """The regression behind Virta sessions staying CLOSED: consecutive
    frequent-flow charges shared one options dict, so every cycle after the
    first replayed the first cycle's start time and meterStop."""

    @pytest.mark.asyncio
    async def test_second_cycle_sends_fresh_start_and_stop(self, device_ocpp_j16, no_sleep):
        sent = []

        async def fake_send(action, payload):
            sent.append((action, payload))
            if action == "StartTransaction":
                return _stub_start_transaction_response()
            return [3, "req-1", {"idTagInfo": {"status": "Accepted"}}]

        device_ocpp_j16.by_device_req_send = AsyncMock(side_effect=fake_send)
        # Shared dict, exactly as Simulator.loop_flow_frequent passes it
        options = {
            "connectorId": 1,
            "idTag": "X",
            "autoActionsLoopDelayInSeconds": 0,
            "autoActionsLoopCount": 1,
        }

        await device_ocpp_j16.flow_charge(True, options)
        first_start = [p for a, p in sent if a == "StartTransaction"][0]
        first_stop = [p for a, p in sent if a == "StopTransaction"][0]

        sent.clear()
        await device_ocpp_j16.flow_charge(True, options)
        second_start = [p for a, p in sent if a == "StartTransaction"][0]
        second_stop = [p for a, p in sent if a == "StopTransaction"][0]

        # Each cycle declares its own time window
        assert second_start["timestamp"] != first_start["timestamp"]
        assert second_stop["timestamp"] != first_stop["timestamp"]
        # The second cycle starts where the first stopped — a real energy
        # register never rewinds
        assert second_start["meterStart"] == first_stop["meterStop"]
        assert second_stop["meterStop"] >= second_start["meterStart"]


class TestJ16FlowReserveStatusPayload:
    @pytest.mark.asyncio
    async def test_reserved_status_uses_1_6_status_field(self, device_ocpp_j16):
        captured = {}

        async def fake_send(action, payload):
            captured[action] = payload
            return [3, "req-1", {}]

        device_ocpp_j16.by_device_req_send = AsyncMock(side_effect=fake_send)

        ok = await device_ocpp_j16.flow_reserve({
            "reservationId": 5, "connectorId": 1, "idTag": "X"
        })

        assert ok is True
        assert captured["StatusNotification"]["status"] == "Reserved"
        assert captured["StatusNotification"]["connectorId"] == 1
