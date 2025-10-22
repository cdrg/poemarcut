# ruff: noqa: T201 # disable print() warning, remove if refactored to GUI app
"""Tool to quickly reprice Path of Exile 1/2 merchant tab items.

Also works for stash tab items, but you'll have to select the price text yourself.

On start, prints a list of suggested new prices for 1-unit currency items based on current poe.ninja currency prices.
"""

import platform
import sys
import time
from pathlib import Path
from typing import Any

import pyautogui
import pydirectinput
import pyperclip
import requests
import yaml
from pynput.keyboard import Key, KeyCode, Listener

S_IN_HOUR = 3600
POE1_CURRENCY_API_URL = "https://poe.ninja/api/data/currencyoverview"
POE2_CURRENCY_API_URL = "https://poe.ninja/poe2/api/economy/temp2/overview"
POE2_EX_WORTHLESS_VAL = 500  # if div<=>ex is above this value, ex is worthless


def get_currency_values(game: str, league: str, *, update: bool = True) -> dict:
    """Fetch currency prices from cache file or poe.ninja currency API.

    GGG only updates the currency exchange API once per hour, so there's no reason to fetch more often than that.

    Args:
        game (int): The game version, either 1 (PoE1) or 2 (PoE2).
        league (str): The league name to fetch currency prices for.
        update (bool): Whether to fetch new prices from API if cache file is older than one hour.

    Returns:
        Dict: The poe.ninja currency API response as a Python object.

    """
    cache_file = Path(f"{league}.yaml")

    data: dict = {}
    # If cache file exists, and either is less than one hour old or if "update" is false,
    # load data from cache file.
    if cache_file.exists() and (cache_file.stat().st_mtime > (time.time() - 1 * S_IN_HOUR) or update is False):
        try:
            with cache_file.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except (yaml.YAMLError, FileNotFoundError) as e:
            print(f"Error reading cache file: {e}", file=sys.stderr)

        if (
            "lines" not in data
            or (
                game == "1"
                and not any((item.get("currencyTypeName") == "Divine Orb") for item in data.get("lines", []))
            )
            or (game == "2" and not any((item.get("id") == "divine") for item in data.get("lines", [])))
        ):
            print("Error: Cache file for 'PoE{game} {league}' is missing data.", file=sys.stderr)
    # Otherwise fetch from API
    else:
        response: requests.Response = requests.Response()
        try:
            if game == "1":
                response = requests.get(
                    POE1_CURRENCY_API_URL,
                    params={"league": league, "type": "Currency"},
                    timeout=10,
                )
            else:
                response = requests.get(
                    POE2_CURRENCY_API_URL, params={"leagueName": league, "overviewName": "Currency"}, timeout=10
                )
            response.raise_for_status()
        except requests.HTTPError as e:
            print(f"HTTP error fetching prices from poe.ninja: {e}", file=sys.stderr)
        except requests.RequestException as e:
            print(f"Error fetching prices from poe.ninja: {e}", file=sys.stderr)

        data = response.json()

        # Validate expected items in data
        if (
            "lines" not in data
            or (
                game == "1"
                and not any((item.get("currencyTypeName") == "Divine Orb") for item in data.get("lines", []))
            )
            or (game == "2" and not any((item.get("id") == "divine") for item in data.get("lines", [])))
        ):
            print(
                f"Error: Invalid data received from API for PoE{game} '{league}' league. This is expected if league does not exist.",
                file=sys.stderr,
            )
        # Write data to cache file if data is valid
        else:
            try:
                with cache_file.open("w", encoding="utf-8") as f:
                    yaml.safe_dump(data, f)
            except (yaml.YAMLError, UnicodeDecodeError) as e:
                print(f"Error writing to cache file: {e}", file=sys.stderr)

    if cache_file.exists() and "lines" in data:
        file_mtime = cache_file.stat().st_mtime
        time_diff = time.time() - file_mtime
        diff_hours = int(time_diff // S_IN_HOUR)
        diff_mins = int((time_diff % S_IN_HOUR) // 60)
        print(
            f"(PoE{game} currency data for '{league}' last updated: {diff_hours}h:{diff_mins:02d}m ago ({time.ctime(file_mtime)}))"
        )

    return data


def keyorkeycode_from_str(key_str: str) -> Key | KeyCode:
    """Convert a string representation of a key to a pynput Key or KeyCode.

    This is unfortunately necessary because pynput does not provide the from_char method for both.

    Args:
        key_str (str): The string representation of the key, e.g. 'f3', 'a', etc.

    Returns:
        Key | KeyCode: The corresponding Key or KeyCode object.

    """
    try:
        # Check if it's a special key in the Key enum
        special_key = getattr(Key, key_str.lower(), None)
        if special_key is not None:
            return special_key
        # Otherwise, treat it as a regular character key
        return KeyCode.from_char(key_str)
    except Exception as e:
        msg = f"Invalid key string: {key_str}"
        raise ValueError(msg) from e


def on_release(  # noqa: PLR0913
    key: Key | KeyCode | None,
    rightclick_key: Key | KeyCode,
    calcprice_key: Key | KeyCode,
    enter_key: Key | KeyCode,
    exit_key: Key | KeyCode,
    adjustment_factor: float,
) -> bool:
    """Handle pynput key release events.

    Args:
        key (Key | KeyCode | None): The released key.
        rightclick_key (Key | KeyCode): The key to send 'right-click' to open the dialog.
        calcprice_key (Key | KeyCode): The key to activate price calculation + replacement.
        enter_key (Key | KeyCode): The key to send 'enter' key to the new price.
        exit_key (Key | KeyCode): The key to exit the program.
        adjustment_factor (float): The factor by which to adjust the price.

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
                current_price: int | None = int(pyperclip.paste())
            except ValueError:
                current_price: int | None = None

            # If the clipboard does not contain a valid integer or is 1 or less, do nothing
            if current_price is None or current_price <= 1:
                return True
            # Calculate the new discounted price
            new_price: int = int(current_price * adjustment_factor)

            # Have to press backspace first because of PoE paste bug with text selected
            pyautogui.press("backspace")

            # Paste the new price from clipboard
            pyperclip.copy(str(new_price))
            pyautogui.hotkey("ctrl", "v")

            time.sleep(0.3)  # small delay to ensure paste completes before handling next key

        elif isinstance(key, (Key, KeyCode)) and key == enter_key:
            # Press enter to confirm new price
            pyautogui.press("enter")

        elif isinstance(key, (Key, KeyCode)) and key == exit_key:
            print("Exiting...")
            return False

    except (OSError, RuntimeError, ValueError, pyautogui.FailSafeException) as e:
        print(f"Error: {e}", file=sys.stderr)

    return True


def print_poe1_currency_suggestions(adjustment_factor: float, data: dict) -> None:
    """Print suggested new currency prices for PoE1 based on current poe.ninja currency values.

    Args:
        adjustment_factor (float): The factor by which the price is being adjusted.
        data (dict): The currency data fetched from poe.ninja.

    """
    if "lines" in data:
        div_chaos_val = next(item for item in data.get("lines", []) if item.get("currencyTypeName") == "Divine Orb")[
            "chaosEquivalent"
        ]

        div_chaos_adj: float = div_chaos_val * adjustment_factor
        print("PoE1 suggested new currency setting if current setting is 1, based on current values:")
        print(f"{adjustment_factor}x 1 Divine Orb")
        print(f" = {int(div_chaos_adj)} Chaos Orb ({div_chaos_adj:.2f})")
        print(f"{adjustment_factor}x 1 Chaos Orb")
        print(" = Just vendor it already!")
    else:
        print("Error: Invalid data, could not determine currency suggestions for PoE1.", file=sys.stderr)


def print_poe2_currency_suggestions(adjustment_factor: float, data: dict) -> None:
    """Print suggested new currency prices for PoE2 based on current poe.ninja currency values.

    Some calculations are inverted depending on if poe.ninja provides "div per X" or "X per div".

    Args:
        adjustment_factor (float): The factor by which the price is being adjusted.
        data (dict): The currency data fetched from poe.ninja.

    """
    if "lines" in data:
        annul_div_val: float = next(item for item in data.get("lines", []) if item.get("id") == "annul")["primaryValue"]
        chaos_div_val: float = next(item for item in data.get("lines", []) if item.get("id") == "chaos")["primaryValue"]
        exalt_div_val: float = next(item for item in data.get("lines", []) if item.get("id") == "exalted")[
            "primaryValue"
        ]

        div_annul_adj: float = 1 / annul_div_val * adjustment_factor
        div_chaos_adj: float = 1 / chaos_div_val * adjustment_factor
        div_exalt_adj: float = 1 / exalt_div_val * adjustment_factor
        annul_chaos_adj: float = 1 / chaos_div_val * annul_div_val * adjustment_factor
        annul_exalt_adj: float = 1 / exalt_div_val * annul_div_val * adjustment_factor
        chaos_exalt_adj: float = 1 / exalt_div_val * chaos_div_val * adjustment_factor
        print("PoE2 suggested new currency setting if current setting is 1, based on current values:")
        print(f"{adjustment_factor}x 1 Divine Orb")
        print(f" = {int(div_annul_adj)} Orb of Annulment ({div_annul_adj:.2f})")
        print(f" = {int(div_chaos_adj)} Chaos Orb ({div_chaos_adj:.2f})")
        print(f" = {int(div_exalt_adj)} Exalted Orb ({div_exalt_adj:.2f})")
        print(f"{adjustment_factor}x 1 Orb of Annulment")
        print(f" = {int(annul_chaos_adj)} Chaos Orb ({annul_chaos_adj:.2f})")
        print(f" = {int(annul_exalt_adj)} Exalted Orb ({annul_exalt_adj:.2f})")
        print(f"{adjustment_factor}x 1 Chaos Orb")
        print(
            f" = {int(chaos_exalt_adj)} Exalted Orb ({chaos_exalt_adj:.2f})",
            end="",
        )
        if 1 / exalt_div_val > POE2_EX_WORTHLESS_VAL:
            print("... but you should probably vendor it")
        else:
            print()
        print(f"{adjustment_factor}x 1 Exalted Orb")
        print(" = Just vendor it already!")
    else:
        print("Error: Invalid data, could not determine currency suggestions for PoE2.", file=sys.stderr)


def main() -> int:
    """Read settings from file, fetch and print currency values, then start keyboard listener."""
    # Load settings from settings.yaml file.
    try:
        with Path("settings.yaml").open("r", encoding="utf-8") as f:
            settings: dict[str, dict[str, Any]] = yaml.safe_load(f)
    except FileNotFoundError:
        print("Error: settings.yaml not found. Exiting.", file=sys.stderr)
        return 1

    # Attempt to parse each key string from settings.yaml into a Key or KeyCode object as appropriate
    keys: dict[str, Key | KeyCode] = {}
    key_names = ["rightclick_key", "calcprice_key", "enter_key", "exit_key"]
    for key_name in key_names:
        try:
            keys[key_name] = keyorkeycode_from_str(settings["keys"][key_name])
        except ValueError as e:
            print(f"Error loading {key_name} from settings.yaml: {e}", file=sys.stderr)
            return 1

    # Attempt to parse adjustment factor
    try:
        adjustment_factor: float = float(settings["logic"]["adjustment_factor"])
    except (ValueError, TypeError):
        print(
            f"Error: Invalid adjustment factor value {settings['logic']['adjustment_factor']} in settings.yaml.",
            file=sys.stderr,
        )
        return 1

    # Attempt to parse game(s)
    games: list = str(settings["currency"]["games"]).replace(" ", "").split(",")
    for game in games:
        if game not in ("1", "2"):
            print(
                f"Error: Invalid value for games {settings['currency']['game']} in settings.yaml. "
                f"Game must be '1' (PoE1) or '2' (PoE2).",
                file=sys.stderr,
            )
            return 1

    print("> PoEMarcut running <")
    print(f"Press '{keys['rightclick_key']}' or right-click with item hovered to open dialog, then... ")
    print(f"press '{keys['calcprice_key']}' to adjust price, then... ")
    print(f"press '{keys['enter_key']}' to set the new price.")
    print(f"Press '{keys['exit_key']}' to exit the program.")
    print("================================")

    # Fetch and print currency values
    for game in games:
        league = settings["currency"]["poe1league"] if game == "1" else settings["currency"]["poe2league"]
        data = get_currency_values(game=game, league=league, update=settings["currency"]["autoupdate"])
        # If data object is valid, print suggested currency values for case where current price is 1
        if (
            game == "1"
            and "lines" in data
            and any((item.get("currencyTypeName") == "Divine Orb") for item in data.get("lines", []))
        ):
            print_poe1_currency_suggestions(adjustment_factor, data)
            print()
        elif game == "2" and "lines" in data and any((item.get("id") == "divine") for item in data.get("lines", [])):
            print_poe2_currency_suggestions(adjustment_factor, data)
            print()
        else:
            print(f"Error: Could not retrieve currency suggestions for PoE{game}.", file=sys.stderr)
            print()

    # Start pynput keyboard listener
    # have to suppress type check because pynput Listener does not follow its own type hint
    with Listener(
        on_release=lambda event: on_release(
            event, keys["rightclick_key"], keys["calcprice_key"], keys["enter_key"], keys["exit_key"], adjustment_factor
        )  # type: ignore[attr-defined]
    ) as listener:
        listener.join()

    return 0


if __name__ == "__main__":
    sys.exit(main())
