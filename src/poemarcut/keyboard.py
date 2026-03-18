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
from poemarcut.item import Item, parse_int_price
from poemarcut.logic import (
    compute_discounted_price_and_actual,
    convert_and_compute_price,
)

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

# Cache parsed bindings so we don't re-parse on every key event.
# Parsed binding format: ('special', Key) | ('char', str) | ('vk', int) | ('scan', int)
_parsed_keys_lock = Lock()
# Keep caches as mutable dicts so we can update in-place (avoid global rebind).
_cached_key_strs: dict[str, str] = {}
_parsed_keys: dict[str, tuple[str, Any]] = {}


def _match_char(event_key: Key | KeyCode | None, char: str) -> bool:
    """Return True if the event_key matches the provided character string.

    Args:
        event_key (Key | KeyCode | None): The event key from the listener.
        char (str): Single-character string to compare.

    Returns:
        bool: True if the event key represents the given character.

    """
    if not isinstance(event_key, KeyCode):
        return False
    if getattr(event_key, "char", None) == char:
        return True
    try:
        return KeyCode.from_char(char) == event_key
    except ValueError:
        return False


def binding_matches(event_key: Key | KeyCode | None, binding: tuple[str, Any]) -> bool:
    """Return True if the event key matches the parsed binding tuple.

    Binding tuples have shape `(type_str, value)` where `type_str` is one
    of: 'special', 'vk', 'scan', 'char'.

    Args:
        event_key (Key | KeyCode | None): The key event to match.
        binding (tuple[str, Any]): Parsed binding tuple.

    Returns:
        bool: True if the event matches the binding.

    """
    if not isinstance(binding, tuple) or len(binding) != 2:  # noqa: PLR2004
        return False

    binding_type, binding_value = binding

    if binding_type == "special":
        return event_key == binding_value

    if binding_type == "vk":
        return getattr(event_key, "vk", None) == binding_value

    if binding_type == "scan":
        return getattr(event_key, "scan", None) == binding_value

    if binding_type == "char":
        return _match_char(event_key, binding_value)

    # final fallback
    return event_key == binding_value


