"""Get and save settings for PoEMarcut.

Defines default settings and settings file location.
"""

import logging
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError, field_validator
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
    enter_key: str = Field(default="f4", description="'enter' key confirms the new price in the dialog")
    exit_key: str = Field(
        default="f6", description="Exit the program. Many tools use f5 for '/hideout', so f6 is default"
    )

    @field_validator("copyitem_key", "rightclick_key", "calcprice_key", "enter_key", "exit_key")
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
        description="If enabled, 'enter' key is pressed after calculating and pasting the new price to set it",
    )


class CurrencySettings(BaseModel):
    """Currency update settings."""

    autoupdate: bool = Field(
        default=True,
        description="Whether to automatically fetch up-to-date currency values. If false, will only use cached/manually set values",
    )
    poe1leagues: list[str] = Field(default=["tmpStandard"], description="The PoE1 leagues to fetch currency values for")
    poe2leagues: list[str] = Field(default=["tmpStandard"], description="The PoE2 leagues to fetch currency values for")


class PoEMSettings(BaseModel):
    """Settings for PoEMarcut."""

    keys: KeySettings
    logic: LogicSettings
    currency: CurrencySettings


class SettingsManager(QObject):
    """Manages the application settings, including loading from and saving to a YAML file.

    This class provides methods to get and set settings, as well as to update specific settings values.
    """

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
        self._settings = PoEMSettings(
            **new_settings.keys.model_dump(), **new_settings.logic.model_dump(), **new_settings.currency.model_dump()
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
