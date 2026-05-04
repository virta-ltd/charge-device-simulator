import asyncio
import dataclasses
import sys
import typing

import aioconsole
import questionary


async def run_with_delay(to_run, delay_seconds):
    await asyncio.sleep(delay_seconds)
    await to_run
    pass


@dataclasses.dataclass
class MenuEntry:
    """A single entry in an interactive menu. `handler` is awaited when the
    entry is selected; `is_back` flags the entry that exits the loop;
    `shortcut` (single character) is the keyboard accelerator in TTY mode and
    is also accepted as input on the non-TTY fallback path."""
    label: str
    handler: typing.Optional[typing.Callable[[], typing.Awaitable[typing.Any]]] = None
    is_back: bool = False
    shortcut: typing.Optional[str] = None


async def run_menu(prompt: str, entries: typing.Sequence[MenuEntry]) -> None:
    """Loop the menu: select an entry, dispatch its handler, repeat until an
    `is_back` entry is chosen. Selection runs through `select_from_list`, so
    it gets arrow-key + numeric/letter shortcuts in TTY and a numbered-list
    fallback elsewhere."""
    labels: typing.List[str] = [e.label for e in entries]
    shortcuts: typing.List[typing.Optional[str]] = [e.shortcut for e in entries]
    while True:
        choice: str = await select_from_list(
            prompt, labels, allow_custom=False, shortcuts=shortcuts)
        entry: MenuEntry = next(e for e in entries if e.label == choice)
        if entry.is_back:
            return
        if entry.handler is not None:
            await entry.handler()


_OTHER_SENTINEL: str = "Other (enter custom value)"


def _is_tty() -> bool:
    """True when stdin is attached to a real terminal. False under pytest,
    piped input, or any environment where prompt_toolkit can't render."""
    try:
        return sys.stdin.isatty()
    except Exception:
        return False


async def select_from_list(
    prompt: str,
    choices: typing.Sequence[str],
    *,
    default: typing.Optional[str] = None,
    allow_custom: bool = True,
    shortcuts: typing.Optional[typing.Sequence[typing.Optional[str]]] = None,
) -> str:
    """Pick one of `choices` interactively.

    TTY: questionary's arrow-key picker. If `shortcuts` is provided, each
    choice carries that explicit shortcut key; otherwise questionary
    auto-assigns 1..9. If `allow_custom`, an "Other" sentinel is appended.

    Non-TTY (pytest, piped input): a numbered list is printed and one line is
    read. A numeric index resolves to that choice; a literal match returns
    that choice; a shortcut match resolves to the corresponding choice;
    otherwise the input is returned verbatim when `allow_custom`, else the
    prompt repeats. Empty input + `default` returns `default`.
    """
    if shortcuts is not None and len(shortcuts) != len(choices):
        raise ValueError("shortcuts must match the length of choices")
    if _is_tty():
        try:
            return await _select_tty(prompt, choices, default, allow_custom, shortcuts)
        except Exception:
            # Fall back to the line-based path on any prompt_toolkit failure
            # (e.g., unsupported pseudo-terminal).
            pass
    return await _select_fallback(prompt, choices, default, allow_custom, shortcuts)


def _build_questionary_choices(
    choices: typing.Sequence[str],
    shortcuts: typing.Optional[typing.Sequence[typing.Optional[str]]],
) -> typing.List[typing.Any]:
    if shortcuts is None:
        return list(choices)
    return [
        questionary.Choice(title=label, value=label, shortcut_key=shortcut)
        if shortcut is not None
        else questionary.Choice(title=label, value=label)
        for label, shortcut in zip(choices, shortcuts)
    ]


async def _select_tty(
    prompt: str,
    choices: typing.Sequence[str],
    default: typing.Optional[str],
    allow_custom: bool,
    shortcuts: typing.Optional[typing.Sequence[typing.Optional[str]]],
) -> str:
    full_choices: typing.List[typing.Any] = _build_questionary_choices(choices, shortcuts)
    if allow_custom:
        full_choices.append(questionary.Separator())
        full_choices.append(_OTHER_SENTINEL)
    # `use_shortcuts=True` is required for shortcuts to render and bind at all.
    # Questionary leaves explicit `shortcut_key` values alone and only
    # auto-assigns 1..9 to choices that don't have one.
    result: typing.Optional[str] = await questionary.select(
        prompt,
        choices=full_choices,
        default=default if default in choices else None,
        use_shortcuts=True,
    ).ask_async()
    if result is None:
        # User aborted (Ctrl-C); re-raise as cancellation.
        raise asyncio.CancelledError()
    if result == _OTHER_SENTINEL:
        return await prompt_text("Custom value:")
    return result


async def prompt_text(prompt: str, *, default: typing.Optional[str] = None) -> str:
    """Read a free-form text line from the user.

    TTY: questionary.text — keeps stdin under prompt_toolkit, so it composes
    cleanly with prior `select_from_list` calls (a plain `aioconsole.ainput`
    after a questionary picker can hang because prompt_toolkit briefly held
    stdin in raw mode).

    Non-TTY: aioconsole.ainput, same behavior as before.
    """
    if _is_tty():
        try:
            result: typing.Optional[str] = await questionary.text(
                prompt,
                default=default or "",
            ).ask_async()
            if result is None:
                raise asyncio.CancelledError()
            return result
        except Exception:
            pass
    rendered: str = prompt
    if default is not None:
        rendered += f" [{default}]"
    rendered += " "
    raw: str = await aioconsole.ainput(rendered)
    if raw == "" and default is not None:
        return default
    return raw


async def _select_fallback(
    prompt: str,
    choices: typing.Sequence[str],
    default: typing.Optional[str],
    allow_custom: bool,
    shortcuts: typing.Optional[typing.Sequence[typing.Optional[str]]],
) -> str:
    shortcut_to_choice: typing.Dict[str, str] = {}
    if shortcuts is not None:
        for label, shortcut in zip(choices, shortcuts):
            if shortcut is not None:
                shortcut_to_choice[shortcut] = label
    while True:
        rendered: str = prompt + "\n"
        for idx, choice in enumerate(choices):
            short: typing.Optional[str] = (
                shortcuts[idx] if shortcuts is not None else None)
            tag: str = f"({short})" if short is not None else f"{idx}"
            rendered += f"  {tag}: {choice}\n"
        if default is not None:
            rendered += f"Pick an index, type a value, or press Enter for {default!r}: "
        else:
            rendered += "Pick an index or type a value: "
        raw: str = await aioconsole.ainput(rendered)
        if raw == "":
            if default is not None:
                return default
            continue
        if raw in shortcut_to_choice:
            return shortcut_to_choice[raw]
        if raw.isdigit():
            index: int = int(raw)
            if 0 <= index < len(choices):
                return choices[index]
        if raw in choices:
            return raw
        if allow_custom:
            return raw
        # Strict mode: re-prompt
        print(f"Invalid value: {raw!r}. Pick from the list above.")
