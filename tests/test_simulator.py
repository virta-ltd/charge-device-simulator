from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from charge_device_simulator.device.error_reasons import ErrorReasons
from charge_device_simulator.device.flows import Flows
from charge_device_simulator.device.frequent_flow_options import FrequentFlowOptions
from charge_device_simulator.device.simulator import Simulator


@pytest.fixture
def mock_device():
    """Creates a mock device with required async methods."""
    device = MagicMock()
    device.flow_authorize = AsyncMock(return_value=True)
    device.flow_charge = AsyncMock(return_value=True)
    device.flow_heartbeat = AsyncMock(return_value=True)
    device.re_initialize = AsyncMock(return_value=True)
    device.on_error = []
    return device


@pytest.fixture
def simulator(mock_device):
    """Creates a Simulator instance with a mock device."""
    sim = Simulator(mock_device)
    sim.flow_charge_options = {"idTag": "TEST_TAG", "connectorId": 1}
    return sim


class TestSimulatorFlowOptionsPassedAsDict:
    """Tests to verify flow methods receive options as dict, not unpacked kwargs.

    This is the critical test class that validates the bug fix.
    Before the fix, simulator.py used **self.flow_charge_options which would
    unpack the dict into keyword arguments, causing TypeError.
    After the fix, it passes self.flow_charge_options directly as a dict.
    """

    @pytest.mark.asyncio
    async def test_frequent_flow_authorize_receives_dict(self, simulator, mock_device):
        """Test that frequent flow authorize passes options dict directly."""
        # Setup frequent flow for Authorize with count=1 and delay=0
        simulator.frequent_flows = {
            Flows.Authorize: FrequentFlowOptions(delay_seconds=0, count=1)
        }

        # Run the frequent flow loop briefly
        # It should trigger authorize flow once and exit
        await simulator.loop_flow_frequent()

        # Verify flow_authorize was called with the options dict directly
        mock_device.flow_authorize.assert_called_once_with(simulator.flow_charge_options)

    @pytest.mark.asyncio
    async def test_frequent_flow_charge_receives_dict(self, simulator, mock_device):
        """Test that frequent flow charge passes options dict directly."""
        # Setup frequent flow for Charge with count=1 and delay=0
        simulator.frequent_flows = {
            Flows.Charge: FrequentFlowOptions(delay_seconds=0, count=1)
        }

        # Run the frequent flow loop briefly
        await simulator.loop_flow_frequent()

        # Verify flow_charge was called with True and the options dict directly
        mock_device.flow_charge.assert_called_once_with(True, simulator.flow_charge_options)

    @pytest.mark.asyncio
    async def test_interactive_flow_charge_receives_dict(self, simulator, mock_device):
        """Test interactive mode passes dict to flow_charge."""
        # Mock aioconsole.ainput to simulate user selecting "1" (flow charge) then "0" (exit)
        with patch('aioconsole.ainput', new_callable=AsyncMock) as mock_input:
            mock_input.side_effect = ["1", "0"]
            await simulator.loop_interactive()

        # Verify flow_charge was called with the options dict directly
        mock_device.flow_charge.assert_called_once_with(True, simulator.flow_charge_options)

    @pytest.mark.asyncio
    async def test_interactive_flow_authorize_receives_dict(self, simulator, mock_device):
        """Test interactive mode passes dict to flow_authorize."""
        # Mock aioconsole.ainput to simulate user selecting "3" (authorize) then "0" (exit)
        with patch('aioconsole.ainput', new_callable=AsyncMock) as mock_input:
            mock_input.side_effect = ["3", "0"]
            await simulator.loop_interactive()

        # Verify flow_authorize was called with the options dict directly
        mock_device.flow_authorize.assert_called_once_with(simulator.flow_charge_options)


