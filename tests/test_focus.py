"""Tests for the Windows foreground-window authorization boundary."""

import platform

import pytest

from poemarcut import focus


def test_non_windows_always_authorized(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    assert focus.is_poe_game_window() is True


def test_windows_allowed_executable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    monkeypatch.setattr(focus, "_get_foreground_process_executable", lambda: "pathofexile_x64.exe")
    assert focus.is_poe_game_window() is True


def test_windows_allowed_executable_case_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    monkeypatch.setattr(focus, "_get_foreground_process_executable", lambda: "PathOfExile2Steam.EXE".lower())
    assert focus.is_poe_game_window() is True


def test_windows_unrelated_process_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    monkeypatch.setattr(focus, "_get_foreground_process_executable", lambda: "notepad.exe")
    assert focus.is_poe_game_window() is False


def test_windows_launcher_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    monkeypatch.setattr(focus, "_get_foreground_process_executable", lambda: "pathofexilelauncher.exe")
    assert focus.is_poe_game_window() is False


def test_windows_no_foreground_process_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    monkeypatch.setattr(focus, "_get_foreground_process_executable", lambda: None)
    assert focus.is_poe_game_window() is False


def test_windows_lookup_error_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Windows")

    def _raise() -> str | None:
        raise OSError

    monkeypatch.setattr(focus, "_get_foreground_process_executable", _raise)
    assert focus.is_poe_game_window() is False
