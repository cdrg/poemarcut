"""Get and save settings for PoEMarcut.

Defines default settings and settings file location.
"""

import logging
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator
from pydantic_yaml import parse_yaml_file_as, to_yaml_file
from PyQt6.QtCore import QObject, pyqtSignal
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
    enter_key: str = Field(default="f4", description="'Enter' key confirms the new price in the dialog")
    stop_key: str = Field(default="f6", description="Stop listening for hotkeys until re-enabled")

    @field_validator("copyitem_key", "rightclick_key", "calcprice_key", "enter_key", "stop_key")
    @classmethod
    def validate_keys(cls, key: str) -> str:
        """Validate that keys are not empty."""
        if not key:
            msg = "Key cannot be empty"
            raise ValueError(msg)
        return key


class LogicSettings(BaseModel):
    """Logic and calculation settings for price adjustments."""

    adjustment_factor: float = Field(
        default=0.9,
        gt=0.01,
        lt=2.0,
        description="The factor by which to multiply the current price to get the new price. For example, 0.9 would discount the current price by 10%",
    )
    min_actual_factor: float = Field(
        default=0.5,
        gt=0.01,
        lt=2.0,
        description="The minimum allowed actual adjustment factor. If the calculated adjustment factor is less than this, the price will not be adjusted",
    )
    enter_after_calcprice: bool = Field(
        default=True,
        description="True: press 'enter' key after calculating and pasting the new price. False: do not press 'enter' automatically.",
    )


class CurrencySettings(BaseModel):
    """Currency update settings."""

    autoupdate: bool = Field(
        default=True,
        description="True: fetch up-to-date currency values. False: only use cached/manually set values",
    )
    poe1leagues: set[str] = Field(
        default_factory=lambda: {"tmpstandard", "tmphardcore"}, description="The available PoE1 trade leagues"
    )
    poe2leagues: set[str] = Field(
        default_factory=lambda: {"tmpstandard", "tmphardcore"}, description="The available PoE2 trade leagues"
    )
    poe1currencies: list[str] = Field(  # dict[str, None] = Field(
        default_factory=lambda: ["divine", "chaos"],
        description="The order of PoE1 currencies to price items in",
    )
    poe2currencies: list[str] = Field(  # dict[str, None] = Field(
        default_factory=lambda: ["divine", "chaos", "exalted"],
        description="The order of PoE2 currencies to price items in",
    )
    assume_highest_currency: bool = Field(
        default=True, description="True: If actual currency is not available, assume the currency is the highest"
    )
    active_game: Literal[1, 2] = Field(
        default=1,
        description="The active game for currency values. 1 for PoE1, 2 for PoE2.",
    )
    active_league: str = Field(default="tmpstandard", description="The active league to fetch currency values for.")

    @model_validator(mode="after")
    def check_value_in_list(self) -> "CurrencySettings":
        """Validate that active_league is in the appropriate list of leagues based on active_game."""
        poe1 = list(self.poe1leagues or [])
        poe2 = list(self.poe2leagues or [])

        if self.active_game == 1 and self.active_league not in poe1:
            if not poe1:
                self.poe1leagues = {self.active_league}
                msg = f"No PoE1 leagues defined, setting active league '{self.active_league}' as the only PoE1 league."
                logger.warning(msg)
                return self
            msg = f"'{self.active_league}' must be in {poe1}, setting active league to '{poe1[0]}'."
            logger.warning(msg)
            self.active_league = poe1[0]
        if self.active_game == 2 and self.active_league not in poe2:  # noqa: PLR2004
            if not poe2:
                self.poe2leagues = {self.active_league}
                msg = f"No PoE2 leagues defined, setting active league '{self.active_league}' as the only PoE2 league."
                logger.warning(msg)
                return self
            msg = f"'{self.active_league}' must be in {poe2}, setting active league to '{poe2[0]}'."
            logger.warning(msg)
            self.active_league = poe2[0]
        return self


class PoEMSettings(BaseModel):
    """Settings for PoEMarcut."""

    keys: KeySettings
    logic: LogicSettings
    currency: CurrencySettings


class SettingsManager(QObject):
    """Manages the application settings, including loading from and saving to a YAML file."""

    # emits (field name, new_value) when a setting is changed
    settings_changed = pyqtSignal(str, object)

    def __init__(self) -> None:
        """Initialize the SettingsManager and load settings from file."""
        super().__init__()
        self._settings = self._load_settings()

    @property
    def settings(self) -> PoEMSettings:
        """Get the current application settings.

        Returns:
            PoEMSettings: The current settings object.

        """
        self._settings = self._load_settings()  # reload settings from file in case they were changed externally
        return self._settings

    def _load_settings(self) -> PoEMSettings:
        """Get PoEMSettings from settings.yaml, or return default settings if file is missing or invalid."""
        try:
            with SETTINGS_FILE.open() as f:
                settings: PoEMSettings = parse_yaml_file_as(PoEMSettings, f)
        except (YAMLError, ValidationError):
            logger.exception("Error reading settings from file, using default settings")
            # return default settings
            settings: PoEMSettings = PoEMSettings(
                keys=KeySettings(), logic=LogicSettings(), currency=CurrencySettings()
            )
        except FileNotFoundError:
            logger.warning("Settings file not found, using default settings and creating settings file")
            # return default settings and create settings file
            settings: PoEMSettings = PoEMSettings(
                keys=KeySettings(), logic=LogicSettings(), currency=CurrencySettings()
            )
            self.set_settings(settings)
        return settings

    def set_settings(self, new_settings: PoEMSettings) -> None:
        """Set the settings in settings.yaml, overwriting or creating file."""
        # Ensure we store a proper PoEMSettings object (keep nested sections intact)
        # new_settings is expected to be a PoEMSettings instance; reconstruct to be safe
        self._settings = PoEMSettings(
            keys=KeySettings(**new_settings.keys.model_dump()),
            logic=LogicSettings(**new_settings.logic.model_dump()),
            currency=CurrencySettings(**new_settings.currency.model_dump()),
        )

        with SETTINGS_FILE.open("w") as f:
            to_yaml_file(f, new_settings, add_comments=True)

        for category in new_settings.__class__.model_fields:
            category_obj = getattr(new_settings, category)
            for field_name in category_obj.__class__.model_fields:
                self.settings_changed.emit(f"{category}.{field_name}", getattr(category_obj, field_name))

    def set_setting(self, category: str, setting: str, value) -> None:  # noqa: ANN001
        """Set a specific setting value and save to settings.yaml."""
        settings = self._load_settings()
        category = category.lower()
        setting = setting.lower()
        if hasattr(settings, category):
            category_obj = getattr(settings, category)
            if hasattr(category_obj, setting):
                setattr(category_obj, setting, value)
                self.set_settings(settings)
                self.settings_changed.emit(f"{category}.{setting}", value)
            else:
                msg = f"Setting '{setting}' not found in category '{category}'"
                raise AttributeError(msg)
        else:
            msg = f"Category '{category}' not found in settings"
            raise AttributeError(msg)


# Module-level shared SettingsManager instance for easy access by other modules.
# Use this singleton to ensure signals and state are centralized.
settings_manager = SettingsManager()
