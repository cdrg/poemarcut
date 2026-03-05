"""Keyboard event handling for PoEMarcut."""

import contextlib
import logging
import platform
import time
from threading import Lock

import pyautogui
import pydirectinput
import pyperclip
from pynput.keyboard import Key, KeyCode, Listener


class KeyboardListenerManager:
    """Singleton manager that owns the `pynput` Listener and related state.

    Encapsulates the listener and a lock so callers don't rely on module
    globals. Use the module-level `_listener_manager` instance.
    """

    def __init__(self) -> None:
        """Initialize the manager's lock and listener state."""
        self._lock = Lock()
        self._listener: Listener | None = None

    def start(
        self,
        keys: dict[str, Key | KeyCode],
        adjustment_factor: float,
        min_actual_factor: float,
        *,
        enter_after_calcprice: bool = True,
        blocking: bool = True,
    ) -> Listener | None:
        """Start and track a `pynput` Listener with the provided parameters.

        Returns the started `Listener` when `blocking` is False, otherwise
        blocks until the listener exits and returns None.
        """
        listener = Listener(
            on_release=lambda key: on_release(
                key=key,
                copyitem_key=keys["copyitem_key"],
                rightclick_key=keys["rightclick_key"],
                calcprice_key=keys["calcprice_key"],
                enter_key=keys["enter_key"],
                exit_key=keys["exit_key"],
                adjustment_factor=adjustment_factor,
                min_actual_factor=min_actual_factor,
                enter_after_calcprice=enter_after_calcprice,
            )  # type: ignore[attr-defined]
        )

        with self._lock:
            self._listener = listener

        if blocking:
            try:
                with listener:
                    listener.join()
            finally:
                with self._lock:
                    if self._listener is listener:
                        self._listener = None
            return None

        listener.start()
        return listener

    def stop(self) -> None:
        """Stop and join the active listener if present.

        This is safe to call from another thread; the manager will clear
        its stored listener reference before attempting to stop it.
        """
        with self._lock:
            listener = self._listener
            self._listener = None

        if listener is None:
            return

        try:
            listener.stop()
            with contextlib.suppress(RuntimeError):
                listener.join(timeout=1.0)
        except Exception:
            logging.getLogger(__name__).exception("Exception while stopping listener.")


# Module-level singleton instance
_listener_manager = KeyboardListenerManager()


def start_listener(
    keys: dict[str, Key | KeyCode],
    adjustment_factor: float,
    min_actual_factor: float,
    *,
    enter_after_calcprice: bool = True,
    blocking: bool = True,
) -> Listener | None:
    """Start the keyboard listener.

    Args:
        keys (dict[str, Key | KeyCode]): A dictionary containing the keys to listen for.
         The expected keys are 'copyitem_key', 'rightclick_key', 'calcprice_key', 'enter_key', and 'exit_key'.
        adjustment_factor (float): The factor by which to adjust the price.
        min_actual_factor (float): The minimum allowed actual adjustment factor.
        enter_after_calcprice (bool): Whether to press enter after price calculation.
        blocking (bool): Whether to block the main thread with the listener. If False, the listener will run in a separate thread.

    """
    # Delegate to the module-level singleton manager. The manager handles
    # storing and stopping the active Listener instance.
    return _listener_manager.start(
        keys=keys,
        adjustment_factor=adjustment_factor,
        min_actual_factor=min_actual_factor,
        enter_after_calcprice=enter_after_calcprice,
        blocking=blocking,
    )


def stop_listener() -> None:
    """Stop the active keyboard listener started by `start_listener`.

    This delegates to the `KeyboardListenerManager` singleton and is safe
    to call from another thread.
    """
    _listener_manager.stop()


