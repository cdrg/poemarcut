"""Currency economy data handling functions for PoEMarcut."""

import logging
import time
from pathlib import Path

import requests
import yaml

from poemarcut import __version__, settings
from poemarcut.constants import S_IN_HOUR

USER_AGENT = "poemarcut/" + __version__ + " (+https://github.com/cdrg/poemarcut)"

# poe.ninja has custom aliases for currently active leagues and events.
# These are not official and will not work on pathofexile.com endpoints.
POENINJA_LEAGUE_IDS = {"tmpStandard", "tmpHardcore", "eventStandard", "eventHardcore"}

# Official endpoints that return the list of active trade leagues.
# An alternative URL is https://www.pathofexile.com/api/league?realm=poe2 which also includes non-trade leagues.
POE1_LEAGUES_API_URL = "https://www.pathofexile.com/api/trade/data/leagues"
POE2_LEAGUES_API_URL = "https://www.pathofexile.com/api/trade2/data/leagues"

# poe.ninja repackages the GGG currency exchange API. Same interface for both games.
POE1_CURRENCY_API_URL = "https://poe.ninja/poe1/api/economy/exchange/current/overview"
POE2_CURRENCY_API_URL = "https://poe.ninja/poe2/api/economy/exchange/current/overview"


logger = logging.getLogger(__name__)


class CurrencyStore:
    """Store of currency economy data by official league name.

    GGG only updates the currency exchange API once per hour.
    """

    def __init__(self) -> None:
        """Initialize the store."""
        self.currency_data_by_league: dict[str, dict] = {}
        self.last_updated: float = 0.0

    def get_data(self, game: int, league: str, *, update: bool) -> dict:
        """Return the currency data for the specified game and league."""
        if game not in (1, 2):
            msg = "Invalid game, must be 1 or 2"
            raise ValueError(msg)

        self.currency_data_by_league[league] = _retrieve_currency_prices(game, league, update=update)

        return self.currency_data_by_league[league]


def _retrieve_currency_prices(game: int, league: str, *, update: bool = True) -> dict:  # noqa: C901
    """Fetch currency prices from cache file or poe.ninja currency API.

    GGG only updates the currency exchange API once per hour, so there's no reason to fetch more often than that.

    Args:
        game (int): The game version, either 1 (PoE1) or 2 (PoE2).
        league (str): The league name to fetch currency prices for.
        update (bool): Whether to fetch new prices from API if cache file is older than one hour.

    Returns:
        dict: The poe.ninja currency API response as a dict. mtime is added to the response dict.

    """
    cache_file = Path(f"{league}-{game}.yaml")

    data: dict = {}

    logger.info("Fetching currency prices for PoE%s '%s' (update=%s)...", game, league, update)
    # Try cache file first. GGG currency exchange API data updates only hourly, so no need to fetch more often than that.
    try:
        cache_mtime: float = cache_file.stat().st_mtime if cache_file.exists() else 0
    except OSError:
        cache_mtime = 0

    # Fetch from cache file if it exists and is less than one hour old, or if updating is disabled.
    if cache_mtime and (cache_mtime > (time.time() - S_IN_HOUR) or update is False):
        try:
            with cache_file.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except (yaml.YAMLError, FileNotFoundError):
            logger.exception("Error reading cache file")
            data = {}

        # Check if cache data is valid by verifying primary currency exists in lines.
        # If valid, add mtime to data and return. If not, will proceed to attempt to fetch from API.
        primary = data.get("core", {}).get("primary")
        if "lines" in data and primary is not None and any(line.get("id") == primary for line in data.get("lines", [])):
            data["mtime"] = cache_mtime
            logger.info(
                "Currency prices for PoE%s '%s' retrieved from cache (cache age: %.1f minutes)",
                game,
                league,
                (time.time() - cache_mtime) / 60,
            )
            return data
        if update is False:
            logger.error(
                "Cache file for PoE%s league '%s' is invalid, but update is disabled. Returning empty data.",
                game,
                league,
            )
            return {}

    # Fetch from API if not fetched from cache file
    response: requests.Response | None = None
    headers = {"User-Agent": USER_AGENT}
    try:
        if game == 1:
            response = requests.get(
                POE1_CURRENCY_API_URL,
                params={"league": league, "type": "Currency"},
                headers=headers,
                timeout=10,
            )
        elif game == 2:  # noqa: PLR2004
            response = requests.get(
                POE2_CURRENCY_API_URL,
                params={"league": league, "type": "Currency"},
                headers=headers,
                timeout=10,
            )
        else:
            msg = f"Invalid game '{game}', must be 1 or 2"
            raise ValueError(msg)
        response.raise_for_status()
    except requests.RequestException:
        logger.exception("Error fetching prices from poe.ninja")
        response = None

    try:
        data = response.json() if response is not None else {}
    except (ValueError, requests.exceptions.JSONDecodeError):
        logger.exception("Error parsing JSON from poe.ninja response")
        data = {}

    if "lines" not in data or "core" not in data or data["core"].get("primary") is None:
        logger.error("Invalid data received from API for PoE%s '%s': %s", game, league, data)
        return data

    try:
        with cache_file.open("w", encoding="utf-8") as f:
            yaml.safe_dump(data, f)
    except (yaml.YAMLError, UnicodeDecodeError):
        logger.exception("Error writing to cache file")

    data["mtime"] = cache_file.stat().st_mtime if cache_file.exists() else time.time()
    logger.info("Currency prices for PoE%s league '%s' retrieved from poe.ninja API and cached", game, league)
    return data


