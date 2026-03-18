"""Get and save settings for PoEMarcut.

Defines default settings and settings file location.
"""

import logging
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, Field, ValidationError, field_serializer, field_validator, model_validator
from PyQt6.QtCore import QObject, pyqtSignal
from yaml import SafeDumper, SafeLoader, YAMLError, dump, load
from yaml.nodes import SequenceNode

from poemarcut import constants, currency

logger = logging.getLogger(__name__)


def _yaml_represent_set(dumper: SafeDumper, data: set) -> SequenceNode:
    return dumper.represent_sequence("!!python/set", list(data))


def _yaml_construct_set(loader: SafeLoader, node: SequenceNode) -> set:
    seq = loader.construct_sequence(node)
    return set(seq)


SafeDumper.add_representer(set, _yaml_represent_set)
SafeLoader.add_constructor("!!python/set", _yaml_construct_set)


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
        """Validate that keys are not empty.

        Args:
            key (str): Candidate key string to validate.

        Returns:
            str: The validated key string.

        """
        if not key:
            msg = "Key cannot be empty"
            raise ValueError(msg)
        return key


class LogicSettings(BaseModel):
    """Logic and calculation settings for price adjustments."""

    # User-facing value: discount percent (0-100). Stored in YAML as percent for clarity.
    discount_percent: int = Field(
        default=10,
        ge=1,
        le=99,
        description="Discount percent to apply to the current price (10% off a price of 100 would result in 90)",
    )

    # Maximum allowed discount percent (user-facing). For example, 50.0 means
    # the price calculation will not apply discounts greater than 50%.
    max_actual_discount: int = Field(
        default=50,
        ge=1,
        le=99,
        description="Maximum allowed discount percent. If the calculated discount would exceed this percentage, the price will be converted or not be adjusted",
    )
    enter_after_calcprice: bool = Field(
        default=True,
        description="True: press 'enter' key after calculating and pasting the new price. False: do not press 'enter' automatically",
    )
    price_delay: float = Field(
        default=0.2,
        ge=0.1,
        le=5.0,
        description="Delay in seconds between opening the price dialog and pasting new price",
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

    @field_serializer("poe1leagues", "poe2leagues", mode="plain")
    def _serialize_leagues(self, v: object) -> object:
        """Ensure `poe1leagues`/`poe2leagues` serialize as Python `set` objects.

        Pydantic may produce `list` during serialization in some code paths;
        returning a `set` here keeps the runtime type so the YAML dumper
        emits the `!!python/set` tag via the registered SafeDumper.
        """
        if isinstance(v, (list, tuple)):
            return set(v)
        return v

    @contextmanager
    def delay_validation(self) -> Generator[None, None, None]:
        """Context manager that temporarily disables validation during assignment of multiple attributes dependent on each other.

        Yields:
            None

        Returns:
            Generator[None, None, None]: A context manager generator that yields None.

        Raises:
            ValidationError: If validation fails when the context manager exits.

        """
        # Capture a lightweight snapshot (model_dump returns a fresh dict).
        original_state = self.model_dump()

        original_validate_assignment = self.model_config.get("validate_assignment", True)
        self.model_config["validate_assignment"] = False
        try:
            yield
        finally:
            self.model_config["validate_assignment"] = original_validate_assignment

        try:
            # Re-validate by constructing a fresh instance from the current dump.
            validated = self.__class__(**self.model_dump())
            for k, v in validated.model_dump().items():
                setattr(self, k, v)
        except (ValidationError, TypeError, ValueError):
            # Restore the original state on failure.
            for k, v in original_state.items():
                setattr(self, k, v)
            raise

    @model_validator(mode="after")
    def ensure_league_in_game_list(self) -> "CurrencySettings":
        """Validate that active_league is in the appropriate list of leagues based on active_game.

        Returns:
            CurrencySettings: Self, potentially mutated to correct leagues.

        """
        poe1 = self.poe1leagues or set()
        poe2 = self.poe2leagues or set()

        if self.active_game == 1 and self.active_league not in poe1:
            if not poe1:
                self.poe1leagues = {self.active_league}
                msg = f"No PoE1 leagues defined, setting active league '{self.active_league}' as the only PoE1 league."
                logger.warning(msg)
                return self
            msg = f"'{self.active_league}' must be in {poe1}, setting active league to '{next(iter(poe1))}'."
            logger.warning(msg)
            self.active_league = next(iter(poe1))
        if self.active_game == 2 and self.active_league not in poe2:  # noqa: PLR2004
            if not poe2:
                self.poe2leagues = {self.active_league}
                msg = f"No PoE2 leagues defined, setting active league '{self.active_league}' as the only PoE2 league."
                logger.warning(msg)
                return self
            msg = f"'{self.active_league}' must be in {poe2}, setting active league to '{next(iter(poe2))}'."
            logger.warning(msg)
            self.active_league = next(iter(poe2))
        return self

    @model_validator(mode="after")
    def ensure_leagues_nonempty(self) -> "CurrencySettings":
        """Ensure `poe1leagues` and `poe2leagues` are never empty.

        If a league set is empty, prefer to set it to `active_league` when
        available; otherwise fall back to well-known defaults.

        Returns:
            CurrencySettings: self, potentially mutated.

        """
        for field in ("poe1leagues", "poe2leagues"):
            val = getattr(self, field) or set()
            if not val:
                active = getattr(self, "active_league", None)
                # Only use active_league for the matching active_game.
                if active and (
                    (field == "poe1leagues" and self.active_game == 1)
                    or (field == "poe2leagues" and self.active_game == 2)  # noqa: PLR2004
                ):
                    setattr(self, field, {active})
                    logger.warning(
                        "No %s defined; setting to active_league %r for active_game %s", field, active, self.active_game
                    )
                else:
                    # Use the field's declared default by instantiating a fresh
                    # CurrencySettings and reading the attribute. This keeps the
                    # fallback in sync with the Field default_factory above.
                    defaults = CurrencySettings()
                    setattr(self, field, getattr(defaults, field))
                    logger.warning("No %s defined; resetting to model default values", field)
        return self

    @model_validator(mode="after")
    def validate_currency_mappings(self) -> "CurrencySettings":
        """Validate `poe1currencies` and `poe2currencies` mappings.

        - Requires a dict mapping currency->int units per highest currency.
        - Orders the dict by numeric value (ascending: most valuable -> least).
        - Ensures the smallest value is exactly 1; otherwise raises ValueError.

        Returns:
            CurrencySettings: Self, normalized and validated.

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
        """Initialize the SettingsManager and load settings from file.

        Returns:
            None

        """
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

    def _load_settings(self) -> PoEMSettings:  # noqa: C901, PLR0912, PLR0915
        """Get PoEMSettings from settings.yaml, or return default settings if file is missing or invalid.

        Returns:
            PoEMSettings: Loaded or default settings object.

        """
        # Build a safe default to fall back to in any failure case
        default = PoEMSettings(keys=KeySettings(), logic=LogicSettings(), currency=CurrencySettings())

        try:
            with SETTINGS_FILE.open() as f:
                try:
                    raw = load(f, Loader=SafeLoader)
                except (YAMLError, ValidationError):
                    logger.exception("Error parsing settings YAML; using defaults")
                    try:
                        self.set_settings(default)
                    except Exception:
                        logger.exception("Failed to persist default settings after parse error")
                    return default
        except FileNotFoundError:
            logger.warning("Settings file not found, using default settings and creating settings file")
            self.set_settings(default)
            return default

        if not isinstance(raw, dict):
            logger.warning("Settings file did not contain a mapping; using defaults")
            try:
                self.set_settings(default)
            except Exception:
                logger.exception("Failed to persist default settings for non-mapping YAML")
            return default

        # Section handlers: (ModelClass, default_instance)
        # Use fresh default instances per-section to avoid accidental mutation
        # of the `default` PoEMSettings nested objects during validation.
        sections = {
            "keys": (KeySettings, KeySettings()),
            "logic": (LogicSettings, LogicSettings()),
            "currency": (CurrencySettings, CurrencySettings()),
        }

        validated: dict[str, BaseModel] = {}

        for name, (cls, default_instance) in sections.items():
            raw_section = raw.get(name, {}) or {}
            if not isinstance(raw_section, dict):
                logger.warning("Settings.%s is not a mapping; ignoring user value", name)
                raw_section = {}

            # Start from the default instance
            current = default_instance

            # If the model provides a delay_validation context manager, use it
            # to set interdependent fields together without triggering
            # partially-applied validators (avoids spurious warnings).
            if hasattr(current, "delay_validation"):
                try:
                    with current.delay_validation():
                        current_dict = current.model_dump()
                        for field_name, val in raw_section.items():
                            if field_name not in current_dict:
                                logger.debug("Unknown setting %s.%s - ignoring", name, field_name)
                                continue
                            setattr(current, field_name, val)
                except (ValidationError, TypeError, ValueError):
                    logger.warning("Invalid values in settings.%s; falling back to defaults", name)
                    current = default_instance
            else:
                # Fall back to per-field trial instantiation for models without delay_validation
                current_dict = current.model_dump()
                for field_name, val in raw_section.items():
                    if field_name not in current_dict:
                        logger.debug("Unknown setting %s.%s - ignoring", name, field_name)
                        continue
                    trial = current_dict.copy()
                    trial[field_name] = val
                    try:
                        current = cls(**trial)
                        current_dict = current.model_dump()
                    except (ValidationError, TypeError, ValueError):
                        logger.warning("Invalid value for %s.%s: %r; falling back to default", name, field_name, val)

            validated[name] = current

        # Reconstruct each section to ensure any remaining invalid nested values
        # are replaced with per-section defaults rather than falling back to the
        # entire settings object.
        cleaned: dict[str, BaseModel] = {}
        for name, (cls, default_instance) in sections.items():
            candidate = validated.get(name, default_instance)
            try:
                # Ensure the candidate can be re-instantiated/validated as its class
                if isinstance(candidate, BaseModel):
                    cleaned[name] = cls(**candidate.model_dump())
                else:
                    cleaned[name] = cls(**(candidate or {}))
            except (ValidationError, TypeError, ValueError):
                logger.warning("Invalid values in finalized settings.%s; falling back to defaults", name)
                cleaned[name] = default_instance

        try:
            # Construct final settings without re-running nested validation. We
            # already validated/cleaned each section above; constructing without
            # validation avoids a single nested failure causing a full fallback.
            settings = PoEMSettings.model_construct(
                keys=cast("KeySettings", cleaned["keys"]),
                logic=cast("LogicSettings", cleaned["logic"]),
                currency=cast("CurrencySettings", cleaned["currency"]),
            )
        except (ValidationError, TypeError, ValueError):
            logger.exception("Failed to compose final PoEMSettings, falling back to defaults")
            try:
                self.set_settings(default)
            except Exception:
                logger.exception("Failed to persist default settings after final composition failure")
            return default

        return settings

    def set_settings(self, new_settings: PoEMSettings) -> None:
        """Set the settings in settings.yaml, overwriting or creating file.

        Args:
            new_settings (PoEMSettings): The new settings to persist.

        Returns:
            None

        """
        # Ensure we store a proper PoEMSettings object (keep nested sections intact)
        # new_settings is expected to be a PoEMSettings instance; reconstruct to be safe
        self._settings = PoEMSettings(
            keys=KeySettings(**new_settings.keys.model_dump()),
            logic=LogicSettings(**new_settings.logic.model_dump()),
            currency=CurrencySettings(**new_settings.currency.model_dump()),
        )

        with SETTINGS_FILE.open("w") as f:
            # Serialize the validated settings to a plain mapping and write YAML
            # using PyYAML. Use `self._settings` which was reconstructed above
            # (and therefore validated) rather than the incoming
            # `new_settings` which may have bypassed validation via
            # `model_construct`.
            data = self._settings.model_dump()
            currency_section = data.get("currency", {}) or {}

            # Ensure league fields are persisted as non-empty sets. If the
            # current value is empty (or an empty list), replace it with the
            # model default to avoid writing empty sequences/sets to disk.
            defaults = CurrencySettings()
            for field in ("poe1leagues", "poe2leagues"):
                val = currency_section.get(field)
                if isinstance(val, list):
                    val = set(val)
                # Normalize falsy/empty values to the model default
                if not val:
                    val = getattr(defaults, field)
                currency_section[field] = val

            data["currency"] = currency_section
            dump(data, f, sort_keys=False, Dumper=SafeDumper)

        for category in new_settings.__class__.model_fields:
            category_obj = getattr(new_settings, category)
            for field_name in category_obj.__class__.model_fields:
                self.settings_changed.emit(f"{category}.{field_name}", getattr(category_obj, field_name))

    def add_currency_and_persist(self, *, game: int, setting_field: str, chosen_key: str) -> None:
        """Insert `chosen_key` into the appropriate position and persist updated mapping.

        Uses helpers in `poemarcut.currency` to compute ordering and mapping based on
        live exchange rates (falls back to existing stored values on error).

        Args:
            game (int): Game id (1 or 2) indicating which currency mapping to update.
            setting_field (str): Field name on `CurrencySettings` to update (e.g. 'poe1currencies').
            chosen_key (str): Currency id to insert.

        Returns:
            None

        """
        settings_obj = self.settings
        currency_settings = settings_obj.currency
        raw = getattr(currency_settings, setting_field) or {}
        current_order = list(raw.keys())

        new_order = currency.compute_new_order(
            game=game,
            league=currency_settings.active_league,
            current_order=current_order,
            chosen_key=chosen_key,
            autoupdate=currency_settings.autoupdate,
        )
        new_mapping = currency.compute_mapping_from_order(
            game=game,
            league=currency_settings.active_league,
            ordered=new_order,
            existing_raw=raw,
            autoupdate=currency_settings.autoupdate,
        )

        setattr(settings_obj.currency, setting_field, new_mapping)
        self.set_settings(settings_obj)


# Module-level shared SettingsManager instance for easy access by other modules.
# Use this singleton to ensure signals and state are centralized.
settings_manager = SettingsManager()
