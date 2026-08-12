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


def _stub_start_transaction_response(transaction_id: int = 555, status: str = "Accepted"):
    return [3, "req-1", {"idTagInfo": {"status": status}, "transactionId": transaction_id}]


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


class TestJ16MeterValuesPayload:
    @pytest.mark.asyncio
    async def test_sampled_value_is_a_string(self, device_ocpp_j16):
        """OCPP 1.6J types sampledValue.value as a string."""
        captured = {}

        async def fake_send(action, payload):
            captured[action] = payload
            return [3, "req-1", {}]

        device_ocpp_j16.by_device_req_send = AsyncMock(side_effect=fake_send)

        await device_ocpp_j16.action_meter_value({"connectorId": 1}, meter_value=2500)

        sampled = captured["MeterValues"]["meterValue"][0]["sampledValue"][0]
        assert sampled["value"] == "2500"

    @pytest.mark.asyncio
    async def test_explicit_zero_reading_is_sent_as_zero(self, device_ocpp_j16):
        """0 is a legitimate register reading (fresh/reset meter); a falsy
        check replaced it with a computed value, fabricating data that
        contradicts the operator's script."""
        captured = {}

        async def fake_send(action, payload):
            captured[action] = payload
            return [3, "req-1", {}]

        device_ocpp_j16.by_device_req_send = AsyncMock(side_effect=fake_send)

        await device_ocpp_j16.action_meter_value({"connectorId": 1}, meter_value=0)

        sampled = captured["MeterValues"]["meterValue"][0]["sampledValue"][0]
        assert sampled["value"] == "0"

    @pytest.mark.asyncio
    async def test_idle_meter_values_omits_transaction_id(self, device_ocpp_j16):
        """TriggerMessage(MeterValues) while no transaction is open must not
        send the placeholder transactionId -1."""
        captured = {}

        async def fake_send(action, payload):
            captured[action] = payload
            return [3, "req-1", {}]

        device_ocpp_j16.by_device_req_send = AsyncMock(side_effect=fake_send)

        await device_ocpp_j16.action_meter_value({"connectorId": 1}, meter_value=100)

        assert "transactionId" not in captured["MeterValues"]

    @pytest.mark.asyncio
    async def test_meter_values_during_transaction_include_transaction_id(self, device_ocpp_j16):
        captured = {}

        async def fake_send(action, payload):
            captured[action] = payload
            return [3, "req-1", {}]

        device_ocpp_j16.by_device_req_send = AsyncMock(side_effect=fake_send)
        device_ocpp_j16.charge_id = 555

        await device_ocpp_j16.action_meter_value({"connectorId": 1}, meter_value=100)

        assert captured["MeterValues"]["transactionId"] == 555

    @pytest.mark.asyncio
    async def test_no_stale_transaction_id_after_completed_session(self, device_ocpp_j16, no_sleep):
        """A completed charge must not leave its id attached to later idle
        meter values."""
        sent = []

        async def fake_send(action, payload):
            sent.append((action, payload))
            if action == "StartTransaction":
                return _stub_start_transaction_response()
            return [3, "req-1", {"idTagInfo": {"status": "Accepted"}}]

        device_ocpp_j16.by_device_req_send = AsyncMock(side_effect=fake_send)

        assert await device_ocpp_j16.flow_charge(True, {
            "connectorId": 1, "idTag": "X",
            "autoActionsLoopDelayInSeconds": 0, "autoActionsLoopCount": 1,
        }) is True
        in_charge = [p for a, p in sent if a == "MeterValues"]
        assert all(p["transactionId"] == 555 for p in in_charge)

        sent.clear()
        await device_ocpp_j16.action_meter_value({"connectorId": 1}, meter_value=100)

        assert "transactionId" not in sent[0][1]


