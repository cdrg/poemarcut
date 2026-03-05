"""Keyboard event handling for PoEMarcut."""

import logging
import platform
import time

import pyautogui
import pydirectinput
import pyperclip
from pynput.keyboard import Key, KeyCode, Listener


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
        rightclick_key (Key | KeyCode): The key to send 'right-click' to open the dialog.
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


def start_listener(
    keys: dict[str, Key | KeyCode],
    adjustment_factor: float,
    min_actual_factor: float,
    *,
    enter_after_calcprice: bool = True,
) -> None:
    """Start the keyboard listener.

    Args:
        keys (dict[str, Key | KeyCode]): A dictionary containing the keys to listen for.
         The expected keys are 'rightclick_key', 'calcprice_key', 'enter_key', and 'exit_key'.
        adjustment_factor (float): The factor by which to adjust the price.
        min_actual_factor (float): The minimum allowed actual adjustment factor.
        enter_after_calcprice (bool): Whether to press enter after price calculation.

    """
    with Listener(
        on_release=lambda key: on_release(
            key=key,
            rightclick_key=keys["rightclick_key"],
            calcprice_key=keys["calcprice_key"],
            enter_key=keys["enter_key"],
            exit_key=keys["exit_key"],
            adjustment_factor=adjustment_factor,
            min_actual_factor=min_actual_factor,
            enter_after_calcprice=enter_after_calcprice,
        )  # type: ignore[attr-defined]
        # have to suppress type check because pynput Listener does not follow its own type hint
    ) as listener:
        listener.join()
