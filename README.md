# PoE Marcut (Path of Exile 1 and 2 Market Cut)

## Usage
1. Run `poemarcut`. It will run in the background.
2. Hover your mouse cursor over an item in a merchant tab
3. Press `F3` (default) or right-click to open the item price dialog.
4. Press `F4` (default) to adjust the price text downward by 0.9x (default)
5. Press `return` to set the price.
   
Press `F5` (default) to exit the tool when desired.

An existing price of `1` will not be changed.

For use when existing price is `1`, a list of suggested new prices in less valuable currencies is printed to the terminal using current economy data.

## GGG TOS Compliance
100% [TOS compliant](https://www.pathofexile.com/developer/docs#policy) and legal. The tool only performs one 'action' per key press.

## Running from the command line
Recommend running with `poetry`, eg `poetry run python poemarcut.py`

## Installation
Download the repository via one of the options in the green Code button on Github (zip, clone, etc).

Before first use, initialize poetry's venv by running `poetry install` in the repo directory.

If needed, [install poetry](https://python-poetry.org/docs/) (via pipx) or use your own python venv of choice.

## Settings
Settings such as hotkeys are contained in `settings.yaml`

## Links
[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/I2I7ROZFD)

[![patreon](https://github.com/user-attachments/assets/b7841f4d-5bcc-4642-a04c-2f22e5c48a24)](https://patreon.com/cdrpt)

[![discord](https://cdn.prod.website-files.com/6257adef93867e50d84d30e2/66e3d74e9607e61eeec9c91b_Logo.svg)](https://discord.gg/gRMjT5gVms)

## Credits
Inspired by the proof-of-concept by [@nickycakes](https://github.com/nickycakes/poe2price)