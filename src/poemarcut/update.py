"""Update checking functionality for PoEMarcut."""

import logging
import re

import requests

GITHUB_URL = "https://api.github.com/repos/cdrg/poemarcut/releases/latest"

logger = logging.getLogger(__name__)


def version_str_to_tuple(version_str: str) -> tuple:
    """Convert a version string into a tuple of ints for comparison.

    Args:
        version_str (str): the version string to convert

    """
    if not version_str:
        return ()
    v = version_str.lstrip("vV")
    parts = [p for p in re.split(r"[^0-9]+", v) if p != ""]
    try:
        return tuple(int(p) for p in parts)
    except ValueError:
        # Fallback: compare lexicographically if non-numeric
        return (v,)


def get_github_version() -> str | None:
    """Get the version of the latest github release.

    Returns:
        str | None: the version string of the latest release, or None on error

    """
    try:
        response = requests.get(GITHUB_URL, timeout=5)
        response.raise_for_status()
    except requests.RequestException:
        logger.exception("Error fetching current github version number")
        return None
    try:
        data = response.json()
    except (ValueError, requests.exceptions.JSONDecodeError):
        logger.exception("Error: No JSON in response while fetching github version number")
        return None
    remote_ver = data.get("tag_name") or data.get("name")

    if not remote_ver:
        return None
    return remote_ver
