"""Get and save settings for PoEMarcut.

Defines default settings and settings file location.
"""

import copy
import logging
from collections.abc import Generator, Iterable
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator
from pydantic_yaml import parse_yaml_file_as, to_yaml_file
from PyQt6.QtCore import QObject, pyqtSignal
from yaml import YAMLError

from poemarcut import constants

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
        description="True: press 'enter' key after calculating and pasting the new price. False: do not press 'enter' automatically",
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
    poe1currencies: dict[str, int] = Field(
        default_factory=lambda: {"divine": 1, "chaos": 100},
        description="List of PoE1 currencies and their values relative to the highest currency",
    )
    poe2currencies: dict[str, int] = Field(
        default_factory=lambda: {"divine": 1, "chaos": 30, "exalted": 240},
        description="List of PoE2 currencies and their values relative to the highest currency",
    )
    assume_highest_currency: bool = Field(
        default=True,
        description="True: If actual currency is not available, assume the value being modified is the highest currency",
    )
    active_game: Literal[1, 2] = Field(
        default=1,
        description="The active game for currency values. 1 for PoE1, 2 for PoE2",
    )
    active_league: str = Field(default="tmpstandard", description="The active league to fetch currency values for")

    @field_validator("poe1leagues", "poe2leagues", mode="before")
    @classmethod
    def _coerce_leagues_to_set(cls, v: object | None) -> set[str]:
        """Coerce league values (often parsed as lists from YAML) into sets.

        This prevents Pydantic serializer warnings when the input value is a
        list but the model field is declared as `set[str]`.
        """
        # Normalize None to empty iterable
        if v is None:
            v = []

        result: set[str]
        # If already a set, return as-is
        if isinstance(v, set):
            return v
        # Handle mapping types by taking keys
        if isinstance(v, dict):
            result = set(v.keys())
        elif isinstance(v, (list, tuple)):
            result = set(v)
        elif isinstance(v, str):
            result = {v}
        else:
            # Fallback for other iterable types
            try:
                result = set(v) if isinstance(v, Iterable) else set()
            except (TypeError, ValueError) as exc:
                logger.debug("Failed to coerce leagues to set: %r (%s)", v, exc)
                result = set()

        return result

    @contextmanager
    def delay_validation(self) -> Generator[None, None, None]:
        """Context manager that temporarily disables validation during assignment of multiple attributes dependent on each other.

        Yields:
            None

        Raises:
            ValidationError: If validation fails when the context manager exits.

        """
        original_dict = copy.deepcopy(self.__dict__)

        original_validate_assignment = self.model_config.get("validate_assignment", True)
        self.model_config["validate_assignment"] = False
        try:
            yield
        finally:
            self.model_config["validate_assignment"] = original_validate_assignment

        try:
            self.__class__.model_validate(self.__dict__)
        except (ValidationError, TypeError, ValueError):
            for key, value in original_dict.items():
                setattr(self, key, value)
            raise

    @model_validator(mode="after")
    def ensure_league_in_game_list(self) -> "CurrencySettings":
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

    @model_validator(mode="after")
    def validate_currency_mappings(self) -> "CurrencySettings":
        """Validate `poe1currencies` and `poe2currencies` mappings.

        - Requires a dict mapping currency->int units per highest currency.
        - Orders the dict by numeric value (ascending: most valuable -> least).
        - Ensures the smallest value is exactly 1; otherwise raises ValueError.
        """
        for attr in ("poe1currencies", "poe2currencies"):
            raw = getattr(self, attr)

            if not isinstance(raw, dict):
                msg = f"{attr} must be a mapping of currency->int units (dict), got {type(raw).__name__}"
                raise TypeError(msg)

            # Ensure all keys are strings and values are positive ints.
            raw_map: dict[str, int] = {}
            # Choose per-game valid currency keys
            valid_keys = (
                constants.POE1_MERCHANT_CURRENCIES if attr == "poe1currencies" else constants.POE2_MERCHANT_CURRENCIES
            )
            for k, v in raw.items():
                # Normalize key to canonical merchant id (lowercase)
                k_norm = str(k).lower()
                if k_norm not in valid_keys:
                    msg = f"{attr} mapping key '{k}' is not a recognized merchant currency short name for this game"
                    raise ValueError(msg)
                try:
                    iv = int(v)
                except (TypeError, ValueError) as _err:
                    msg = f"{attr} mapping value for '{k}' is not an integer: {v!r}"
                    raise ValueError(msg) from None
                if iv <= 0:
                    msg = f"{attr} mapping value for '{k}' must be a positive integer, got {iv}"
                    raise ValueError(msg)
                raw_map[k_norm] = iv

            if not raw_map:
                setattr(self, attr, {})
                continue

            # Order by value (ascending: most valuable -> least valuable)
            ordered_items = sorted(raw_map.items(), key=lambda kv: kv[1])

            # The smallest value must be exactly 1; otherwise refuse and raise.
            min_val = ordered_items[0][1]
            if min_val != 1:
                msg = f"{attr} mapping must have smallest unit == 1, got {min_val}"
                raise ValueError(msg)

            # Rebuild ordered dict preserving the computed order
            normalized = {k: int(v) for k, v in ordered_items}
            setattr(self, attr, normalized)

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


# Module-level shared SettingsManager instance for easy access by other modules.
# Use this singleton to ensure signals and state are centralized.
settings_manager = SettingsManager()