def get_leagues(game: int) -> set[str] | None:
    """Get the list of available trade leagues for the specified game.

    API response is in the format:
    {"result":[{"id":"Standard","realm":"pc","text":"Standard"},...]}

    Args:
        game (int): The game version, either 1 (PoE1) or 2 (PoE2).

    Returns:
        set[str]: A set of available trade leagues for the specified game.

    """
    logger.info("Fetching list of leagues for PoE%s from GGG trade API...", game)
    response: requests.Response | None = None
    headers = {"User-Agent": USER_AGENT}
    try:
        if game == 1:
            response = requests.get(
                POE1_LEAGUES_API_URL,
                headers=headers,
                timeout=10,
            )
        elif game == 2:  # noqa: PLR2004
            response = requests.get(
                POE2_LEAGUES_API_URL,
                headers=headers,
                timeout=10,
            )
        else:
            msg = f"Invalid game '{game}', must be 1 or 2"
            raise ValueError(msg)
        response.raise_for_status()
    except requests.RequestException:
        logger.exception("Error fetching prices from poe.ninja")
        response = None

    try:
        data = response.json() if response is not None else {}
    except (ValueError, requests.exceptions.JSONDecodeError):
        logger.exception("Error parsing JSON from poe.ninja response")
        data = {}

    if "result" not in data:
        logger.error("Invalid data received from API for PoE%s: %s", game, data)
        return None

    logger.info("Successfully fetched leagues for PoE%s: %s", game, {item.get("id") for item in data.get("result", [])})
    # Only return ids of 'pc' (PoE1)/'poe2' leagues, we are not interested in realm or full text
    if game == 1:
        return {item.get("id") for item in data.get("result", []) if item.get("realm") == "pc"}
    return {item.get("id") for item in data.get("result", []) if item.get("realm") == "poe2"}


def get_currency_value(game: int, league: str, currency_name: str) -> tuple[float, str]:
    """Get the value of a specified currency for the specified game and league.

    Args:
        game (int): The game, either 1 (PoE1) or 2 (PoE2).
        league (str): The league name to fetch currency prices for.
        currency_name (str): The currency id, detailsId, or name to fetch values for.

    Returns:
        tuple[float, str]: A tuple containing the primary value and primary currency for the specified currency.

    """
    data = store.get_data(game=game, league=league, update=settings.settings_manager.settings.currency.autoupdate)
    primary_value: float = next(
        (float(cur.get("primaryValue")) for cur in data.get("lines", []) if cur.get("id") == currency_name), 0.0
    )
    if primary_value == 0.0:
        msg = f"Currency '{currency_name}' not found for league '{league}'"
        raise LookupError(msg)
    primary_currency: str = data.get("core", {}).get("primary", "")
    return primary_value, primary_currency


def get_exchange_rate(game: int, league: str, from_currency: str, to_currency: str) -> float:
    """Return the exchange rate from `from_currency` to `to_currency` for the given league.

    The rate returned is how many units of `to_currency` equal one unit of `from_currency`.

    For example, if `from_currency` is "divine" and `to_currency` is "chaos", and the current price
    of a divine orb is 100 chaos, this function would return 100. If reversed, it would return 0.01.

    Each currency's poe.ninja `primaryValue` (value in the response primary
    currency) is used to compute: rate = primaryValue(from) / primaryValue(to).

    Args:
        game: 1 or 2 for PoE1/PoE2.
        league: official league name (matches cache filename).
        from_currency: currency id, detailsId, or name for the source currency.
        to_currency: currency id, detailsId, or name for the target currency.

    Raises:
        ValueError: if currencies are not found or values are invalid.

    Returns:
        float: number of `to_currency` units equal to one `from_currency` unit.

    """
    data = store.get_data(game, league, update=settings.settings_manager.settings.currency.autoupdate)
    lines: list[dict] | None = data.get("lines")
    if not lines:
        msg = f"No currency data available for league '{league}'"
        raise LookupError(msg)

    from_cur_data = next((cur for cur in lines if cur.get("id") == from_currency), None)
    to_cur_data = next((cur for cur in lines if cur.get("id") == to_currency), None)
    if from_cur_data is None:
        msg = f"Currency '{from_currency}' not found for league '{league}'"
        raise ValueError(msg)
    if to_cur_data is None:
        msg = f"Currency '{to_currency}' not found for league '{league}'"
        raise ValueError(msg)

    from_primary_value = from_cur_data.get("primaryValue")
    to_primary_value = to_cur_data.get("primaryValue")
    if from_primary_value is None:
        msg = f"Invalid primaryValue for {from_currency}"
        raise ValueError(msg)
    if to_primary_value is None:
        msg = f"Invalid primaryValue for {to_currency}"
        raise ValueError(msg)
    try:
        from_f = float(from_primary_value)
        to_f = float(to_primary_value)
    except (TypeError, ValueError):
        msg = "Invalid primaryValue for one of the currencies"
        raise ValueError(msg) from None

    if to_f == 0:
        msg = "Division by zero: target currency has primaryValue 0"
        raise ValueError(msg)

    return from_f / to_f


def get_update_time(game: int, league: str) -> float:
    """Get the last update time for the currency data of the specified game and league.

    Args:
        game (int): The game version, either 1 (PoE1) or 2 (PoE2).
        league (str): The league name.

    Returns:
        float: The last update time as a Unix timestamp (mtime).

    Throws:
        TypeError: If the mtime in the currency data is missing or not a valid number.

    """
    data = store.get_data(game=game, league=league, update=settings.settings_manager.settings.currency.autoupdate)
    mtime = data.get("mtime")
    if not isinstance(mtime, (int, float)):
        msg = f"Invalid or missing mtime in currency data for league '{league}'"
        raise TypeError(msg)
    return mtime


# Module-level singleton for callers that prefer the manager pattern.
store = CurrencyStore()