def keyorkeycode_from_str(key_str: str) -> Key | KeyCode:
    """Convert a string representation of a key to a pynput Key or KeyCode.

    This is unfortunately necessary because pynput does not provide the from_char method for both.

    Args:
        key_str (str): The string representation of the key, e.g. 'f3', 'a', etc.

    Returns:
        Key | KeyCode: The corresponding Key or KeyCode object.

    """
    # Check if it's a special key in the Key enum
    try:
        special_key = getattr(Key, key_str.lower(), None)
        if special_key is not None:
            return special_key
    except AttributeError as e:
        msg = f"Invalid key string: {key_str}"
        raise ValueError(msg) from e

    # Otherwise, treat it as a regular character key
    if len(key_str) != 1:
        msg = f"Invalid key string: {key_str}"
        raise ValueError(msg)
    try:
        key_code = KeyCode.from_char(key_str)
    except ValueError as e:
        msg = f"Invalid key string: {key_str}"
        raise ValueError(msg) from e
    return key_code


def on_release(  # noqa: C901, PLR0912, PLR0913
    key: Key | KeyCode | None,
    copyitem_key: Key | KeyCode,
    rightclick_key: Key | KeyCode,
    calcprice_key: Key | KeyCode,
    enter_key: Key | KeyCode,
    exit_key: Key | KeyCode,
    adjustment_factor: float,
    min_actual_factor: float,
    *,
    enter_after_calcprice: bool = True,
) -> bool:
    """Handle pynput key release events.

    Args:
        key (Key | KeyCode | None): The released key.
        copyitem_key (Key | KeyCode): The key to send 'ctrl+alt+c' command to copy the hovered item.
        rightclick_key (Key | KeyCode): The key to send 'right-click' to open the price dialog for the hovered item.
        calcprice_key (Key | KeyCode): The key to activate price calculation + replacement.
        enter_key (Key | KeyCode): The key to send 'enter' key to the new price.
        exit_key (Key | KeyCode): The key to exit the program.
        adjustment_factor (float): The factor by which to adjust the price.
        min_actual_factor (float): The minimum allowed actual adjustment factor.
        enter_after_calcprice (bool): Whether to press enter after price calculation.

    Returns:
        bool: True to continue listening, False to stop.

    """
    if key is None:
        return True

    try:
        if isinstance(key, (Key, KeyCode)) and key == copyitem_key:
            # Send ctrl+alt+c to copy hovered item text to clipboard
            pyautogui.hotkey("ctrl", "alt", "c")

        if isinstance(key, (Key, KeyCode)) and key == rightclick_key:
            # Right click to open price dialog
            # prefer to use pydirectinput because pyautogui.rightclick doesn't work properly in the game
            if platform.system() == "Windows":
                pydirectinput.rightClick()
            else:
                pyautogui.rightClick()  # this doesn't work on Windows, untested on other platforms

        elif isinstance(key, (Key, KeyCode)) and key == calcprice_key:
            # Copy (pre-selected) price to the clipboard
            # use pyautogui because it sends keys faster
            pyautogui.hotkey("ctrl", "c")

            try:
                # Get current price from clipboard. Strip any thousands separators (locale dependent).
                current_price: int = int(pyperclip.paste().replace(",", "").replace(".", ""))
            except ValueError:
                return True  # do nothing if clipboard value is not a valid int

            if current_price <= 1:
                return True  # do nothing if parsed int is 1 or less

            actual_adjustment_factor: float = int(current_price * adjustment_factor) / current_price
            if actual_adjustment_factor < min_actual_factor:
                return True  # do nothing if actual adj factor is below minimum

            # Calculate the new discounted price
            new_price: int = int(current_price * adjustment_factor)

            # Have to press backspace first because of PoE paste bug.
            # (If text is selected and text cursor is at end of line, pasting will fail.)
            pyautogui.press("backspace")

            time.sleep(0.35)  # small delay to ensure backspace completes before pasting

            # Paste the new price from clipboard
            pyperclip.copy(str(new_price))
            pyautogui.hotkey("ctrl", "v")

            if enter_after_calcprice:
                # Press enter to confirm new price
                pyautogui.press("enter")

        elif isinstance(key, (Key, KeyCode)) and key == enter_key:
            if not enter_after_calcprice:
                # Press enter to confirm new price
                pyautogui.press("enter")

        elif isinstance(key, (Key, KeyCode)) and key == exit_key:
            return False

    except (OSError, RuntimeError, ValueError, pyautogui.FailSafeException):
        logging.getLogger(__name__).exception("Exception while handling key release event.")

    return True