class TestSimulatorOptionsPersistence:
    """Tests to verify options dict modifications persist across calls."""

    @pytest.mark.asyncio
    async def test_device_modifications_persist_in_simulator(self, simulator, mock_device):
        """Test that when device modifies options, changes persist in simulator.flow_charge_options."""
        original_options = simulator.flow_charge_options
        original_id = id(original_options)

        async def modify_options(auto_stop, options):
            # Device modifies the options dict (simulating fill_missing_options_charge_start)
            options["chargeStartTime"] = "2025-01-15T12:00:00"
            options["meterStart"] = 1000
            return True

        mock_device.flow_charge = AsyncMock(side_effect=modify_options)

        # Setup and run frequent flow
        simulator.frequent_flows = {
            Flows.Charge: FrequentFlowOptions(delay_seconds=0, count=1)
        }
        await simulator.loop_flow_frequent()

        # Assert that modifications persist in the original options dict
        assert "chargeStartTime" in simulator.flow_charge_options
        assert simulator.flow_charge_options["chargeStartTime"] == "2025-01-15T12:00:00"
        assert "meterStart" in simulator.flow_charge_options
        assert simulator.flow_charge_options["meterStart"] == 1000

        # Assert it's the same dict reference
        assert id(simulator.flow_charge_options) == original_id


class TestSimulatorRfidSwipe:
    @pytest.mark.asyncio
    async def test_rfid_swipe_passes_entered_id_tag_without_mutating_config(self, simulator, mock_device):
        original_options = simulator.flow_charge_options
        original_id = id(original_options)
        original_id_tag = original_options.get("idTag")

        with patch('aioconsole.ainput', new_callable=AsyncMock) as mock_input:
            mock_input.side_effect = ["4", "RFID-SWIPED-TAG", "0"]
            await simulator.loop_interactive()

        mock_device.flow_charge.assert_called_once()
        passed_options = mock_device.flow_charge.call_args.args[1]
        assert passed_options["idTag"] == "RFID-SWIPED-TAG"
        # Configured options must not be mutated
        assert simulator.flow_charge_options.get("idTag") == original_id_tag
        assert id(simulator.flow_charge_options) == original_id
        # The swipe options were a copy, not the same dict
        assert passed_options is not simulator.flow_charge_options


class TestErrorExitInteractiveBehavior:
    """When the operator runs in interactive mode, a CSMS-rejected response
    should drop them back to the menu rather than sys.exit'ing the process."""

    @pytest.mark.asyncio
    async def test_lifecycle_start_disables_error_exit_when_interactive(
            self, simulator, mock_device):
        mock_device.error_exit = True
        simulator.is_interactive = True
        simulator.frequent_flow_enabled = False
        # Stub the interactive loop so lifecycle_start returns immediately
        with patch.object(simulator, "loop_interactive", new_callable=AsyncMock):
            await simulator.lifecycle_start()

        assert mock_device.error_exit is False

    @pytest.mark.asyncio
    async def test_lifecycle_start_keeps_error_exit_when_not_interactive(
            self, simulator, mock_device):
        mock_device.error_exit = True
        simulator.is_interactive = False
        simulator.frequent_flow_enabled = False

        await simulator.lifecycle_start()

        # error_exit must remain True so frequent-flow / non-interactive runs
        # still crash on rejected responses (the existing fail-fast behavior).
        assert mock_device.error_exit is True


class TestSimulatorErrorHandling:
    """Tests for simulator error handling."""

    @pytest.mark.asyncio
    async def test_unknown_exception_triggers_re_initialize(self, simulator, mock_device):
        """Test that UnknownException error reason triggers re_initialize."""
        await simulator.device_on_error("test error", ErrorReasons.UnknownException)

        mock_device.re_initialize.assert_called_once()

    @pytest.mark.asyncio
    async def test_non_unknown_exception_does_not_re_initialize(self, simulator, mock_device):
        """Test that other error reasons do not trigger re_initialize."""
        await simulator.device_on_error("test error", ErrorReasons.InvalidResponse)

        mock_device.re_initialize.assert_not_called()
