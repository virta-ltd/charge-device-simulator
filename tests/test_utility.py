from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import questionary

from charge_device_simulator.device import utility


CHOICES = ("Available", "Preparing", "Charging", "Faulted")


class TestSelectFromListFallback:
    """Non-TTY fallback path (the path tests, pytest CI, and piped input hit).

    All tests force `_is_tty()` to False so questionary is never invoked."""

    @pytest.mark.asyncio
    async def test_numeric_index_resolves_to_choice(self):
        with patch.object(utility, "_is_tty", return_value=False), \
             patch("aioconsole.ainput", new_callable=AsyncMock) as mock_input:
            mock_input.side_effect = ["2"]
            result = await utility.select_from_list("Pick:", CHOICES)
        assert result == "Charging"

    @pytest.mark.asyncio
    async def test_literal_match_resolves_to_choice(self):
        with patch.object(utility, "_is_tty", return_value=False), \
             patch("aioconsole.ainput", new_callable=AsyncMock) as mock_input:
            mock_input.side_effect = ["Faulted"]
            result = await utility.select_from_list("Pick:", CHOICES)
        assert result == "Faulted"

    @pytest.mark.asyncio
    async def test_arbitrary_string_returned_when_allow_custom(self):
        with patch.object(utility, "_is_tty", return_value=False), \
             patch("aioconsole.ainput", new_callable=AsyncMock) as mock_input:
            mock_input.side_effect = ["MadeUpStatus"]
            result = await utility.select_from_list(
                "Pick:", CHOICES, allow_custom=True)
        assert result == "MadeUpStatus"

    @pytest.mark.asyncio
    async def test_strict_mode_reprompts_until_valid(self):
        with patch.object(utility, "_is_tty", return_value=False), \
             patch("aioconsole.ainput", new_callable=AsyncMock) as mock_input:
            mock_input.side_effect = ["Bogus", "Available"]
            result = await utility.select_from_list(
                "Pick:", CHOICES, allow_custom=False)
        assert result == "Available"
        assert mock_input.await_count == 2

    @pytest.mark.asyncio
    async def test_empty_input_with_default_returns_default(self):
        with patch.object(utility, "_is_tty", return_value=False), \
             patch("aioconsole.ainput", new_callable=AsyncMock) as mock_input:
            mock_input.side_effect = [""]
            result = await utility.select_from_list(
                "Pick:", CHOICES, default="Available")
        assert result == "Available"

    @pytest.mark.asyncio
    async def test_empty_input_without_default_reprompts(self):
        with patch.object(utility, "_is_tty", return_value=False), \
             patch("aioconsole.ainput", new_callable=AsyncMock) as mock_input:
            mock_input.side_effect = ["", "1"]
            result = await utility.select_from_list("Pick:", CHOICES)
        assert result == "Preparing"
        assert mock_input.await_count == 2

    @pytest.mark.asyncio
    async def test_numeric_out_of_range_falls_through_to_custom(self):
        with patch.object(utility, "_is_tty", return_value=False), \
             patch("aioconsole.ainput", new_callable=AsyncMock) as mock_input:
            mock_input.side_effect = ["99"]
            result = await utility.select_from_list("Pick:", CHOICES)
        # "99" is not a valid index and not in choices, so allow_custom returns it as-is
        assert result == "99"


class TestSelectFromListTty:
    """TTY path — mock questionary.select(...).ask_async() rather than driving
    prompt_toolkit itself."""

    @pytest.mark.asyncio
    async def test_questionary_result_returned_directly(self):
        question = MagicMock()
        question.ask_async = AsyncMock(return_value="Charging")
        with patch.object(utility, "_is_tty", return_value=True), \
             patch("questionary.select", return_value=question) as mock_select:
            result = await utility.select_from_list("Pick:", CHOICES)
        assert result == "Charging"
        # The "Other" sentinel should be appended when allow_custom=True
        passed_choices = mock_select.call_args.kwargs["choices"]
        assert utility._OTHER_SENTINEL in passed_choices

    @pytest.mark.asyncio
    async def test_other_sentinel_triggers_followup_input(self):
        question = MagicMock()
        question.ask_async = AsyncMock(return_value=utility._OTHER_SENTINEL)
        with patch.object(utility, "_is_tty", return_value=True), \
             patch("questionary.select", return_value=question), \
             patch("aioconsole.ainput", new_callable=AsyncMock) as mock_input:
            mock_input.return_value = "MadeUpStatus"
            result = await utility.select_from_list("Pick:", CHOICES)
        assert result == "MadeUpStatus"
        mock_input.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_other_sentinel_when_strict(self):
        question = MagicMock()
        question.ask_async = AsyncMock(return_value="Available")
        with patch.object(utility, "_is_tty", return_value=True), \
             patch("questionary.select", return_value=question) as mock_select:
            await utility.select_from_list("Pick:", CHOICES, allow_custom=False)
        passed_choices = mock_select.call_args.kwargs["choices"]
        assert utility._OTHER_SENTINEL not in passed_choices

    @pytest.mark.asyncio
    async def test_falls_back_to_line_path_on_questionary_failure(self):
        question = MagicMock()
        question.ask_async = AsyncMock(side_effect=RuntimeError("no terminal"))
        with patch.object(utility, "_is_tty", return_value=True), \
             patch("questionary.select", return_value=question), \
             patch("aioconsole.ainput", new_callable=AsyncMock) as mock_input:
            mock_input.side_effect = ["1"]
            result = await utility.select_from_list("Pick:", CHOICES)
        assert result == "Preparing"


