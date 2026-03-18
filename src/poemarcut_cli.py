# ruff: noqa: T201 # disable print() warning since this is the CLI
"""Tool to quickly reprice Path of Exile 1/2 merchant tab items.

Also works for stash tab items, but you'll have to select the price text yourself.

On start, prints a list of suggested new prices for 1-unit currency items based on current poe.ninja currency prices.
"""

import logging
import sys
import time

from poemarcut import currency, keyboard, settings, update
from poemarcut.__init__ import __version__
from poemarcut.constants import BOLD, RESET, S_IN_HOUR


def print_last_updated(game: int, league: str, file_mtime: float) -> None:
    """Print when the currency data was last updated from the cache file.

    Args:
        game (int): The game version, either 1 (PoE1) or 2 (PoE2).
        league (str): The league name.
        file_mtime (float): The mtime of the cache file.

    Returns:
        None

    """
    time_diff = time.time() - file_mtime
    diff_hours = int(time_diff // S_IN_HOUR)
    diff_mins = int((time_diff % S_IN_HOUR) // 60)
    print(
        f"(PoE{game} currency data for '{league}' last updated: {diff_hours}h:{diff_mins:02d}m ago ({time.ctime(file_mtime)}))"
    )


def print_poe1_currency_suggestions(discount_percent: int, data: dict) -> None:
    """Print suggested new currency prices for PoE1 based on current poe.ninja currency values.

    Args:
        discount_percent (float): The discount percent to apply (0-100).
        data (dict): The currency data fetched from poe.ninja.

    Returns:
        None

    """
    if "lines" in data and "core" in data and data["core"].get("primary"):
        if data["core"]["primary"] == "chaos" and data["core"].get("rates") and data["core"]["rates"].get("divine"):
            chaos_div_val: float = data["core"]["rates"]["divine"]
        elif data["core"]["primary"] == "divine" and data["core"].get("rates") and data["core"]["rates"].get("chaos"):
            chaos_div_val: float = 1 / data["core"]["rates"]["chaos"]
        elif any((item.get("id") == "chaos") for item in data.get("lines", [])):
            chaos_div_val: float = next(item for item in data.get("lines", []) if item.get("id") == "chaos")[
                "primaryValue"
            ]
        else:
            print("Error: Invalid data, could not determine currency suggestions for PoE1.", file=sys.stderr)
            return

        div_chaos_adj: float = 1 / chaos_div_val * (1.0 - (discount_percent / 100.0))
        print(f"{BOLD}PoE1{RESET} suggested new currency setting if current setting is 1, based on current values:")
        print(f"{discount_percent:.2f}% off ({(1.0 - discount_percent / 100.0):.2f}x) 1 Divine Orb")
        print(f" = {int(div_chaos_adj)} Chaos Orb ({div_chaos_adj:.2f})")
        print(f"{(1.0 - discount_percent / 100.0):.2f}x 1 Chaos Orb")
        print(" = Just vendor it already!")
    else:
        print("Error: Invalid data, could not determine currency suggestions for PoE1.", file=sys.stderr)


def print_poe2_currency_suggestions(discount_percent: int, data: dict) -> None:
    """Print suggested new currency prices for PoE2 based on current poe.ninja currency values.

    Some calculations are inverted depending on if poe.ninja provides "div per X" or "X per div".

    Args:
        discount_percent (float): The discount percent to apply (0-100).
        data (dict): The currency data fetched from poe.ninja.

    Returns:
        None

    """  # Compute multiplier from discount_percent inline where needed
    if (
        "lines" in data
        and "core" in data
        and data["core"].get("primary")
        and any((item.get("id") == "annul") for item in data.get("lines", []))
        and any((item.get("id") == "chaos") for item in data.get("lines", []))
        and any((item.get("id") == "exalted") for item in data.get("lines", []))
    ):
        annul_div_val: float = next(item for item in data.get("lines", []) if item.get("id") == "annul")["primaryValue"]
        chaos_div_val: float = next(item for item in data.get("lines", []) if item.get("id") == "chaos")["primaryValue"]
        exalt_div_val: float = next(item for item in data.get("lines", []) if item.get("id") == "exalted")[
            "primaryValue"
        ]

        div_annul_adj: float = 1 / annul_div_val * (1.0 - (discount_percent / 100.0))
        div_chaos_adj: float = 1 / chaos_div_val * (1.0 - (discount_percent / 100.0))
        div_exalt_adj: float = 1 / exalt_div_val * (1.0 - (discount_percent / 100.0))
        annul_chaos_adj: float = 1 / chaos_div_val * annul_div_val * (1.0 - (discount_percent / 100.0))
        annul_exalt_adj: float = 1 / exalt_div_val * annul_div_val * (1.0 - (discount_percent / 100.0))
        chaos_exalt_adj: float = 1 / exalt_div_val * chaos_div_val * (1.0 - (discount_percent / 100.0))
        print(f"{BOLD}PoE2{RESET} suggested new currency setting if current setting is 1, based on current values:")
        print(f"{discount_percent:.2f}% off ({(1.0 - discount_percent / 100.0):.2f}x) 1 Divine Orb")
        print(f" = {int(div_annul_adj)} Orb of Annulment ({div_annul_adj:.2f})")
        print(f" = {int(div_chaos_adj)} Chaos Orb ({div_chaos_adj:.2f})")
        print(f" = {int(div_exalt_adj)} Exalted Orb ({div_exalt_adj:.2f})")
        print(f"{discount_percent:.2f}% off ({(1.0 - discount_percent / 100.0):.2f}x) 1 Orb of Annulment")
        print(f" = {int(annul_chaos_adj)} Chaos Orb ({annul_chaos_adj:.2f})")
        print(f" = {int(annul_exalt_adj)} Exalted Orb ({annul_exalt_adj:.2f})")
        print(f"{discount_percent:.2f}% off ({(1.0 - discount_percent / 100.0):.2f}x) 1 Chaos Orb")
        print(
            f" = {int(chaos_exalt_adj)} Exalted Orb ({chaos_exalt_adj:.2f})",
            end="",
        )
        print()
        print(f"{discount_percent:.2f}% off ({(1.0 - discount_percent / 100.0):.2f}x) 1 Exalted Orb")
        print(" = Just vendor it already!")
    else:
        print("Error: Invalid data, could not determine currency suggestions for PoE2.", file=sys.stderr)


def main() -> int:  # noqa: C901, PLR0915
    """Read settings from file, fetch and print currency values, then start keyboard listener.

    Returns:
        int: Process exit code (0 for success).

    """
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),  # Output to console
        ],
    )

    settings_man: settings.SettingsManager = settings.settings_manager
    # Parsed binding tuples from keyboard.keyorkeycode_from_str
    keys: dict[str, tuple[str, object]] = {
        k: keyboard.keyorkeycode_from_str(key_str=v) for k, v in settings_man.settings.keys.model_dump().items()
    }

    def _binding_to_str(binding: tuple[str, object]) -> str:
        """Format a keyboard binding tuple as a readable string.

        Args:
            binding (tuple[str, object]): A tuple of binding type and value.

        Returns:
            str: Human-readable representation of the binding.

        """
        t, v = binding
        if t == "special":
            return str(v)
        if t == "char":
            return str(v)
        if t == "vk":
            return f"vk:{v}"
        if t == "scan":
            return f"scan:{v}"
        return str(binding)

    def _print_instructions() -> None:
        """Print user-facing keyboard instructions to the console.

        Returns:
            None

        """
        print("> PoEMarcut running <")
        print(
            f'Press "{_binding_to_str(binding=keys["copyitem_key"])}" or "ctrl+shift+c" with item hovered to copy to clipboard, then... '
        )
        print(
            f'Press "{_binding_to_str(binding=keys["rightclick_key"])}" or "right-click" with item hovered to open dialog, then... '
        )
        print(f'Press "{_binding_to_str(binding=keys["calcprice_key"])}" to adjust price')
        if not settings_man.settings.currency.autoupdate:
            print(f'press "{_binding_to_str(binding=keys["enter_key"])}" or "enter" to set the new price.')
        print(f'Press "{_binding_to_str(binding=keys["stop_key"])}" to exit the program.')
        print("================================")

    _print_instructions()

    def _print_currency_suggestions(discount_percent: int) -> None:
        """Fetch and print currency suggestions for supported games.

        Args:
            discount_percent (float): Discount percent used to compute suggested prices.

        Returns:
            None

        """
        games: list[int] = [1, 2]
        for game in games:
            league = (
                next(iter(settings_man.settings.currency.poe1leagues))
                if game == 1
                else next(iter(settings_man.settings.currency.poe2leagues))
            )
            try:
                data = currency.store.get_data(
                    game=game, league=league, update=settings_man.settings.currency.autoupdate
                )
            except (LookupError, ValueError, OSError):
                print(f"Error: Could not retrieve currency data for PoE{game} ({league}).", file=sys.stderr)
                data = {}
            print_last_updated(game=game, league=league, file_mtime=data.get("mtime", 0))

            # If data object is valid, print suggested currency values for case where current price is 1
            if game == 1 and "lines" in data and "core" in data and data["core"].get("primary"):
                print_poe1_currency_suggestions(discount_percent=discount_percent, data=data)
                print()
            elif game == 2 and "lines" in data and "core" in data and data["core"].get("primary"):  # noqa: PLR2004
                print_poe2_currency_suggestions(discount_percent=discount_percent, data=data)
                print()
            else:
                print(f"Error: Could not retrieve currency suggestions for PoE{game}.", file=sys.stderr)
                print()

        update_available, github_version = update.is_github_update_available()
        if update_available and github_version:
            print(
                f"{BOLD}A newer version of PoEMarcut is available{RESET} at https://github.com/cdrg/poemarcut: {github_version} (you have {__version__})"
            )

    _print_currency_suggestions(discount_percent=settings_man.settings.logic.discount_percent)

    keyboard.start_listener(blocking=True)

    # Ensure singleton-managed listener is stopped/cleaned up (no-op if already stopped)
    try:
        keyboard.stop_listener()
    except (RuntimeError, OSError):
        logging.getLogger(__name__).exception("Error while stopping keyboard listener on exit.")

    print("Exiting PoEMarcut...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