class KeyboardListenerManager:
    """Singleton manager that owns the `pynput` Listener and related state.

    Encapsulates the listener and a lock so callers don't rely on module
    globals. Use the module-level `_listener_manager` instance.
    """

    def __init__(self) -> None:
        """Initialize the manager's lock and listener state.

        Returns:
            None

        """
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
            """Wrap the module-level `on_release` used by the Listener.

            Args:
                key (Key | KeyCode | None): The released key event supplied by pynput.

            Returns:
                bool: True to continue listening, False to stop.

            """
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

        # Non-blocking: start the listener in a separate thread and return it.
        try:
            listener.start()
        except RuntimeError:
            logger.exception("Exception while starting listener.")
            # Ensure we don't keep a reference to a failed listener
            with self._lock:
                if self._listener is listener:
                    self._listener = None
            return None
        else:
            return listener

    def stop(self) -> None:
        """Stop the currently tracked listener, if any.

        Safe to call from another thread. No-op if there's no active listener.

        Returns:
            None

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

    Returns:
        Listener | None: The started Listener when `blocking` is False, otherwise None.

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

    Returns:
        None

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
        settings_manager: settings.SettingsManager = settings.settings_manager
        try:
            key_strs: dict[str, str] = settings_manager.settings.keys.model_dump()
        except (AttributeError, TypeError, ValueError):
            logger.exception("Failed to read key strings from settings.")
            return True

        with _parsed_keys_lock:
            if _cached_key_strs != key_strs:
                _parsed_keys.clear()
                for k, v in key_strs.items():
                    try:
                        _parsed_keys[k] = keyorkeycode_from_str(key_str=v)
                    except ValueError:
                        logger.exception("Invalid hotkey binding '%s' for key '%s'; skipping.", v, k)
                        # skip invalid binding but keep listener running
                _cached_key_strs.clear()
                _cached_key_strs.update(key_strs)
        discount_percent: int = settings_manager.settings.logic.discount_percent

        max_actual_discount: int = settings_manager.settings.logic.max_actual_discount
        enter_after_calcprice: bool = settings_manager.settings.logic.enter_after_calcprice
        game: int = settings_manager.settings.currency.active_game
        league: str = settings_manager.settings.currency.active_league
        raw_currencies = (
            settings_manager.settings.currency.poe1currencies
            if game == 1
            else settings_manager.settings.currency.poe2currencies
        )
        currencies: list[str] = list(raw_currencies.keys())
        merchant_currency_prefixes = (
            constants.POE1_MERCHANT_CURRENCY_PREFIXES if game == 1 else constants.POE2_MERCHANT_CURRENCY_PREFIXES
        )

        # Helper to fetch parsed binding safely (may be missing if parsing failed)
        def _get_binding(name: str) -> tuple[str, Any] | None:
            """Retrieve a parsed binding by name from the module cache.

            Args:
                name (str): The settings key name for the binding.

            Returns:
                tuple[str, Any] | None: Parsed binding tuple or None if missing.

            """
            with _parsed_keys_lock:
                return _parsed_keys.get(name)

        copyitem_key = _get_binding("copyitem_key")
        rightclick_key = _get_binding("rightclick_key")
        calcprice_key = _get_binding("calcprice_key")
        enter_key = _get_binding("enter_key")
        stop_key = _get_binding("stop_key")

        if (
            copyitem_key is not None
            and isinstance(key, (Key, KeyCode))
            and binding_matches(event_key=key, binding=copyitem_key)
        ):
            logger.info("Attempting to extract price and currency type from hovered item.")
            # Send ctrl+alt+c to copy hovered item text to clipboard
            pyautogui.hotkey("ctrl", "alt", "c")
            item = Item.from_text(text=pyperclip.paste())
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

        if (
            rightclick_key is not None
            and isinstance(key, (Key, KeyCode))
            and binding_matches(event_key=key, binding=rightclick_key)
        ):
            logger.info("Attempting to open price dialog with right click.")
            # Right click to open price dialog
            # prefer to use pydirectinput because pyautogui.rightclick doesn't work properly in the game
            if platform.system() == "Windows" and pydirectinput is not None:
                pydirectinput.rightClick()
            else:
                pyautogui.rightClick()  # this doesn't work on Windows, untested on other platforms

        elif (
            calcprice_key is not None
            and isinstance(key, (Key, KeyCode))
            and binding_matches(event_key=key, binding=calcprice_key)
        ):
            logger.info("Attempting to calculate discounted price and update clipboard and price dialog.")
            # Copy (pre-selected) price to the clipboard
            # use pyautogui because it sends keys faster
            pyautogui.hotkey("ctrl", "c")

            with _state_lock:
                last_price, last_cur_type = _last_price, _last_type

            try:
                raw_clip = pyperclip.paste()
                try:
                    # Parse current price from clipboard. Strip any thousands separators (locale dependent).
                    copied_price: int = parse_int_price(raw_clip)
                except ValueError:
                    logger.warning(
                        "Clipboard value '%s' is not a valid integer. Aborting price calculation.",
                        raw_clip,
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
                if not last_cur_type and settings_manager.settings.currency.assume_highest_currency:
                    last_price = copied_price
                    last_cur_type = currencies[0] if currencies else None

                # Compute integer discounted price and observed percent after integer rounding.
                discounted_price_candidate, actual_discount = compute_discounted_price_and_actual(
                    copied_price, discount_percent
                )
                next_cur_type: str | None = None
                # if we can't go lower because price is 1 or the calculated percent discount
                # exceeds the allowed maximum, bail out or try converting to the next currency
                if copied_price == 1 or actual_discount > float(max_actual_discount):
                    # and if we know the copied currency type and it's in our list of convertible currencies and it's not the final currency
                    if (
                        last_cur_type is not None
                        and last_cur_type in currencies
                        and last_cur_type != list(currencies)[-1]
                    ):
                        # Ensure max_actual_discount is respected but apply discount_percent otherwise when possible.
                        amount_units = int(last_price or copied_price)

                        def _get_rate(*, from_currency: str, to_currency: str) -> float:
                            return currency.get_exchange_rate(
                                game=game,
                                league=league,
                                from_currency=from_currency,
                                to_currency=to_currency,
                                autoupdate=settings_manager.settings.currency.autoupdate,
                            )

                        converted_price, converted_currency, converted_actual = convert_and_compute_price(
                            original_units=amount_units,
                            last_cur_type=last_cur_type,
                            currencies=currencies,
                            discount_percent=discount_percent,
                            max_actual_discount=max_actual_discount,
                            get_exchange_rate=_get_rate,
                        )

                        if converted_price is None:
                            logger.info(
                                "Unable to find a conversion path that respects max_actual_discount %.2f%%. Price not adjusted.",
                                max_actual_discount,
                            )
                            return True

                        discounted_price_candidate = converted_price
                        actual_discount = converted_actual
                        next_cur_type = converted_currency
                    elif copied_price == 1:
                        logger.info(
                            "Price is 1 %s, but cannot convert to next currency. Either currency type is unknown, not in the list of convertible currencies, or is the final currency.",
                            last_cur_type or "unknown",
                        )
                        return True  # do nothing if parsed int is 1 and we do not know the currency type or it's the final type
                    elif actual_discount > float(max_actual_discount):
                        logger.info(
                            "Calculated discount %.2f%% exceeds max allowed discount %.2f%%. Price not adjusted.",
                            actual_discount,
                            max_actual_discount,
                        )
                        return True  # do nothing if the calculated discount exceeds the maximum allowed discount

                # Use the precomputed integer discounted price
                new_price: int = discounted_price_candidate

                # Small delay before pasting to ensure the price dialog is ready for input
                time.sleep(0.1)

                # Paste the new price from clipboard
                logger.info(
                    "Pasting new price '%d', previous price was '%d'. (%.2f%%)",
                    new_price,
                    copied_price,
                    actual_discount,
                )
                pyperclip.copy(str(new_price))
                pyautogui.hotkey("ctrl", "v")

                # Change currency dropdown if currency was converted
                if next_cur_type is not None:
                    logger.info("Attempting to select next currency '%s' in dropdown.", next_cur_type)
                    # tab to switch focus to currency dropdown
                    pyautogui.press("tab")

                    # move the selection in the dropdown by typing the prefix, or using arrow keys
                    prefix = merchant_currency_prefixes[next_cur_type]
                    time.sleep(0.6)  # long delay is needed for the dropdown to be ready for whatever reason

                    # typing to select from dropdown doesn't work well with more than ~3 characters, since there's a timeout
                    if len(prefix) <= 3:  # noqa: PLR2004
                        pyautogui.write(prefix, interval=0.1)
                    # for longer prefixes, we need to determine the numerical difference of the indexes and then use arrow keys
                    elif last_cur_type is not None:
                        cur_index = list(merchant_currency_prefixes.keys()).index(last_cur_type)
                        target_index = list(merchant_currency_prefixes.keys()).index(next_cur_type)
                        index_diff = target_index - cur_index
                        if index_diff > 0:
                            for _ in range(index_diff):
                                pyautogui.press("down")
                                time.sleep(0.1)
                        elif index_diff < 0:
                            for _ in range(-index_diff):
                                pyautogui.press("up")
                                time.sleep(0.1)
                    else:
                        logger.warning(
                            "Unable to select next currency because current currency type is unknown and next currency prefix '%s' is too long.",
                            prefix,
                        )
                        return True  # do nothing

                    # enter to confirm the dropdown selection
                    pyautogui.press("enter")

                if enter_after_calcprice:
                    # Press enter to confirm new price
                    pyautogui.press("enter")
            finally:
                # Clear persisted price/type since it was processed and is no longer valid.
                with _state_lock:
                    _last_price, _last_type = None, None

        elif (
            enter_key is not None
            and isinstance(key, (Key, KeyCode))
            and binding_matches(event_key=key, binding=enter_key)
        ):
            if not enter_after_calcprice:
                # Press enter to confirm new price
                pyautogui.press("enter")
        elif (
            stop_key is not None
            and isinstance(key, (Key, KeyCode))
            and binding_matches(event_key=key, binding=stop_key)
        ):
            logger.info("Stop key pressed, stopping listener.")
            return False

    except (
        OSError,
        RuntimeError,
        pyautogui.FailSafeException,
        LookupError,
        pyperclip.PyperclipException,
    ):
        logger.exception("Exception while handling key release event.")

    return True


def keyorkeycode_from_str(key_str: str) -> tuple[str, Any]:
    """Convert a string representation of a key to a pynput Key or KeyCode.

    This is unfortunately necessary because pynput does not provide the from_char method for both.

    Args:
        key_str (str): The string representation of the key, e.g. 'f3', 'a', etc.

    Returns:
        Key | KeyCode: The corresponding Key or KeyCode object.

    """
    key_str = key_str.strip()
    # Support vk:<int> and scan:<int> formats for layout-independent bindings
    if key_str.startswith("vk:"):
        try:
            return ("vk", int(key_str.split(":", 1)[1]))
        except (ValueError, TypeError) as e:
            msg = f"Invalid vk binding: {key_str}"
            raise ValueError(msg) from e
    if key_str.startswith("scan:"):
        try:
            return ("scan", int(key_str.split(":", 1)[1]))
        except (ValueError, TypeError) as e:
            msg = f"Invalid scan binding: {key_str}"
            raise ValueError(msg) from e

    # Check if it's a special key in the Key enum
    try:
        special_key = getattr(Key, key_str.lower(), None)
        if special_key is not None:
            return ("special", special_key)
    except AttributeError as e:
        msg = f"Invalid key string: {key_str}"
        raise ValueError(msg) from e

    # Otherwise, treat it as a regular character key
    if len(key_str) != 1:
        msg = f"Invalid key string: {key_str}"
        raise ValueError(msg)
    # store char bindings as ('char', <single-char>)
    return ("char", key_str)
