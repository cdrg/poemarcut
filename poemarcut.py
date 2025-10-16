"""Tool to quickly reprice Path of Exile 1/2 market tab items.

Suggests new prices for 1-unit currency items based on current poe.ninja currency prices.
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


def get_currency_values(game: int, league: str, autoupdate: bool = True) -> dict:
    """Fetch currency prices from cache file or poe.ninja currency API.

    TODO: PoE1 is not supported yet because poe.ninja does not support PoE1 exchange yet.

    Args:
        game (int): The game version, either 1 (PoE1) or 2 (PoE2).
        league (str): The league name to fetch currency prices for.
        autoupdate (bool, optional): Whether to fetch new prices from API if cache file is older
                                     than one hour. Default True.

    Returns:
        Dict: The poe.ninja currency API response as a Python object.

    """
    S_IN_HOUR = 3600
    POE1_CURRENCY_API_URL = "" #"https://poe.ninja/poe1/api/economy/temp2/overview" ?
    POE2_CURRENCY_API_URL = "https://poe.ninja/poe2/api/economy/temp2/overview"

    api_url = POE2_CURRENCY_API_URL if game == 2 else POE1_CURRENCY_API_URL
    cache_file = Path(f"currency{game}.yaml")

    data: dict = {}
    # If cache file exists, and either is less than one hour old or if autoupdate is false, 
    # load data from cache file. Currency API only updates every hour.
    if cache_file.exists() and (cache_file.stat().st_mtime > (time.time() - 1 * S_IN_HOUR) 
                                or autoupdate is False):
        try:
            with cache_file.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except (yaml.YAMLError, FileNotFoundError) as e:
            print(f"Error reading cache file: {e}", file=sys.stderr)

        if "core" not in data:
            print("Error: Cache file is missing data.", file=sys.stderr)
    # Otherwise fetch from API
    else:
        response: requests.Response = requests.Response()
        try:
            response = requests.get(
                api_url,
                params={"leagueName": league, "overviewName": "Currency"},
                timeout=10
            )
            response.raise_for_status()
        except requests.HTTPError as e:
            print(f"HTTP error fetching prices from poe.ninja: {e}", file=sys.stderr)
        except requests.RequestException as e:
            print(f"Error fetching prices from poe.ninja: {e}", file=sys.stderr)

        data = response.json()

        # Save data to cache file if data is valid
        if "core" in data:
            try:
                with cache_file.open("w", encoding="utf-8") as f:
                    yaml.safe_dump(data, f)
            except (yaml.YAMLError, UnicodeDecodeError) as e:
                print(f"Error writing to cache file: {e}", file=sys.stderr)

    file_mtime = cache_file.stat().st_mtime
    time_diff = time.time() - file_mtime
    diff_hours = int(time_diff // S_IN_HOUR)
    diff_mins = int((time_diff % S_IN_HOUR) // 60)
    print(f"Currency data last updated: {diff_hours}h:{diff_mins:02d}m ago ({time.ctime(file_mtime)})")
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
        else:
            # Otherwise, treat it as a regular character key
            return KeyCode.from_char(key_str)
    except Exception as e:
        raise ValueError(f"Invalid key string: {key_str}") from e

def on_release(key: Key | KeyCode | None, rightclick_key: Key | KeyCode, calcprice_key: Key | KeyCode,
               exit_key: Key | KeyCode, adjustment_factor: float) -> bool:
    """Handle pynput key release events.

    Args:
        key (Key | KeyCode | None): The released key.
        rightclick_key (Key | KeyCode): The key to send right-click.
        calcprice_key (Key | KeyCode): The key to activate price calculation + replacement.
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
                pyautogui.rightClick() # this doesn't work on Windows, untested on other platforms

        elif isinstance(key, (Key, KeyCode)) and key == calcprice_key:
            # Copy (pre-selected) price to the clipboard
            # use pyautogui because it sends keys faster
            pyautogui.hotkey('ctrl', 'c')

            try:
                current_price: int | None = int(pyperclip.paste())
            except ValueError:
                current_price: int | None = None

            # If the clipboard does not contain a valid integer or is 1 or less, do nothing
            if current_price is None or current_price <= 1:
                return True
            else:
                # Calculate the new discounted price
                new_price: int = int(current_price * adjustment_factor)

                # Have to press backspace first because of PoE paste bug with text selected
                pyautogui.press('backspace')

                # Paste the new price from clipboard
                pyperclip.copy(str(new_price))
                pyautogui.hotkey('ctrl', 'v')

        elif isinstance(key, (Key, KeyCode)) and key == exit_key:
            print("Exiting...")
            return False

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)

    return True

