"""Currency value handling functions for PoEMarcut."""

import logging
import time
from pathlib import Path

import requests
import yaml

from poemarcut import __version__
from poemarcut.constants import POE1_CURRENCY_API_URL, POE2_CURRENCY_API_URL, S_IN_HOUR

logger = logging.getLogger(__name__)


def get_currency_values(game: int, league: str, *, update: bool = True) -> tuple[dict, float]:
    """Fetch currency prices from cache file or poe.ninja currency API.

    GGG only updates the currency exchange API once per hour, so there's no reason to fetch more often than that.

    Args:
        game (int): The game version, either 1 (PoE1) or 2 (PoE2).
        league (str): The league name to fetch currency prices for.
        update (bool): Whether to fetch new prices from API if cache file is older than one hour.

    Returns:
        Tuple: The poe.ninja currency API response as a dict and the cache file modification time as a float.

    """
    cache_file = Path(f"{league}.yaml")

    data: dict = {}

    # Try cache file first. GGG currency exchange API data updates only hourly, so no need to fetch more often than that
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

        if "lines" in data and any(item.get("core", {}).get("primary") is not None for item in data.get("lines", [])):
            return data, cache_mtime

    # Fetch from API if not fetched from cache file
    response: requests.Response | None = None
    headers = {"User-Agent": "poemarcut/" + __version__ + " (+https://github.com/cdrg/poemarcut)"}
    try:
        if game == "1":
            response = requests.get(
                POE1_CURRENCY_API_URL,
                params={"league": league, "type": "Currency"},
                headers=headers,
                timeout=10,
            )
        else:
            response = requests.get(
                POE2_CURRENCY_API_URL,
                params={"league": league, "type": "Currency"},
                headers=headers,
                timeout=10,
            )
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
        return data, 0

    try:
        with cache_file.open("w", encoding="utf-8") as f:
            yaml.safe_dump(data, f)
    except (yaml.YAMLError, UnicodeDecodeError):
        logger.exception("Error writing to cache file")

    file_mtime = cache_file.stat().st_mtime

    return data, file_mtime