class TestJ16StopTransactionPayload:
    async def _capture_stop(self, device, options):
        captured = {}

        async def fake_send(action, payload):
            captured[action] = payload
            return [3, "req-1", {"idTagInfo": {"status": "Accepted"}}]

        device.by_device_req_send = AsyncMock(side_effect=fake_send)
        await device.action_charge_stop(options)
        return captured["StopTransaction"]

    @pytest.mark.asyncio
    async def test_includes_transaction_end_sample(self, device_ocpp_j16):
        """Backends build the CDR from the closing register reading."""
        payload = await self._capture_stop(device_ocpp_j16, {
            "connectorId": 1,
            "idTag": "X",
            "meterStart": 1000,
            "meterStop": 3500,
            "chargeStopTime": "2025-01-15T12:30:00+00:00",
        })

        sampled = payload["transactionData"][0]["sampledValue"][0]
        assert sampled["value"] == "3500"
        assert sampled["context"] == "Transaction.End"
        assert sampled["measurand"] == "Energy.Active.Import.Register"
        assert payload["transactionData"][0]["timestamp"] == payload["timestamp"]

    @pytest.mark.asyncio
    async def test_meter_stop_matches_transaction_data(self, device_ocpp_j16):
        """A mismatch between the two is what makes a session unbillable."""
        payload = await self._capture_stop(device_ocpp_j16, {
            "connectorId": 1,
            "idTag": "X",
            "meterStart": 1000,
            "chargeStartTime": "2025-01-15T12:00:00+00:00",
        })

        assert str(payload["meterStop"]) == \
            payload["transactionData"][0]["sampledValue"][0]["value"]


class TestJ16StopTransactionConfHandling:
    """idTagInfo is optional in StopTransaction.conf and concerns the idTag's
    future authorization, not whether the stop was registered. An empty conf
    `[3, id, {}]` is valid and used to raise KeyError, crashing the flow and
    skipping the closing Available status."""

    def _options(self):
        return {"connectorId": 1, "idTag": "X", "meterStart": 1000,
                "meterStop": 2000, "chargeStopTime": "2025-01-15T12:30:00+00:00"}

    @pytest.mark.asyncio
    async def test_empty_conf_is_a_successful_stop(self, device_ocpp_j16):
        device_ocpp_j16.charge_id = 555
        device_ocpp_j16.by_device_req_send = AsyncMock(return_value=[3, "r", {}])

        ok = await device_ocpp_j16.action_charge_stop(self._options())

        assert ok is True
        assert device_ocpp_j16.charge_id == -1

    @pytest.mark.asyncio
    async def test_non_accepted_id_tag_info_still_stops(self, device_ocpp_j16):
        """A Blocked/Invalid verdict is about the tag, not the stop."""
        device_ocpp_j16.charge_id = 555
        device_ocpp_j16.by_device_req_send = AsyncMock(
            return_value=[3, "r", {"idTagInfo": {"status": "Blocked"}}])

        ok = await device_ocpp_j16.action_charge_stop(self._options())

        assert ok is True
        assert device_ocpp_j16.charge_id == -1

    @pytest.mark.asyncio
    async def test_timeout_or_call_error_still_fails(self, device_ocpp_j16):
        device_ocpp_j16.error_exit = False
        device_ocpp_j16.charge_id = 555
        device_ocpp_j16.by_device_req_send = AsyncMock(return_value=None)

        ok = await device_ocpp_j16.action_charge_stop(self._options())

        assert ok is False
        assert device_ocpp_j16.charge_id == 555

    @pytest.mark.asyncio
    async def test_malformed_conf_still_fails(self, device_ocpp_j16):
        device_ocpp_j16.error_exit = False
        device_ocpp_j16.by_device_req_send = AsyncMock(return_value=[3, "r"])

        ok = await device_ocpp_j16.action_charge_stop(self._options())

        assert ok is False


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

    @pytest.mark.asyncio
    async def test_preparing_precedes_start_transaction(self, device_ocpp_j16, no_sleep):
        sent = []

        async def fake_send(action, payload):
            sent.append((action, payload.get("status")))
            if action == "StartTransaction":
                return _stub_start_transaction_response()
            return [3, "req-1", {"idTagInfo": {"status": "Accepted"}}]

        device_ocpp_j16.by_device_req_send = AsyncMock(side_effect=fake_send)

        await device_ocpp_j16.flow_charge(True, {
            "connectorId": 1, "idTag": "X",
            "autoActionsLoopDelayInSeconds": 0, "autoActionsLoopCount": 1,
        })

        actions = [a for a, _ in sent]
        statuses = [s for a, s in sent if a == "StatusNotification"]
        assert actions.index("StartTransaction") > \
            next(i for i, (a, s) in enumerate(sent) if s == "Preparing")
        assert statuses[:2] == ["Preparing", "Charging"]


