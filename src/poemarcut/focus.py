"""Foreground-window lookup for PoEMarcut.

OS API lookups to determine whether the currently focused window is a Path of Exile
game client window.

"""

import ctypes
import logging
import platform
from ctypes import wintypes

from poemarcut.constants import POE_GAME_EXECUTABLES

logger = logging.getLogger(__name__)

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def _get_foreground_process_executable() -> str | None:
    """Return the basename of the foreground window's owning process executable.

    Returns:
        str | None: Lowercased executable basename (e.g. 'pathofexile_x64.exe'),
        or None if it could not be determined.

    """
    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None

    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return None

    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)  # noqa: FBT003
    if not handle:
        return None

    try:
        buf = ctypes.create_unicode_buffer(260)
        size = wintypes.DWORD(len(buf))
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return None
        image_path = buf.value
    finally:
        kernel32.CloseHandle(handle)

    if not image_path:
        return None

    return image_path.rsplit("\\", 1)[-1].lower()


def is_poe_game_window() -> bool:
    """Return whether the currently focused window is a known Path of Exile game client window.

    On Windows, this checks that the foreground window's owning process is one
    of the known set of Path of Exile 1 or 2 client executables. Any failure to
    determine the foreground process (no window, inaccessible process, lookup
    error) is treated as unauthorized.

    On non-Windows platforms, always returns True.

    Returns:
        bool: True if the currently focused window is a known Path of Exile game client window.

    """
    if platform.system() != "Windows":
        return True

    try:
        executable = _get_foreground_process_executable()
    except OSError:
        logger.exception("Failed to determine foreground window process.")
        return False

    if executable is None:
        return False

    return executable in POE_GAME_EXECUTABLES
