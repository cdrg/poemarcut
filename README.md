# PoE2 Marcut (Path of Exile 2 Market Cut)

## Usage
1. Run `poe2marcut`. It will run in the background.
2. Hover your mouse cursor over an item in a merchant tab
3. Press `F3` (default) or right-click to open the item price dialog.
4. Press `F4` (default) to adjust the price text downward by 0.9x (default)
5. Press `return` to set the price.
   
Press `F5` (default) to exit the tool when desired.

An existing price of `1` will not be changed. Upcoming: a suggested price in less valuable currencies will be printed to the terminal, using economy data.

## GGG TOS Compliance
100% [TOS compliant](https://www.pathofexile.com/developer/docs#policy) and legal. The tool only performs one 'action' per key press.

## Running from the command line
Recommend running with `poetry`, eg `poetry run python poe2marcut.py`

## Installation
Before first use, initialize poetry's venv by running `poetry install` in the script directory.

[Install poetry](https://python-poetry.org/docs/) (via pipx) if needed or use your own python venv of choice.

## Settings
Settings such as hotkeys are contained in `settings.yaml`

## Credits
Inspired by the proof-of-concept by [@nickycakes](https://github.com/nickycakes/poe2price)