"""Tests for the foreground-window gate integrated into `keyboard.on_release`."""

from unittest.mock import MagicMock

import pytest
from pynput.keyboard import Key

from poemarcut import keyboard


def test_rejected_focus_blocks_stop_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(keyboard, "is_poe_game_window", lambda: False)
    result = keyboard.on_release(key=Key.f6)
    assert result is True  # listener keeps running; stop_key had no effect


def test_rejected_focus_blocks_calcprice_and_leaves_state_untouched(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(keyboard, "is_poe_game_window", lambda: False)

    keyboard._last_price = 42  # noqa: SLF001
    keyboard._last_type = "chaos"  # noqa: SLF001

    hotkey_mock = MagicMock()
    paste_mock = MagicMock(return_value="42")
    monkeypatch.setattr(keyboard.pyautogui, "hotkey", hotkey_mock)
    monkeypatch.setattr(keyboard.pyperclip, "paste", paste_mock)

    keyboard.on_release(key=Key.f3)

    hotkey_mock.assert_not_called()
    paste_mock.assert_not_called()
    assert keyboard._last_price == 42  # noqa: SLF001
    assert keyboard._last_type == "chaos"  # noqa: SLF001

    keyboard._last_price = None  # noqa: SLF001
    keyboard._last_type = None  # noqa: SLF001


def test_authorized_focus_allows_calcprice_to_proceed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(keyboard, "is_poe_game_window", lambda: True)

    keyboard._last_price = None  # noqa: SLF001
    keyboard._last_type = None  # noqa: SLF001

    hotkey_mock = MagicMock()
    paste_mock = MagicMock(return_value="100")
    monkeypatch.setattr(keyboard.pyautogui, "hotkey", hotkey_mock)
    monkeypatch.setattr(keyboard.pyperclip, "paste", paste_mock)

    keyboard.on_release(key=Key.f3)

    hotkey_mock.assert_any_call("ctrl", "c")
    paste_mock.assert_called()
