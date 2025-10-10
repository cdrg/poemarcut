from typing import Dict, Any
import sys

import yaml
from pynput.keyboard import Key, KeyCode, Listener
import pyautogui
import pyperclip

def keyorkeycode_from_str(key_str: str) -> Key | KeyCode:
    """Convert a string representation of a key to a pynput Key or KeyCode.
    This is unfortunately necessary because pynput does not provide the from_char method for both."""
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
    """Handle key release events."""
    if key is None:
        return True

    try:
        if isinstance(key, (Key, KeyCode)) and key == rightclick_key:   
            # Right click to open price dialog
            pyautogui.rightClick()

        elif isinstance(key, (Key, KeyCode)) and key == calcprice_key:
            # Copy (pre-selected) price to the clipboard
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
            
                # Have to press backspace first because of PoE2 paste bug with text selected
                pyautogui.press('backspace')

                # Paste the new price from clipboard
                pyperclip.copy(str(new_price))
                pyautogui.hotkey('ctrl', 'v')
                
        elif isinstance(key, (Key, KeyCode)) and key == exit_key:
            print("Exiting...")
            return False
            
    except Exception as e:
        print(f"Error: {e}")
    
    return True

def main() -> int:
    # Load settings from settings.yaml file.
    try:
        with open('settings.yaml', 'r') as f:
            settings: Dict[str, Dict[str, Any]] = yaml.safe_load(f)
    except FileNotFoundError:
        print("Error: settings.yaml not found. Exiting.")
        return 1

    # Attempt to turn key strings from settings yaml into Key or KeyCode objects as appropriate
    try:
        rightclick_key: Key | KeyCode = keyorkeycode_from_str(settings['keys']['rightclick_key'])
    except ValueError as e:
        print(f"Error: {e}")
        return 1
    try:
        calcprice_key: Key | KeyCode = keyorkeycode_from_str(settings['keys']['calcprice_key'])
    except ValueError as e:
        print(f"Error: {e}")
        return 1
    try:
        exit_key: Key | KeyCode = keyorkeycode_from_str(settings['keys']['exit_key'])
    except ValueError as e:
        print(f"Error: {e}")
        return 1

    try:
        adjustment_factor: float = float(settings['logic']['adjustment_factor'])
    except (ValueError, TypeError):
        print(f"Error: Invalid adjustment factor value {settings['adjustment_factor']} in settings.yaml.")
        return 1
    
    print(f"PoE2Marcut running. Press '{rightclick_key}' or right-click with item hovered to open "
          f"dialog, then press '{calcprice_key}' to adjust price. Press '{exit_key}' to exit.")

    # Start pynput keyboard listener
    # have to suppress type check because pynput Listener does not follow its own type hint
    with Listener(on_release=lambda event: on_release(event, rightclick_key, calcprice_key, exit_key, adjustment_factor)) as listener: # type: ignore
        listener.join()

    return 0

if __name__ == "__main__":
    sys.exit(main())