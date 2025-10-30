# PoE Marcut (Path of Exile 1 and 2 Market Cut)
You log in to PoE for the day and you have a bunch of unsold items in your merchant tabs.

Are you going to price check every single one of them again? No way, total waste of time.

Instead, quickly adjust each item downward by a set percentage using PoEMarcut. Repeat next time until they sell or they reach nothing and you vendor them.

## Usage
1. Run `poemarcut`. It will run in the background.
2. Hover your mouse cursor over an item in a merchant tab.
3. Press `F2` (default) or `right-click` to open the item price dialog.
4. Press `F3` (default) to adjust the price text downward by 0.9x (default) and close the dialog.
   
Press `F6` (default) to exit the tool when desired.

The new price is always rounded down (decimal is truncated), to ensure the price is always reduced, even when the existing price is `2` (which will become `1`).

An existing price of `1` will not be changed.

An optional setting `min_actual_factor` will prevent very low prices from being reduced further, eg `0.6` will prevent `2` from being reduced to `1` (0.5 actual, 0.6 minimum).

For use when existing price is `1`, a list of suggested new prices in less valuable currencies is printed to the terminal using current poe.ninja economy data.

## GGG TOS Compliance
100% [TOS policy compliant](https://www.pathofexile.com/developer/docs#policy) and legal. The tool is a simple keyboard macro that only performs one 'server action' per key press, following the policy.

## Installation / Running

Download and extract the zip from [Github Releases](https://github.com/cdrg/poemarcut/releases/latest) containing `poemarcut.exe` and `settings.yaml`. Run `poemarcut.exe`.

Alternatively [run the source from the command line](https://github.com/cdrg/poemarcut#running-from-the-command-line) with python.

## Settings
Settings such as hotkeys, price adjustment percentage, leagues, etc are contained in `settings.yaml`. 

This plain-text file can be edited with any text editor and contains descriptions of each setting.

## Links
[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/I2I7ROZFD)

[![patreon](https://github.com/user-attachments/assets/b7841f4d-5bcc-4642-a04c-2f22e5c48a24)](https://patreon.com/cdrpt)

[![discord](https://cdn.prod.website-files.com/6257adef93867e50d84d30e2/66e3d74e9607e61eeec9c91b_Logo.svg)](https://discord.gg/gRMjT5gVms)

## Credits
Inspired by the proof-of-concept by [@nickycakes](https://github.com/nickycakes/poe2price)

## Advanced

### Running from the command line
Recommend running with `poetry`, eg `poetry run python poemarcut.py`

- Download the repository via one of the options in the green Code button on Github (zip, clone, etc).

- Before first use, initialize poetry's venv by running `poetry install` in the repo directory.

- If needed, [install poetry](https://python-poetry.org/docs/) (via pipx) or use your own python venv of choice.

#### Full Windows instructions
1. Install Python 3.12 or 3.13 from the Microsoft Store app, if you don't already have it installed.
2. Open terminal
3. `python -m pip install --user pipx` to get pipx
4. `.\pipx.exe ensurepath`
5. `pipx install poetry` to get poetry
6. Download/clone source from github somewhere
7. `poetry install` to initialize poetry environment for the folder
8. `poetry run python poemarcut.py`

### Building
Run `poetry run build`.
