"""Keyboard event handling for PoEMarcut."""

import contextlib
import logging
import platform
import time
from collections.abc import Callable
from threading import Lock
from typing import Any

import pyautogui
import pyperclip
from pynput.keyboard import Key, KeyCode, Listener

from poemarcut import constants, currency, settings
from poemarcut.item import Item

# pydirectinput uses Windows-only APIs at import-time; import only on Windows
pydirectinput: Any | None = None
if platform.system() == "Windows":
    try:
        pydirectinput = __import__("pydirectinput")
    except ImportError:
        pydirectinput = None

logger = logging.getLogger(__name__)

# Module-level state to persist the last-extracted price/type between
# `on_release` invocations (the pynput listener calls this function per key
# event). Protect access with a lock to be safe if the listener runs on a
# separate thread.
_state_lock = Lock()
_last_price: int | None = None
_last_type: str | None = None


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
        *,
        blocking: bool = True,
        on_stop: Callable[[], None] | None = None,
    ) -> Listener | None:
        """Start and track a `pynput` Listener with the provided parameters.

        Returns: the started `Listener` when `blocking` is False, otherwise
        blocks until the listener exits and returns None.
        """

        def _on_release(key: Key | KeyCode | None) -> bool:
            should_continue = on_release(key=key)
            if not should_continue and on_stop is not None:
                # Let on_stop exceptions propagate so they're visible to callers.
                on_stop()
            return should_continue

        listener = Listener(on_release=_on_release)  # type: ignore[arg-type]

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
        except RuntimeError:
            logger.exception("Exception while stopping listener.")


# Module-level singleton instance
_listener_manager = KeyboardListenerManager()


def start_listener(
    *,
    blocking: bool = True,
    on_stop: Callable[[], None] | None = None,
) -> Listener | None:
    """Start the keyboard listener.

    Args:
        blocking (bool): Whether to block the main thread with the listener. If False, the listener will run in a separate thread.
        on_stop (Callable[[], None] | None): Optional callback invoked when
            the listener stops itself by handling the configured stop key.

    """
    # Delegate to the module-level singleton manager. The manager handles
    # storing and stopping the active Listener instance.
    return _listener_manager.start(
        blocking=blocking,
        on_stop=on_stop,
    )


def stop_listener() -> None:
    """Stop the active keyboard listener started by `start_listener`.

    This delegates to the `KeyboardListenerManager` singleton and is safe
    to call from another thread.
    """
    _listener_manager.stop()


