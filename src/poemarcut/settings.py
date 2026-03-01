"""Get and save settings for PoEMarcut.

Defines default settings and settings file location.
"""

import logging
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError
from pydantic_yaml import parse_yaml_file_as, to_yaml_file
from yaml import YAMLError

logger = logging.getLogger(__name__)


SETTINGS_FILE = Path.cwd() / "settings.yaml"


class KeySettings(BaseModel):
    """Keyboard hotkey settings."""

    copyitem_key: str = Field(
        default="f1",
        description="Copies the ctrl+atl+c text of the hovered item in the stash/market tab, including the price and currency type",
    )
    rightclick_key: str = Field(
        default="f2", description="'right-click' opens the item price dialog in market/stash tabs"
    )
    calcprice_key: str = Field(
        default="f3",
        description="Copies the old price, calculates new, and pastes new price into the dialog (and optionally presses 'enter')",
    )
    enter_key: str = Field(default="f4", description="'enter' key confirms the new price in the dialog")
    exit_key: str = Field(
        default="f6", description="Exit the program. Many tools use f5 for '/hideout', so f6 is default"
    )


class LogicSettings(BaseModel):
    """Logic and calculation settings for price adjustments."""

    adjustment_factor: float = Field(
        default=0.9,
        gt=0,
        description="The factor by which to multiply the current price to get the new price. For example, 0.9 would discount the current price by 10%",
    )
    min_actual_factor: float = Field(
        default=0.5,
        gt=0,
        description="The minimum allowed actual adjustment factor. If the calculated adjustment factor is less than this, the price will not be adjusted",
    )
    enter_after_calcprice: bool = Field(
        default=True,
        description="Whether to press 'enter' to close the dialog and set the new price after calculating and pasting",
    )


class GameSettings(BaseModel):
    """Which game to fetch currency values for."""

    game: int = Field(
        default=1,
        ge=1,
        le=2,
        description="The game to output currency values for, '1' (PoE1) or '2' (PoE2)",
    )


class CurrencySettings(BaseModel):
    """Currency update settings."""

    autoupdate: bool = Field(
        default=True,
        description="Whether to automatically fetch up-to-date currency values. If false, will only use cached/manually set values",
    )
    games: list[GameSettings] = Field(
        default=[GameSettings(game=1), GameSettings(game=2)],
        description="The game(s) to output currency values for",
    )
    poe1league: str = Field(default="Mirage", description="The PoE1 league to fetch currency values for")
    poe2league: str = Field(default="Fate of the Vaal", description="The PoE2 league to fetch currency values for")


class PoEMSettings(BaseModel):
    """Settings for PoEMarcut."""

    keys: KeySettings
    logic: LogicSettings
    currency: CurrencySettings


def get_settings() -> PoEMSettings:
    """Get PoEMSettings from settings.yaml, or return default settings if file is missing or invalid."""
    try:
        with SETTINGS_FILE.open() as f:
            settings: PoEMSettings = parse_yaml_file_as(PoEMSettings, f)
    except (YAMLError, ValidationError):
        logger.exception("Error reading settings from file, using default settings")
        # return default settings
        settings: PoEMSettings = PoEMSettings(keys=KeySettings(), logic=LogicSettings(), currency=CurrencySettings())
    except FileNotFoundError:
        logger.warning("Settings file not found, using default settings and creating settings file")
        # return default settings and create settings file
        settings: PoEMSettings = PoEMSettings(keys=KeySettings(), logic=LogicSettings(), currency=CurrencySettings())
        set_settings(settings)
    return settings


def set_settings(settings: PoEMSettings) -> None:
    """Set the settings in settings.yaml, creating file if needed."""
    with SETTINGS_FILE.open("w") as f:
        to_yaml_file(f, settings, add_comments=True)
