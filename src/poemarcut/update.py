"""Update checking functionality for PoEMarcut."""

import logging
import re

import requests

from poemarcut import __version__

GITHUB_RELEASE_URL = "https://github.com/cdrg/poemarcut/releases/latest"
GITHUB_RELEASES_API_URL = "https://api.github.com/repos/cdrg/poemarcut/releases/latest"

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
    """Get the version of the latest GitHub release.

    Returns:
        str | None: the version string of the latest release, or None on error

    """
    try:
        response = requests.get(GITHUB_RELEASES_API_URL, timeout=5)
        response.raise_for_status()
    except requests.RequestException:
        logger.exception("Error fetching current GitHub version number")
        return None
    try:
        data = response.json()
    except (ValueError, requests.exceptions.JSONDecodeError):
        logger.exception("Error: No JSON in response while fetching GitHub version number")
        return None
    remote_ver = data.get("tag_name") or data.get("name")

    if not remote_ver:
        return None
    return remote_ver


def is_github_update_available() -> tuple[bool, str | None]:
    """Check the latest GitHub release for a newer version and return a tuple indicating if an update is available and the latest version.

    Returns:
        tuple[bool, str | None]: A tuple where the first element is a boolean indicating if an update is available, and the second element is the latest version string or None if no update is available.

    """
    logger.info("Checking for updates on GitHub...")
    github_version = get_github_version()
    if not github_version:
        return False, None

    remote_vt: tuple = version_str_to_tuple(str(github_version))
    local_vt: tuple = version_str_to_tuple(str(__version__))

    # If parsing produced non-empty tuples and remote > local, return True, otherwise False
    update_available = bool(remote_vt and local_vt and remote_vt > local_vt)
    if update_available:
        logger.info("GitHub update available: %s", github_version)
    else:
        logger.info("No GitHub update available")
    return update_available, github_version