def on_release(  # noqa: C901, PLR0911, PLR0912, PLR0915
    key: Key | KeyCode | None,
) -> bool:
    """Handle pynput key release events.

    Args:
        key (Key | KeyCode | None): The released key.

    Returns:
        bool: True to continue listening, False to stop.

    """
    # Use module-level persisted state so the value extracted when the
    # `copyitem_key` is pressed is available later when `calcprice_key` is
    # pressed. Access is protected with `_state_lock`.
    global _last_price, _last_type

    if key is None:
        return True

    try:
        settings_man: settings.SettingsManager = settings.settings_manager
        try:
            keys: dict[str, Key | KeyCode] = {
                k: keyorkeycode_from_str(v) for k, v in settings_man.settings.keys.model_dump().items()
            }
        except ValueError:
            logger.exception("Failed to build keys for hotkeys listener.")
            return False
        adjustment_factor: float = settings_man.settings.logic.adjustment_factor
        min_actual_factor: float = settings_man.settings.logic.min_actual_factor
        enter_after_calcprice: bool = settings_man.settings.logic.enter_after_calcprice
        game: int = settings_man.settings.currency.active_game
        league: str = settings_man.settings.currency.active_league
        raw_currencies = (
            settings_man.settings.currency.poe1currencies
            if game == 1
            else settings_man.settings.currency.poe2currencies
        )
        currencies: list[str] = list(raw_currencies.keys())
        merchant_currency_prefixes = (
            constants.POE1_MERCHANT_CURRENCY_PREFIXES if game == 1 else constants.POE2_MERCHANT_CURRENCY_PREFIXES
        )
        copyitem_key = keys["copyitem_key"]
        rightclick_key = keys["rightclick_key"]
        calcprice_key = keys["calcprice_key"]
        enter_key = keys["enter_key"]
        stop_key = keys["stop_key"]

        if isinstance(key, (Key, KeyCode)) and key == copyitem_key:
            logger.info("Attempting to extract price and currency type from hovered item.")
            # Send ctrl+alt+c to copy hovered item text to clipboard
            pyautogui.hotkey("ctrl", "alt", "c")
            item = Item.from_text(pyperclip.paste())
            if item is not None and item.note is not None:
                logger.info(
                    "Extracted price '%s' and currency '%s' from hovered item '%s'.",
                    item.note.price,
                    item.note.currency,
                    item.name,
                )
                price, cur_type = item.note.price, item.note.currency
            else:
                logger.warning(
                    "Failed to extract price and currency type from hovered item. Clipboard text was: %s",
                    pyperclip.paste(),
                )
                price, cur_type = None, None
            with _state_lock:
                _last_price, _last_type = price, cur_type

        if isinstance(key, (Key, KeyCode)) and key == rightclick_key:
            logger.info("Attempting to open price dialog with right click.")
            # Right click to open price dialog
            # prefer to use pydirectinput because pyautogui.rightclick doesn't work properly in the game
            if platform.system() == "Windows" and pydirectinput is not None:
                pydirectinput.rightClick()
            else:
                pyautogui.rightClick()  # this doesn't work on Windows, untested on other platforms

        elif isinstance(key, (Key, KeyCode)) and key == calcprice_key:
            logger.info("Attempting to calculate discounted price and update clipboard and price dialog.")
            # Copy (pre-selected) price to the clipboard
            # use pyautogui because it sends keys faster
            pyautogui.hotkey("ctrl", "c")

            with _state_lock:
                last_price, last_cur_type = _last_price, _last_type

            try:
                try:
                    # Get current price from clipboard. Strip any thousands separators (locale dependent).
                    # Future: handle fractional values? which are supported in stash tabs but not merchant
                    copied_price: int = int(pyperclip.paste().replace(",", "").replace(".", ""))
                except ValueError:
                    logger.warning(
                        "Clipboard value '%s' is not a valid integer. Aborting price calculation.",
                        pyperclip.paste(),
                    )
                    return True  # do nothing if clipboard value is not a valid int

                if (
                    last_price is not None and last_price != copied_price
                ):  # sanity check that both parsed prices are the same
                    logger.warning(
                        "Clipboard price (%d) does not match expected last price (%d). Aborting price calculation.",
                        copied_price,
                        last_price,
                    )
                    return True  # do nothing if clipboard price doesn't match previously parsed price

                if copied_price < 1:
                    logger.error("Parsed price is less than 1 (%d). Aborting price calculation.", copied_price)
                    return True  # do nothing if current price is less than 1

                # if we don't know the currency type and assume_highest is enabled, assume the currency type is the highest
                if not last_cur_type and settings_man.settings.currency.assume_highest_currency:
                    last_price = copied_price
                    last_cur_type = currencies[0] if currencies else None

                actual_adj_factor: float = int(copied_price * adjustment_factor) / copied_price
                next_cur_type: str | None = None
                # if we can't go lower, because price is 1 or is low enough tha the discount would be too high
                if copied_price == 1 or actual_adj_factor < min_actual_factor:
                    # and if we know the copied currency type and it's in our list of convertible currencies and it's not the final currency
                    if (
                        last_cur_type is not None
                        and last_cur_type in currencies
                        and last_cur_type != list(currencies)[-1]
                    ):
                        next_cur_type = list(currencies)[list(currencies).index(last_cur_type) + 1]
                        # convert the price as the equivalent amount of the next currency type
                        # get_exchange_rate returns a whole number if the more valuable currency is the first argument
                        try:
                            exchange_rate: float = currency.get_exchange_rate(
                                game=game, league=league, from_currency=last_cur_type, to_currency=next_cur_type
                            )
                        except LookupError:
                            logger.error(  # noqa: TRY400
                                "Failed to get exchange rate for game %i league %s from %s to %s. Price not adjusted.",
                                game,
                                league,
                                last_cur_type,
                                next_cur_type,
                            )
                            return True  # do nothing if exchange rate retrieval fails
                        copied_price = int(exchange_rate)
                        logger.info(
                            "Price is %d %s, converting to equivalent of %d %s based on exchange rate %.2f",
                            last_price,
                            last_cur_type,
                            copied_price,
                            next_cur_type,
                            exchange_rate,
                        )
                    elif copied_price == 1:
                        logger.info(
                            "Price is 1 %s, but cannot convert to next currency. Either currency type is unknown, not in the list of convertible currencies, or is the final currency.",
                            last_cur_type or "unknown",
                        )
                        return True  # do nothing if parsed int is 1 and we do not know the currency type or it's the final type
                    elif actual_adj_factor < min_actual_factor:
                        logger.info(
                            "Calculated adjustment factor %.2f [trunc(%d*%.2f)/%d] is less than the minimum adjustment factor %.2f. Price not adjusted.",
                            actual_adj_factor,
                            last_price,
                            adjustment_factor,
                            last_price,
                            min_actual_factor,
                        )
                        return True  # do nothing if the actual adjustment factor is less than the minimum allowed factor (enforce maximum discount)

                # Calculate the new discounted price, rounding down (truncate) to ensure price always decreases
                new_price: int = int(copied_price * adjustment_factor)

                # Paste the new price from clipboard
                logger.info("Pasting new price '%d' from clipboard.", new_price)
                pyperclip.copy(str(new_price))
                pyautogui.hotkey("ctrl", "v")

                # Change currency dropdown if currency was converted
                if next_cur_type is not None:
                    logger.info("Attempting to select next currency type '%s' in dropdown.", next_cur_type)
                    # tab to switch focus to currency dropdown
                    pyautogui.press("tab")

                    # type the characters of the shortest possible prefix of the full currency name
                    # one by one to move the dropdown selection
                    prefix = merchant_currency_prefixes[next_cur_type]
                    time.sleep(0.6)  # long delay is needed for the dropdown to be ready for whatever reason
                    pyautogui.write(prefix, interval=0.1)

                    # enter to confirm the dropdown selection
                    pyautogui.press("enter")

                if enter_after_calcprice:
                    # Press enter to confirm new price
                    pyautogui.press("enter")
            finally:
                # Clear persisted price/type since it was processed and is no longer valid.
                with _state_lock:
                    _last_price, _last_type = None, None

        elif isinstance(key, (Key, KeyCode)) and key == enter_key:
            if not enter_after_calcprice:
                # Press enter to confirm new price
                pyautogui.press("enter")

        elif isinstance(key, (Key, KeyCode)) and key == stop_key:
            logger.info("Stop key pressed, stopping listener.")
            return False

    except (OSError, RuntimeError, ValueError, pyautogui.FailSafeException):
        logger.exception("Exception while handling key release event.")

    return True


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