class TestPromptText:
    @pytest.mark.asyncio
    async def test_non_tty_returns_input_verbatim(self):
        with patch.object(utility, "_is_tty", return_value=False), \
             patch("aioconsole.ainput", new_callable=AsyncMock) as mock_input:
            mock_input.return_value = "RFID-12345"
            result = await utility.prompt_text("Swipe:")
        assert result == "RFID-12345"

    @pytest.mark.asyncio
    async def test_non_tty_blank_with_default_returns_default(self):
        with patch.object(utility, "_is_tty", return_value=False), \
             patch("aioconsole.ainput", new_callable=AsyncMock) as mock_input:
            mock_input.return_value = ""
            result = await utility.prompt_text("Connector:", default="1")
        assert result == "1"

    @pytest.mark.asyncio
    async def test_non_tty_blank_without_default_returns_empty(self):
        with patch.object(utility, "_is_tty", return_value=False), \
             patch("aioconsole.ainput", new_callable=AsyncMock) as mock_input:
            mock_input.return_value = ""
            result = await utility.prompt_text("Optional:")
        assert result == ""

    @pytest.mark.asyncio
    async def test_tty_uses_questionary_text(self):
        question = MagicMock()
        question.ask_async = AsyncMock(return_value="42")
        with patch.object(utility, "_is_tty", return_value=True), \
             patch("questionary.text", return_value=question) as mock_text:
            result = await utility.prompt_text("Connector:")
        assert result == "42"
        mock_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_tty_falls_back_to_line_input_on_failure(self):
        question = MagicMock()
        question.ask_async = AsyncMock(side_effect=RuntimeError("no terminal"))
        with patch.object(utility, "_is_tty", return_value=True), \
             patch("questionary.text", return_value=question), \
             patch("aioconsole.ainput", new_callable=AsyncMock) as mock_input:
            mock_input.return_value = "fallback-value"
            result = await utility.prompt_text("Prompt:")
        assert result == "fallback-value"


class TestRunMenu:
    @pytest.mark.asyncio
    async def test_dispatches_handler_then_loops_until_back(self):
        first_handler = AsyncMock()
        second_handler = AsyncMock()
        with patch.object(utility, "_is_tty", return_value=False), \
             patch("aioconsole.ainput", new_callable=AsyncMock) as mock_input:
            mock_input.side_effect = ["1", "2", "0"]
            await utility.run_menu("Pick:", [
                utility.MenuEntry("Back", is_back=True),
                utility.MenuEntry("First", first_handler),
                utility.MenuEntry("Second", second_handler),
            ])
        first_handler.assert_awaited_once()
        second_handler.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_back_entry_with_no_handler_exits_immediately(self):
        with patch.object(utility, "_is_tty", return_value=False), \
             patch("aioconsole.ainput", new_callable=AsyncMock) as mock_input:
            mock_input.side_effect = ["0"]
            await utility.run_menu("Pick:", [
                utility.MenuEntry("Back", is_back=True),
                utility.MenuEntry("Other", AsyncMock()),
            ])
        mock_input.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_label_match_dispatches(self):
        handler = AsyncMock()
        with patch.object(utility, "_is_tty", return_value=False), \
             patch("aioconsole.ainput", new_callable=AsyncMock) as mock_input:
            mock_input.side_effect = ["First", "Back"]
            await utility.run_menu("Pick:", [
                utility.MenuEntry("Back", is_back=True),
                utility.MenuEntry("First", handler),
            ])
        handler.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_shortcut_input_dispatches_handler(self):
        handler = AsyncMock()
        with patch.object(utility, "_is_tty", return_value=False), \
             patch("aioconsole.ainput", new_callable=AsyncMock) as mock_input:
            mock_input.side_effect = ["s", "0"]
            await utility.run_menu("Pick:", [
                utility.MenuEntry("Exit", is_back=True, shortcut="0"),
                utility.MenuEntry("Single message", handler, shortcut="s"),
            ])
        handler.assert_awaited_once()


class TestSelectFromListShortcuts:
    @pytest.mark.asyncio
    async def test_shortcut_input_resolves_to_choice_in_fallback(self):
        with patch.object(utility, "_is_tty", return_value=False), \
             patch("aioconsole.ainput", new_callable=AsyncMock) as mock_input:
            mock_input.side_effect = ["s"]
            result = await utility.select_from_list(
                "Pick:",
                ("Available", "Single"),
                allow_custom=False,
                shortcuts=("a", "s"),
            )
        assert result == "Single"

    @pytest.mark.asyncio
    async def test_tty_passes_questionary_choice_with_explicit_shortcut(self):
        question = MagicMock()
        question.ask_async = AsyncMock(return_value="Single")
        with patch.object(utility, "_is_tty", return_value=True), \
             patch("questionary.select", return_value=question) as mock_select:
            await utility.select_from_list(
                "Pick:",
                ("Available", "Single"),
                allow_custom=False,
                shortcuts=("a", "s"),
            )
        passed_choices = mock_select.call_args.kwargs["choices"]
        # When explicit shortcuts are supplied we build Choice objects, not raw strings
        assert all(isinstance(c, questionary.Choice) for c in passed_choices)
        assert [c.shortcut_key for c in passed_choices] == ["a", "s"]
        # use_shortcuts must be True so questionary renders + binds the keys;
        # explicit shortcut_key values are preserved (auto-assignment only fills
        # in choices that don't already have one).
        assert mock_select.call_args.kwargs["use_shortcuts"] is True

    @pytest.mark.asyncio
    async def test_mismatched_shortcuts_length_raises(self):
        with pytest.raises(ValueError):
            await utility.select_from_list(
                "Pick:", ("a", "b"), shortcuts=("x",))