def main() -> int:
    """Check settings, fetch and print currency values, then start keyboard listener."""
    # Load settings from settings.yaml file.
    try:
        with open('settings.yaml') as f:
            settings: dict[str, dict[str, Any]] = yaml.safe_load(f)
    except FileNotFoundError:
        print("Error: settings.yaml not found. Exiting.", file=sys.stderr)
        return 1

    # Attempt to turn key strings from settings yaml into Key or KeyCode objects as appropriate
    try:
        rightclick_key: Key | KeyCode = keyorkeycode_from_str(settings['keys']['rightclick_key'])
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    try:
        calcprice_key: Key | KeyCode = keyorkeycode_from_str(settings['keys']['calcprice_key'])
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    try:
        exit_key: Key | KeyCode = keyorkeycode_from_str(settings['keys']['exit_key'])
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    try:
        adjustment_factor: float = float(settings['logic']['adjustment_factor'])
    except (ValueError, TypeError):
        print(f"Error: Invalid adjustment factor value {settings['logic']['adjustment_factor']} in settings.yaml.", file=sys.stderr)
        return 1

    try:
        game: int = int(settings['currency']['game'])
        if game not in (1, 2):
            raise ValueError("Game must be 1 (PoE1) or 2 (PoE2).")
    except (ValueError, TypeError):
        print(f"Error: Invalid value for game {settings['currency']['game']} in settings.yaml.", file=sys.stderr)
        return 1

    print(f"PoEMarcut running. Press '{rightclick_key}' or right-click with item hovered to open "
          f"dialog, then press '{calcprice_key}' to adjust price. Press '{exit_key}' to exit program.")
    print("================================")

    # Fetch currency values
    data = get_currency_values(game=game, league=settings['currency']['league'], 
                                        autoupdate=settings['currency']['autoupdate'])
    # If if data object is valid, print currency values for suggested new price
    if "core" in data:
        annul_div_val = next(item for item in data.get("lines", []) if item.get("id") == "annul")["primaryValue"]
        div_chaos_val = data["core"]["rates"]["chaos"]
        div_exalt_val = data["core"]["rates"]["exalted"]

        print("Suggested new currency setting if current setting is 1, based on current values:")
        print(f"{adjustment_factor}x 1 Divine Orb")
        print(f" = {int(1/annul_div_val*adjustment_factor)} Orb of Annulment ({1/annul_div_val*adjustment_factor:.2f})")
        print(f" = {int(div_chaos_val*adjustment_factor)} Chaos Orb ({div_chaos_val*adjustment_factor:.2f})")
        print(f" = {int(div_exalt_val*adjustment_factor)} Exalted Orb ({div_exalt_val*adjustment_factor:.2f})")
        print(f"{adjustment_factor}x 1 Orb of Annulment")
        print(f" = {int(div_chaos_val*annul_div_val*adjustment_factor)} Chaos Orb ({div_chaos_val*annul_div_val*adjustment_factor:.2f})")
        print(f" = {int(div_exalt_val*annul_div_val*adjustment_factor)} Exalted Orb ({div_exalt_val*annul_div_val*adjustment_factor:.2f})")
        print(f"{adjustment_factor}x 1 Chaos Orb")
        print(f" = {int(div_exalt_val*1/div_chaos_val*adjustment_factor)} Exalted Orb ({div_exalt_val*1/div_chaos_val*adjustment_factor:.2f})", end="")
        if div_exalt_val > 500:
            print("... but you should really vendor it")
        else:
            print("")
        print(f"{adjustment_factor}x 1 Exalted Orb")
        print(" = Just vendor it already!")

    # Start pynput keyboard listener
    # have to suppress type check because pynput Listener does not follow its own type hint
    with Listener(on_release=lambda event: on_release(event, rightclick_key, calcprice_key, exit_key, 
                                                      adjustment_factor)) as listener: # type: ignore
        listener.join()

    return 0

if __name__ == "__main__":
    sys.exit(main())