class TestJ16MidFlowFailureStillStops:
    """Once StartTransaction is accepted the backend holds an open session; a
    mid-flow failure (timeouts and CALLERRORs resolve to None) must still send
    StopTransaction, or the session is orphaned server-side — stuck open and
    never billed — while RemoteStopTransaction gets rejected because
    charge_in_progress was already cleared."""

    async def _run_flow(self, device, fail_when):
        sent = []

        async def fake_send(action, payload):
            sent.append((action, payload))
            if fail_when(action, payload):
                return None  # what a timeout or CALLERROR resolves to
            if action == "StartTransaction":
                return _stub_start_transaction_response()
            return [3, "req-1", {"idTagInfo": {"status": "Accepted"}}]

        device.by_device_req_send = AsyncMock(side_effect=fake_send)
        ok = await device.flow_charge(True, {
            "connectorId": 1, "idTag": "X",
            "autoActionsLoopDelayInSeconds": 0, "autoActionsLoopCount": 1,
        })
        return ok, [a for a, _ in sent]

    @pytest.mark.asyncio
    async def test_charging_status_failure_still_sends_stop(self, device_ocpp_j16, no_sleep):
        ok, actions = await self._run_flow(
            device_ocpp_j16,
            lambda a, p: a == "StatusNotification" and p.get("status") == "Charging")

        assert ok is False
        assert "StopTransaction" in actions
        assert device_ocpp_j16.charge_in_progress is False

    @pytest.mark.asyncio
    async def test_meter_values_failure_still_sends_stop(self, device_ocpp_j16, no_sleep):
        ok, actions = await self._run_flow(
            device_ocpp_j16, lambda a, p: a == "MeterValues")

        assert ok is False
        assert "StopTransaction" in actions

    @pytest.mark.asyncio
    async def test_finishing_status_failure_still_sends_stop(self, device_ocpp_j16, no_sleep):
        ok, actions = await self._run_flow(
            device_ocpp_j16,
            lambda a, p: a == "StatusNotification" and p.get("status") == "Finishing")

        assert ok is False
        assert "StopTransaction" in actions

    @pytest.mark.asyncio
    async def test_no_stop_when_start_transaction_never_succeeded(self, device_ocpp_j16, no_sleep):
        device_ocpp_j16.error_exit = False
        ok, actions = await self._run_flow(
            device_ocpp_j16, lambda a, p: a == "StartTransaction")

        assert ok is False
        assert "StopTransaction" not in actions


class TestJ16RejectedStartRollsBackStatus:
    """Preparing is sent before StartTransaction; if the CSMS then rejects the
    start (e.g. the tag turned Blocked between Authorize and start), the flow
    must send Available so the connector isn't left stuck in Preparing."""

    @pytest.mark.asyncio
    async def test_blocked_start_sends_available_after_preparing(self, device_ocpp_j16, no_sleep):
        device_ocpp_j16.error_exit = False
        sent = []

        async def fake_send(action, payload):
            sent.append((action, payload))
            if action == "StartTransaction":
                return _stub_start_transaction_response(status="Blocked")
            return [3, "req-1", {"idTagInfo": {"status": "Accepted"}}]

        device_ocpp_j16.by_device_req_send = AsyncMock(side_effect=fake_send)

        ok = await device_ocpp_j16.flow_charge(True, {
            "connectorId": 1, "idTag": "X",
            "autoActionsLoopDelayInSeconds": 0, "autoActionsLoopCount": 1,
        })

        assert ok is False
        statuses = [p.get("status") for a, p in sent if a == "StatusNotification"]
        assert statuses == ["Preparing", "Available"]
        # No transaction was ever opened, so nothing to stop
        assert "StopTransaction" not in [a for a, _ in sent]
        assert device_ocpp_j16.charge_in_progress is False


class TestJ16ScriptedMeterValuesFlow:
    @pytest.mark.asyncio
    async def test_stop_repeats_last_scripted_sample_across_cycles(self, device_ocpp_j16, no_sleep):
        sent = []

        async def fake_send(action, payload):
            sent.append((action, payload))
            if action == "StartTransaction":
                return _stub_start_transaction_response()
            return [3, "req-1", {"idTagInfo": {"status": "Accepted"}}]

        device_ocpp_j16.by_device_req_send = AsyncMock(side_effect=fake_send)
        options = {
            "connectorId": 1, "idTag": "X", "meterStart": 1000,
            "meterValues": [
                {"meterValue": 1500, "timestamp": "2025-01-15T12:10:00+00:00",
                 "secondsToSleep": 0},
                {"meterValue": 2000, "timestamp": "2025-01-15T12:20:00+00:00",
                 "secondsToSleep": 0},
            ],
        }

        await device_ocpp_j16.flow_charge(True, options)
        first_stop = [p for a, p in sent if a == "StopTransaction"][0]

        sent.clear()
        await device_ocpp_j16.flow_charge(True, options)
        second_start = [p for a, p in sent if a == "StartTransaction"][0]
        second_stop = [p for a, p in sent if a == "StopTransaction"][0]

        # The stop reading repeats the script's final register value, in both
        # meterStop and the Transaction.End sample
        assert first_stop["meterStop"] == 2000
        assert first_stop["transactionData"][0]["sampledValue"][0]["value"] == "2000"
        # The script replays identically each cycle: meterStart stays at the
        # configured value instead of carrying the previous stop above the
        # replayed samples
        assert second_start["meterStart"] == 1000
        assert second_stop["meterStop"] == 2000

    @pytest.mark.asyncio
    async def test_stop_reports_last_delivered_sample_when_a_send_fails_mid_script(self, device_ocpp_j16, no_sleep):
        """A MeterValues send failure aborts the script; the stop must repeat
        the last sample the backend actually received, not the configured
        final value the session never reached."""
        sent = []

        async def fake_send(action, payload):
            sent.append((action, payload))
            if action == "StartTransaction":
                return _stub_start_transaction_response()
            if (action == "MeterValues"
                    and payload["meterValue"][0]["sampledValue"][0]["value"] == "10000"):
                return None
            return [3, "req-1", {"idTagInfo": {"status": "Accepted"}}]

        device_ocpp_j16.by_device_req_send = AsyncMock(side_effect=fake_send)
        options = {
            "connectorId": 1, "idTag": "X", "meterStart": 1000,
            "meterValues": [
                {"meterValue": 1500, "timestamp": "2025-01-15T12:10:00+00:00",
                 "secondsToSleep": 0},
                {"meterValue": 10000, "timestamp": "2025-01-15T12:20:00+00:00",
                 "secondsToSleep": 0},
            ],
        }

        ok = await device_ocpp_j16.flow_charge(True, options)

        assert ok is False
        stop = [p for a, p in sent if a == "StopTransaction"][0]
        assert stop["meterStop"] == 1500
        assert stop["transactionData"][0]["sampledValue"][0]["value"] == "1500"


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
