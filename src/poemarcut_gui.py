"""PoEMarcut GUI."""

import contextlib
import logging
import sys
import threading
import time
from collections.abc import Iterable, Mapping
from functools import partial
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import MappingProxyType

from PyQt6.QtCore import QEvent, QObject, QSignalBlocker, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QAction,
    QCloseEvent,
    QDoubleValidator,
    QFontDatabase,
    QIcon,
    QIntValidator,
    QMoveEvent,
    QResizeEvent,
    QValidator,
)
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from poemarcut import __version__, constants, currency, keyboard, settings, update

logger = logging.getLogger(__name__)


# QObject that emits the latest log message via a Qt signal.
class LogSignalEmitter(QObject):
    """QObject emitter that sends the most recent log message to GUI slots.

    The `last_log` signal emits a single `str` payload containing the
    formatted log record. Emitting is performed from the logging handler
    and will be delivered on the Qt event loop thread.
    """

    last_log = pyqtSignal(str)


_log_emitter = LogSignalEmitter()


class _LastLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - tiny helper
        """Emit a logging record by forwarding a formatted message via Qt signal.

        Args:
            record (logging.LogRecord): The record to emit.

        Returns:
            None

        """
        msg = record.getMessage()
        with contextlib.suppress(Exception):
            msg = self.format(record)
        with contextlib.suppress(Exception):
            _log_emitter.last_log.emit(msg)


class _EmojiFormatter(logging.Formatter):
    # Map level names to custom symbols
    LEVEL_SYMBOLS = MappingProxyType(
        {"DEBUG": "🐛", "INFO": "💡", "WARNING": "⚠️", "ERROR": "❌", "EXCEPTION": "💥", "CRITICAL": "🚨"}
    )

    def format(self, record: logging.LogRecord) -> str:
        """Format a LogRecord, replacing the level name with a symbol.

        Args:
            record (logging.LogRecord): The record to format.

        Returns:
            str: The formatted log string with a symbol for the level.

        """
        # Swap levelname for symbol
        record.levelname = self.LEVEL_SYMBOLS.get(record.levelname, record.levelname)
        return super().format(record)


# PoE-like color scheme
poe_header_text_color = "rgb(163, 139, 99)"
poe_header_style = f"color: {poe_header_text_color}; font-weight: bold; text-decoration: underline;"
poe_text_color = "rgb(170, 170, 170)"
poe_dark_bg_color = "rgb(34, 16, 4)"
poe_light_bg_color = "rgb(50, 30, 10)"
poe_dropdown_text_color = "rgb(178, 175, 159)"
poe_dropdown_bg_color = "rgb(48, 48, 48)"
poe_selection_bg_color = "rgb(124, 124, 124)"
poe_edit_bg_color = "rgb(58, 51, 46)"
poe_small_text = "font-size: 9pt"

# width/height 2x border-radius = a circle
qradiobutton_light = (
    "QRadioButton::indicator { width: 24px; height: 24px; border-radius: 12px; background-color: black; }"
)
greenlight = "limegreen"
redlight = "salmon"
qradiobutton_greenlight = qradiobutton_light.replace("background-color: black", f"background-color: {greenlight}")
qradiobutton_redlight = qradiobutton_light.replace("background-color: black", f"background-color: {redlight}")

# Friendly display overrides for special poe.ninja league ids (case-insensitive)
LEAGUE_DISPLAY_OVERRIDES: dict[str, str] = {
    "tmpstandard": "Current league",
    "tmphardcore": "Current hardcore league",
}

# Determine base path for bundled resources. When run from a PyInstaller
# onefile bundle, resources are extracted into the runtime folder
# available at `sys._MEIPASS`.
try:
    _base_path = Path(sys._MEIPASS)  # pyright: ignore[reportAttributeAccessIssue] # noqa: SLF001
except AttributeError:
    _base_path = Path(__file__).parent.parent

# Paths to bundled assets (works both when run normally and when packaged with PyInstaller).
font_path: Path = _base_path / "assets" / "Fontin-Regular.otf"
icon_path: Path = _base_path / "assets" / "icon.ico"
settings_icon_path: Path = _base_path / "assets" / "gear.ico"


class PoEMarcutGUI(QMainWindow):
    """GUI for PoE Marcut.

    Displays price suggestions and access to settings.
    """

    # Emitted when background currency fetch completes (dict with 'success' and 'lines' or 'error' keys)
    currency_data_ready = pyqtSignal(object)
    # Emitted when keyboard listener stops itself (e.g. stop_key pressed)
    hotkeys_listener_stopped = pyqtSignal()
    # Emitted when a GitHub update check completes: (version: str|None)
    # A non-None version indicates an update is available.
    github_update_ready = pyqtSignal(object)
    # Emitted when a background league fetch completes: (game: int, leagues: set[str] | None)
    leagues_ready = pyqtSignal(int, object)

    def __init__(self) -> None:
        """Initialize the PoEMarcut GUI window and set up the user interface.

        Returns:
            None

        """
        super().__init__()
        # Use the shared SettingsManager singleton
        self.settings_manager: settings.SettingsManager = settings.settings_manager
        self.setWindowTitle("PoE Marcut")
        # Initialize window geometry from saved settings
        try:
            gui_settings = self.settings_manager.settings.gui
            pos = gui_settings.position
            size = gui_settings.size
            self.setGeometry(int(pos.x), int(pos.y), int(size.width), int(size.height))
        except (AttributeError, TypeError, ValueError):
            # Fallback to a sensible default if settings are malformed
            self.setGeometry(400, 100, 450, 400)

        self.custom_font_family: str = "default"

        font_id: int = QFontDatabase.addApplicationFont(str(font_path))
        if font_id == -1:
            logger.warning("Failed to load custom font, using default.")
        else:
            families = QFontDatabase.applicationFontFamilies(font_id)
            self.custom_font_family = families[0] if families else "default"

        if icon_path.is_file():
            app_icon: QIcon = QIcon(str(icon_path))
            self.setWindowIcon(app_icon)

        self.setStyleSheet(
            f"* {{ font-family: {self.custom_font_family}; font-size: 12pt; }} "
            f"QMainWindow {{ color: {poe_header_text_color}; background-color: {poe_dark_bg_color}; }} "
            f"QWidget#SettingsWindow {{ color: {poe_header_text_color}; background-color: {poe_dark_bg_color}; }}"
            f"QLabel {{ color: {poe_text_color}; }} "
            f"QLineEdit {{ color: {poe_text_color}; background-color: {poe_edit_bg_color}; }} "
            f"QTextEdit {{ color: {poe_header_text_color}; background-color: {poe_light_bg_color}; }} "
            f"QCheckBox {{ color: {poe_header_text_color}; }} "
            f"QCheckBox::indicator {{ border: 1px solid; border-color: {poe_text_color}; }} "
            f"QCheckBox::indicator:checked {{ background-color: {poe_header_text_color}; }} "
            f"QComboBox {{  }} "
            f"QComboBox QAbstractItemView {{ color: {poe_dropdown_text_color}; background-color: {poe_dropdown_bg_color}; selection-background-color: {poe_selection_bg_color}; }} "
            f"QListWidget {{ color: {poe_header_text_color}; background-color: {poe_light_bg_color}; border: 1px solid {poe_header_text_color}; }} "
            f"QToolTip {{ color: {poe_text_color}; background-color: {poe_light_bg_color}; border: 1px solid {poe_header_text_color}; }}"
            f"QInputDialog {{ color: {poe_text_color}; background-color: {poe_dark_bg_color}; }} "
        )

        self._tray_icon: QSystemTrayIcon | None = None
        self._tray_menu: QMenu | None = None
        self._tray_hotkeys_action: QAction | None = None

        self.init_ui()

        # Local cached settings object to avoid repeatedly reading from disk
        # and to allow batching/debouncing writes.
        self._settings_cache = self.settings_manager.settings
        self._persist_scheduled = False

        # Signal used to update the UI from a background thread
        self.hotkeys_listener_stopped.connect(self._on_hotkeys_listener_stopped)

        # Check for GitHub update in background to avoid blocking UI
        try:
            # connect signal to slot so updates arrive on the GUI thread
            self.github_update_ready.connect(self._on_github_update_ready)
            # connect leagues_ready to handler that updates settings/UI on GUI thread
            self.leagues_ready.connect(self._on_leagues_ready)
            threading.Thread(target=self._check_github_update, daemon=True).start()
        except (RuntimeError, TypeError):
            logger.exception("Failed to start background thread for github update check")

        logger.info("PoEMarcut initialized")

    def init_ui(self) -> None:  # noqa: PLR0915
        """Set up the user interface components.

        Returns:
            None

        """
        central: QWidget = QWidget()
        main_layout: QGridLayout = QGridLayout()

        self.currency_header: QLabel = QLabel("Currency Information")
        self.currency_header.setStyleSheet(poe_header_style)
        main_layout.addWidget(self.currency_header, 0, 0, 1, 1)

        self.github_update_label: QLabel = QLabel(f"v{__version__}")
        main_layout.addWidget(self.github_update_label, 1, 2, 1, 1)

        league_widget: QWidget = QWidget()
        league_layout: QVBoxLayout = QVBoxLayout(league_widget)
        league_layout.setContentsMargins(0, 0, 0, 0)
        league_label: QLabel = QLabel("Choose league:")
        league_layout.addWidget(league_label)

        self.league_combo: QComboBox = QComboBox()
        self.populate_league_combo()
        league_row = QHBoxLayout()
        league_row.addWidget(self.league_combo)
        league_row.addStretch()
        league_layout.addLayout(league_row)
        # Update active game/league when the user selects a league
        self.league_combo.currentIndexChanged.connect(self._on_league_combo_changed)

        self.currency_lastupdate_label: QLabel = QLabel("")
        self.currency_lastupdate_label.setStyleSheet(f"color: {poe_text_color}; {poe_small_text};")
        league_layout.addWidget(self.currency_lastupdate_label)

        self.currency_note_label: QLabel = QLabel("GGG only updates currency economy data once per hour.")
        self.currency_note_label.setStyleSheet(f"color: {poe_text_color}; {poe_small_text};")
        league_layout.addWidget(self.currency_note_label)

        main_layout.addWidget(league_widget, 1, 0, 2, 2)

        self.currency_list: QListWidget = QListWidget()
        main_layout.addWidget(self.currency_list, 3, 0, 1, 3)
        self.populate_currency_list()

        status_layout: QHBoxLayout = QHBoxLayout()
        self.status_label: QLabel = QLabel("Status:")
        self.status_label.setStyleSheet(f"{poe_small_text};")
        status_layout.addWidget(self.status_label)
        self.log_output_label: QLabel = QLabel("")
        self.log_output_label.setStyleSheet(f"{poe_small_text};")
        # Size the log label relative to the main window width so it doesn't grow past the window.
        self.log_output_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        try:
            avail = int(self.width() - (self.status_label.sizeHint().width() + 80))
        except (TypeError, ValueError, AttributeError):
            avail = 200
        avail = max(avail, 100)
        self.log_output_label.setMaximumWidth(avail)
        status_layout.addWidget(self.log_output_label)
        status_layout.addStretch()
        # Connect the global log-emitter signal to update the label in the GUI thread.
        self._last_log_shown = None
        try:
            _log_emitter.last_log.connect(self._on_last_log_message)
        except (RuntimeError, TypeError):
            logger.exception("Failed to connect log emitter to GUI slot")
        main_layout.addLayout(status_layout, 4, 0, 1, 3)

        self.settings_button: QPushButton = QPushButton("Settings...")
        self.settings_button.clicked.connect(self.toggle_settings_window)
        main_layout.addWidget(self.settings_button, 5, 0, 1, 1)

        self.hotkeys_enabled: bool = False  # State for hotkeys button

        self.hotkeys_button: QPushButton = QPushButton("Enable hotkeys")
        self.hotkeys_button.clicked.connect(self.toggle_hotkeys)
        main_layout.addWidget(self.hotkeys_button, 5, 1, 1, 1)

        self.indicator = QRadioButton()
        self.indicator.setEnabled(False)  # Disable user interaction
        main_layout.addWidget(self.indicator, 5, 2, 1, 1)

        self.toggle_hotkeys()  # Enable hotkeys on start

        central.setLayout(main_layout)
        self.setCentralWidget(central)
        # Install event filter to track window move events for positioning settings window
        self.installEventFilter(self)

        self.setup_settings_sidebar()

        # Create a separate top-level window for Settings, positioned to the right of the main window
        self.settings_window: QWidget = QWidget()
        self.settings_window.setObjectName("SettingsWindow")
        self.settings_window.setWindowTitle("PoE Marcut Settings")
        if settings_icon_path.is_file():
            settings_icon: QIcon = QIcon(str(settings_icon_path))
            self.settings_window.setWindowIcon(settings_icon)
        # Use the same main window stylesheet
        self.settings_window.setStyleSheet(self.styleSheet())
        self.settings_window.setLayout(self.side_settings_layout)
        self.settings_window.hide()  # Start hidden

    def moveEvent(self, event: QMoveEvent) -> None:  # type: ignore[override]  # noqa: N802
        """Track window moves and persist position to settings (debounced)."""
        try:
            # Use frameGeometry to include the window frame/title bar so
            # persisted position reflects the visible outer window.
            geom = self.frameGeometry()
            if getattr(self, "_settings_cache", None) is not None:
                try:
                    self._settings_cache.gui.position.x = int(geom.x())
                    self._settings_cache.gui.position.y = int(geom.y())
                except (AttributeError, TypeError, ValueError):
                    # Fallback: attempt direct assignment again
                    self._settings_cache.gui.position.x = int(geom.x())
                    self._settings_cache.gui.position.y = int(geom.y())
                # Update settings UI fields if present
                try:
                    with QSignalBlocker(getattr(self, "window_position_x_qle", None)):
                        if getattr(self, "window_position_x_qle", None) is not None:
                            self.window_position_x_qle.setText(str(int(geom.x())))
                    with QSignalBlocker(getattr(self, "window_position_y_qle", None)):
                        if getattr(self, "window_position_y_qle", None) is not None:
                            self.window_position_y_qle.setText(str(int(geom.y())))
                except (AttributeError, TypeError, RuntimeError) as _exc:
                    logger.debug("Failed updating position fields in settings UI", exc_info=True)
                self._schedule_persist_settings()
        except (AttributeError, TypeError, ValueError):
            logger.exception("Failed to persist window position on move")
        super().moveEvent(event)

    def resizeEvent(self, event: QResizeEvent) -> None:  # type: ignore[override]  # noqa: N802
        """Track window resizes and persist size to settings (debounced)."""
        try:
            # Use geometry (client area) when persisting size so the stored
            # width/height round-trip correctly via setGeometry() without
            # accumulating window decoration deltas across runs.
            geom = self.geometry()
            if getattr(self, "_settings_cache", None) is not None:
                try:
                    self._settings_cache.gui.size.width = int(geom.width())
                    self._settings_cache.gui.size.height = int(geom.height())
                except (AttributeError, TypeError, ValueError):
                    # Fallback: attempt direct assignment again
                    self._settings_cache.gui.size.width = int(geom.width())
                    self._settings_cache.gui.size.height = int(geom.height())
                # Update settings UI fields if present
                try:
                    with QSignalBlocker(getattr(self, "window_size_width_qle", None)):
                        if getattr(self, "window_size_width_qle", None) is not None:
                            self.window_size_width_qle.setText(str(int(geom.width())))
                    with QSignalBlocker(getattr(self, "window_size_height_qle", None)):
                        if getattr(self, "window_size_height_qle", None) is not None:
                            self.window_size_height_qle.setText(str(int(geom.height())))
                except (AttributeError, TypeError, RuntimeError) as _exc:
                    logger.debug("Failed updating size fields in settings UI", exc_info=True)
                self._schedule_persist_settings()
        except (AttributeError, TypeError, ValueError):
            logger.exception("Failed to persist window size on resize")
        super().resizeEvent(event)

    def setup_settings_sidebar(self) -> None:  # noqa: PLR0915
        """Build the settings sidebar.

        Returns:
            None

        """
        settings_man: settings.SettingsManager = self.settings_manager

        self.side_settings_layout: QHBoxLayout = QHBoxLayout()

        ### left panel of settings
        leftthird_layout: QGridLayout = QGridLayout()
        row_idx = 0

        ## set up components for Keys settings fields
        keys_settings: settings.KeySettings = settings_man.settings.keys
        keys_settings_header: QLabel = QLabel("Keys settings")
        keys_settings_header.setStyleSheet(poe_header_style)
        leftthird_layout.addWidget(keys_settings_header, row_idx, 0, 1, 2)
        row_idx += 1

        # loop through all key fields
        # store line edits so we can update them when settings change
        self.key_lineedits: dict[str, QLineEdit] = {}
        for field_name, field_value in keys_settings:
            field_info = keys_settings.__class__.model_fields[field_name]
            setting_label: QLabel = QLabel(f"{field_name}:".replace("_", " "))
            setting_label.setToolTip(field_info.description or "")

            lineedit: QLineEdit = QLineEdit(str(field_value))
            self.key_validator = KeyOrKeyCodeValidator()
            lineedit.setValidator(self.key_validator)
            # update settings when the user finishes editing
            lineedit.editingFinished.connect(partial(self.process_qle_text, "Keys", field_name, lineedit))
            self.key_lineedits[field_name] = lineedit

            leftthird_layout.addWidget(setting_label, row_idx, 0)
            leftthird_layout.addWidget(lineedit, row_idx, 1)
            row_idx += 1

        ## set up components for Logic settings fields
        logic_settings: settings.LogicSettings = settings_man.settings.logic
        logic_settings_header: QLabel = QLabel("Logic settings")
        logic_settings_header.setStyleSheet(poe_header_style)
        leftthird_layout.addWidget(logic_settings_header, row_idx, 0, 1, 2)
        row_idx += 1

        # discount percent field
        af_setting_label: QLabel = QLabel("Discount %")
        af_field_info = logic_settings.__class__.model_fields.get("discount_percent")
        af_setting_label.setToolTip((af_field_info.description if af_field_info is not None else "") or "")
        self.discount_percent_le: QLineEdit = QLineEdit(str(logic_settings.discount_percent))
        # Percent validator: 1-99 (integer)
        self.discount_percent_le.setValidator(QIntValidator(1, 99, parent=self.discount_percent_le))
        self.discount_percent_le.returnPressed.connect(
            partial(self.process_qle_int, "Logic", "discount_percent", self.discount_percent_le)
        )
        self.discount_percent_le.editingFinished.connect(
            partial(self.process_qle_int, "Logic", "discount_percent", self.discount_percent_le)
        )
        leftthird_layout.addWidget(af_setting_label, row_idx, 0)
        leftthird_layout.addWidget(self.discount_percent_le, row_idx, 1)
        row_idx += 1

        # max actual discount field (percent)
        maf_setting_label: QLabel = QLabel("Max discount")
        maf_field_info = logic_settings.__class__.model_fields.get("max_actual_discount")
        maf_setting_label.setToolTip((maf_field_info.description if maf_field_info is not None else "") or "")
        self.max_actual_discount_le: QLineEdit = QLineEdit(str(logic_settings.max_actual_discount))
        # Percent validator: 1-99 (integer)
        self.max_actual_discount_le.setValidator(QIntValidator(1, 99, parent=self.max_actual_discount_le))
        self.max_actual_discount_le.returnPressed.connect(
            partial(self.process_qle_int, "Logic", "max_actual_discount", self.max_actual_discount_le)
        )
        self.max_actual_discount_le.editingFinished.connect(
            partial(self.process_qle_int, "Logic", "max_actual_discount", self.max_actual_discount_le)
        )
        leftthird_layout.addWidget(maf_setting_label, row_idx, 0)
        leftthird_layout.addWidget(self.max_actual_discount_le, row_idx, 1)
        row_idx += 1

        # enter after calcprice field
        eac_setting_label: QLabel = QLabel("Press enter")
        eac_field_info = logic_settings.__class__.model_fields["enter_after_calcprice"]
        eac_setting_label.setToolTip(eac_field_info.description or "")
        self.enter_after_cb: QCheckBox = QCheckBox("")
        self.enter_after_cb.setChecked(logic_settings.enter_after_calcprice)
        self.enter_after_cb.stateChanged.connect(
            partial(self.process_qcb, "Logic", "enter_after_calcprice", self.enter_after_cb)
        )
        leftthird_layout.addWidget(eac_setting_label, row_idx, 0)
        leftthird_layout.addWidget(self.enter_after_cb, row_idx, 1)
        row_idx += 1

        # price delay field
        pd_setting_label: QLabel = QLabel("Price delay")
        pd_field_info = logic_settings.__class__.model_fields["price_delay"]
        pd_setting_label.setToolTip(pd_field_info.description or "")
        self.price_delay_le: QLineEdit = QLineEdit(str(logic_settings.price_delay))
        self.price_delay_le.setValidator(QDoubleValidator(0.1, 5.0, 1, parent=self.price_delay_le))
        self.price_delay_le.returnPressed.connect(
            partial(self.process_qle_float, "Logic", "price_delay", self.price_delay_le)
        )
        self.price_delay_le.editingFinished.connect(
            partial(self.process_qle_float, "Logic", "price_delay", self.price_delay_le)
        )
        leftthird_layout.addWidget(pd_setting_label, row_idx, 0)
        leftthird_layout.addWidget(self.price_delay_le, row_idx, 1)
        row_idx += 1

        # set up components for GUI settings fields
        gui_settings: settings.GuiSettings = settings_man.settings.gui
        gui_settings_header: QLabel = QLabel("GUI settings")
        gui_settings_header.setStyleSheet(poe_header_style)
        leftthird_layout.addWidget(gui_settings_header, row_idx, 0, 1, 2)
        row_idx += 1

        # always on top field
        always_on_top_label: QLabel = QLabel("Always on top")
        always_on_top_field_info = gui_settings.__class__.model_fields["always_on_top"]
        always_on_top_label.setToolTip(always_on_top_field_info.description or "")
        self.always_on_top_cb: QCheckBox = QCheckBox()
        self.always_on_top_cb.stateChanged.connect(
            partial(self.process_qcb, "Gui", "always_on_top", self.always_on_top_cb)
        )
        self.always_on_top_cb.setChecked(gui_settings.always_on_top)
        leftthird_layout.addWidget(always_on_top_label, row_idx, 0)
        leftthird_layout.addWidget(self.always_on_top_cb, row_idx, 1)
        row_idx += 1

        # minimize to tray field
        minimize_to_tray_label: QLabel = QLabel("Minimize to tray")
        minimize_to_tray_field_info = gui_settings.__class__.model_fields["minimize_to_tray"]
        minimize_to_tray_label.setToolTip(minimize_to_tray_field_info.description or "")
        self.minimize_to_tray_cb: QCheckBox = QCheckBox()
        self.minimize_to_tray_cb.stateChanged.connect(
            partial(self.process_qcb, "Gui", "minimize_to_tray", self.minimize_to_tray_cb)
        )
        self.minimize_to_tray_cb.setChecked(gui_settings.minimize_to_tray)
        # Disable the option if the system tray is unavailable on this platform
        try:
            if not QSystemTrayIcon.isSystemTrayAvailable():
                self.minimize_to_tray_cb.setEnabled(False)
                # Append availability note to the tooltip
                note = " (disabled: system tray unavailable on this platform)"
                self.minimize_to_tray_cb.setToolTip((minimize_to_tray_field_info.description or "") + note)
        except (AttributeError, RuntimeError, TypeError):
            logger.exception("Failed to query system tray availability for minimize-to-tray checkbox")
        leftthird_layout.addWidget(minimize_to_tray_label, row_idx, 0)
        leftthird_layout.addWidget(self.minimize_to_tray_cb, row_idx, 1)
        row_idx += 1

        # window position fields
        window_position_label: QLabel = QLabel("Window position")
        window_position_field_info = gui_settings.__class__.model_fields["position"]
        window_position_label.setToolTip(window_position_field_info.description or "")
        leftthird_layout.addWidget(window_position_label, row_idx, 0)
        row_idx += 1
        position_layout: QHBoxLayout = QHBoxLayout()
        self.window_position_x_qle: QLineEdit = QLineEdit()
        self.window_position_x_qle.setReadOnly(True)
        self.window_position_x_qle.setText(str(gui_settings.position.x))
        position_layout.addWidget(self.window_position_x_qle)
        window_position_comma_label: QLabel = QLabel(",")
        position_layout.addWidget(window_position_comma_label)
        self.window_position_y_qle: QLineEdit = QLineEdit()
        self.window_position_y_qle.setReadOnly(True)
        self.window_position_y_qle.setText(str(gui_settings.position.y))
        position_layout.addWidget(self.window_position_y_qle)

        leftthird_layout.addLayout(position_layout, row_idx, 0, 1, 2)
        row_idx += 1

        # window size fields
        window_size_label: QLabel = QLabel("Window size")
        window_size_field_info = gui_settings.__class__.model_fields["size"]
        window_size_label.setToolTip(window_size_field_info.description or "")
        leftthird_layout.addWidget(window_size_label, row_idx, 0)
        row_idx += 1
        size_layout: QHBoxLayout = QHBoxLayout()
        self.window_size_width_qle: QLineEdit = QLineEdit()
        self.window_size_width_qle.setReadOnly(True)
        self.window_size_width_qle.setText(str(gui_settings.size.width))
        size_layout.addWidget(self.window_size_width_qle)
        window_size_x_label: QLabel = QLabel("x")
        size_layout.addWidget(window_size_x_label)
        self.window_size_height_qle: QLineEdit = QLineEdit()
        self.window_size_height_qle.setReadOnly(True)
        self.window_size_height_qle.setText(str(gui_settings.size.height))
        size_layout.addWidget(self.window_size_height_qle)

        leftthird_layout.addLayout(size_layout, row_idx, 0, 1, 2)
        row_idx += 1

        # stretch to push items to top
        leftthird_layout.setRowStretch(row_idx, 1)

        self.side_settings_layout.addLayout(leftthird_layout, 0)

        ### middle panel of settings
        middle_layout: QVBoxLayout = QVBoxLayout()

        ## set up components for Currency settings fields
        currency_settings: settings.CurrencySettings = settings_man.settings.currency
        currency_settings_header: QLabel = QLabel("Currency settings")
        currency_settings_header.setStyleSheet(poe_header_style)
        middle_layout.addWidget(currency_settings_header)

        # assume highest currency field
        ahc_row_layout: QHBoxLayout = QHBoxLayout()
        ahc_setting_label: QLabel = QLabel("Assume highest")
        ahc_field_info = currency_settings.__class__.model_fields["assume_highest_currency"]
        ahc_setting_label.setToolTip(ahc_field_info.description or "")
        ahc_row_layout.addWidget(ahc_setting_label, stretch=1)
        self.assume_highest_currency_cb: QCheckBox = QCheckBox("")
        self.assume_highest_currency_cb.setChecked(currency_settings.assume_highest_currency)
        self.assume_highest_currency_cb.stateChanged.connect(
            partial(self.process_qcb, "Currency", "assume_highest_currency", self.assume_highest_currency_cb)
        )
        ahc_row_layout.addWidget(self.assume_highest_currency_cb, stretch=1)
        middle_layout.addLayout(ahc_row_layout)

        # poe1currencies field
        p1c_list_layout: QVBoxLayout = QVBoxLayout()
        p1c_setting_label: QLabel = QLabel("PoE1 currencies")
        p1c_field_info = currency_settings.__class__.model_fields["poe1currencies"]
        p1c_setting_label.setToolTip(p1c_field_info.description or "")
        p1c_list_layout.addWidget(p1c_setting_label)

        self.p1c_list_widget = QListWidget()
        self._populate_list_widget(self.p1c_list_widget, currency_settings.poe1currencies, "Currency", "poe1currencies")
        self.p1c_list_widget.currentItemChanged.connect(
            partial(self.process_qlw, "Currency", "poe1currencies", self.p1c_list_widget)
        )
        p1c_list_layout.addWidget(self.p1c_list_widget)
        middle_layout.addLayout(p1c_list_layout)

        # poe1 currencies button
        self.add_poe1_currency_button: QPushButton = QPushButton("Add PoE1 currency...")
        self.add_poe1_currency_button.setToolTip("Add a PoE1 currency to the conversion list")
        self.add_poe1_currency_button.clicked.connect(self.add_poe1_currency)
        middle_layout.addWidget(self.add_poe1_currency_button)

        # poe2currencies field
        p2c_list_layout: QVBoxLayout = QVBoxLayout()
        p2c_setting_label: QLabel = QLabel("PoE2 currencies")
        p2c_field_info = currency_settings.__class__.model_fields["poe2currencies"]
        p2c_setting_label.setToolTip(p2c_field_info.description or "")
        p2c_list_layout.addWidget(p2c_setting_label)

        self.p2c_list_widget = QListWidget()
        self._populate_list_widget(self.p2c_list_widget, currency_settings.poe2currencies, "Currency", "poe2currencies")
        self.p2c_list_widget.currentItemChanged.connect(
            partial(self.process_qlw, "Currency", "poe2currencies", self.p2c_list_widget)
        )
        p2c_list_layout.addWidget(self.p2c_list_widget)
        middle_layout.addLayout(p2c_list_layout)

        # poe2 currencies button
        self.add_poe2_currency_button: QPushButton = QPushButton("Add PoE2 currency...")
        self.add_poe2_currency_button.setToolTip("Add a PoE2 currency to the conversion list")
        self.add_poe2_currency_button.clicked.connect(self.add_poe2_currency)
        middle_layout.addWidget(self.add_poe2_currency_button)

        # active game field
        ag_setting_label: QLabel = QLabel("Active game")
        ag_field_info = currency_settings.__class__.model_fields["active_game"]
        ag_setting_label.setToolTip(ag_field_info.description or "")
        self.active_game_le: QLineEdit = QLineEdit(str(currency_settings.active_game))
        self.active_game_le.setReadOnly(True)
        middle_layout.addWidget(ag_setting_label)
        middle_layout.addWidget(self.active_game_le)

        middle_layout.addStretch()
        self.side_settings_layout.addLayout(middle_layout, 1)

        ### right panel of settings
        rightthird_layout: QVBoxLayout = QVBoxLayout()

        blank_header: QLabel = QLabel("Currency settings")
        blank_header.setStyleSheet("color: transparent;")
        rightthird_layout.addWidget(blank_header)

        # autoupdate field
        au_row_layout: QHBoxLayout = QHBoxLayout()
        au_setting_label: QLabel = QLabel("Autoupdate")
        au_field_info = currency_settings.__class__.model_fields["autoupdate"]
        au_setting_label.setToolTip(au_field_info.description or "")
        au_row_layout.addWidget(au_setting_label, stretch=1)
        self.autoupdate_cb: QCheckBox = QCheckBox("")
        self.autoupdate_cb.setChecked(currency_settings.autoupdate)
        self.autoupdate_cb.stateChanged.connect(partial(self.process_qcb, "Currency", "autoupdate", self.autoupdate_cb))
        au_row_layout.addWidget(self.autoupdate_cb, stretch=1)
        rightthird_layout.addLayout(au_row_layout)

        # poe1leagues field
        p1l_list_layout: QVBoxLayout = QVBoxLayout()
        p1l_setting_label: QLabel = QLabel("PoE1 leagues")
        p1l_field_info = currency_settings.__class__.model_fields["poe1leagues"]
        p1l_setting_label.setToolTip(p1l_field_info.description or "")
        p1l_list_layout.addWidget(p1l_setting_label)

        self.p1l_list_widget = QListWidget()
        self.p1l_list_widget.setMinimumWidth(160)
        self._populate_list_widget(self.p1l_list_widget, currency_settings.poe1leagues, "Currency", "poe1leagues")
        self.p1l_list_widget.currentItemChanged.connect(
            partial(self.process_qlw, "Currency", "poe1leagues", self.p1l_list_widget)
        )
        p1l_list_layout.addWidget(self.p1l_list_widget)
        rightthird_layout.addLayout(p1l_list_layout)

        # poe1 leagues button
        self.get_poe1_leagues_button: QPushButton = QPushButton("Get PoE1 leagues")
        self.get_poe1_leagues_button.setToolTip("Replace the PoE1 leagues with the list from GGG")
        self.get_poe1_leagues_button.clicked.connect(self.get_poe1_leagues)
        rightthird_layout.addWidget(self.get_poe1_leagues_button)

        # poe2leagues field
        p2l_list_layout: QVBoxLayout = QVBoxLayout()
        p2l_setting_label: QLabel = QLabel("PoE2 leagues")
        p2l_field_info = currency_settings.__class__.model_fields["poe2leagues"]
        p2l_setting_label.setToolTip(p2l_field_info.description or "")
        p2l_list_layout.addWidget(p2l_setting_label)

        self.p2l_list_widget = QListWidget()
        self.p2l_list_widget.setMinimumWidth(160)
        self._populate_list_widget(self.p2l_list_widget, currency_settings.poe2leagues, "Currency", "poe2leagues")
        self.p2l_list_widget.currentItemChanged.connect(
            partial(self.process_qlw, "Currency", "poe2leagues", self.p2l_list_widget)
        )
        p2l_list_layout.addWidget(self.p2l_list_widget)
        rightthird_layout.addLayout(p2l_list_layout)

        # poe2 leagues button
        self.get_poe2_leagues_button: QPushButton = QPushButton("Get PoE2 leagues")
        self.get_poe2_leagues_button.setToolTip("Replace the PoE2 leagues with the list from GGG")
        self.get_poe2_leagues_button.clicked.connect(self.get_poe2_leagues)
        rightthird_layout.addWidget(self.get_poe2_leagues_button)

        # active league field
        al_setting_label: QLabel = QLabel("Active league")
        al_field_info = currency_settings.__class__.model_fields["active_league"]
        al_setting_label.setToolTip(al_field_info.description or "")
        self.active_league_le: QLineEdit = QLineEdit(str(currency_settings.active_league))
        self.active_league_le.setReadOnly(True)
        rightthird_layout.addWidget(al_setting_label)
        rightthird_layout.addWidget(self.active_league_le)

        self.side_settings_layout.addLayout(rightthird_layout, 1)

        # React to external setting changes and update widgets
        try:
            self.settings_manager.settings_changed.connect(self._on_setting_changed)
        except AttributeError:
            logger.exception("Failed to connect settings_changed signal")

    def _make_list_item_widget(
        self, text: str, list_widget: QListWidget, category: str, setting: str, *, allow_remove: bool = True
    ) -> QWidget:
        """Create a QWidget containing a label and an 'X' remove button for a list item.

        The remove button will delete the item from the QListWidget and update settings.

        Args:
            text (str): The text to display for the item.
            list_widget (QListWidget): The list widget to which the item belongs.
            category (str): Settings category name.
            setting (str): Settings field name to update when item removed.
            allow_remove (bool): Whether to enable the remove button. Should be False if this is the last item.

        Returns:
            QWidget: A widget containing the label and remove button.

        """
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        label = QLabel(text)
        layout.addWidget(label, stretch=1)
        remove_btn = QPushButton("X")
        remove_btn.setFixedWidth(28)
        remove_btn.setEnabled(bool(allow_remove))
        if allow_remove:
            remove_btn.clicked.connect(partial(self._remove_list_item, list_widget, text, category, setting))
        else:
            # If removal is not allowed (last item), give a tooltip explaining why
            remove_btn.setToolTip("Cannot remove the last item")
        layout.addWidget(remove_btn)
        return container

    def _remove_list_item(self, list_widget: QListWidget, text: str, category: str, setting: str) -> None:  # noqa: C901, PLR0912
        """Remove the first matching item with `text` from `list_widget` and save settings.

        Args:
            list_widget (QListWidget): The widget to remove the item from.
            text (str): The item text to match and remove.
            category (str): Settings category name.
            setting (str): Settings field name to update.

        Returns:
            None

        """
        # Prevent removing the final item in the list
        if list_widget.count() <= 1:
            return

        for i in range(list_widget.count()):
            item = list_widget.item(i)
            if item is None:
                continue
            w = list_widget.itemWidget(item)  # If we've set a custom widget for this item, read its label
            item_text = None
            if w is not None:
                lbl = w.findChild(QLabel)
                if lbl is not None:
                    item_text = lbl.text()
            else:
                item_text = item.text()
            if item_text == text:
                # Clean up the attached widget to avoid orphaned overlays
                if w is not None:
                    with contextlib.suppress(Exception):
                        list_widget.removeItemWidget(item)
                    with contextlib.suppress(Exception):
                        w.setParent(None)
                    with contextlib.suppress(Exception):
                        w.deleteLater()
                list_widget.takeItem(i)
                break
        # Update remove-button state immediately so the last remaining item
        # is shown as unremovable in the UI without waiting for debounced
        # persistence.
        try:
            remaining = list_widget.count()
            for j in range(remaining):
                it2 = list_widget.item(j)
                if it2 is None:
                    continue
                w2 = list_widget.itemWidget(it2)
                if w2 is None:
                    continue
                # Find the remove QPushButton within the custom widget
                try:
                    btn = w2.findChild(QPushButton)
                except (AttributeError, TypeError):
                    btn = None
                if btn is None:
                    continue
                if remaining <= 1:
                    btn.setEnabled(False)
                    btn.setToolTip("Cannot remove the last item")
                else:
                    btn.setEnabled(True)
                    btn.setToolTip("")
        except (AttributeError, TypeError, RuntimeError):
            logger.exception("Failed to update remove-button state after removal %s.%s", category, setting)

        # Persist the new list to settings (debounced)
        try:
            self.process_qlw(category, setting, list_widget)
        except (AttributeError, TypeError, ValueError, settings.ValidationError):
            logger.exception("Failed to persist list after removal %s.%s", category, setting)

    def _populate_list_widget(
        self, list_widget: QListWidget, items: Iterable[str] | None, category: str, setting: str
    ) -> None:
        """Clear and populate `list_widget` with `items`, using item widgets with remove buttons.

        Args:
            list_widget (QListWidget): The list widget to populate.
            items (Iterable[str] | None): Iterable of item texts to populate.
            category (str): Settings category name.
            setting (str): Settings field name to update when items change.

        Returns:
            None

        """
        # Remove and delete any existing item widgets to avoid orphaned widgets
        for j in range(list_widget.count()):
            it = list_widget.item(j)
            if it is None:
                continue
            w = list_widget.itemWidget(it)
            if w is not None:
                with contextlib.suppress(Exception):
                    list_widget.removeItemWidget(it)
                with contextlib.suppress(Exception):
                    w.setParent(None)
                with contextlib.suppress(Exception):
                    w.deleteLater()
        list_widget.clear()
        if not items:
            return
        # Ensure deterministic order for sets
        if isinstance(items, set):
            items = sorted(items)
        items_list = list(items) if items is not None else []
        total = len(items_list)
        for it in items_list:
            lw_item = QListWidgetItem()
            # Disable remove when this is the only item
            widget = self._make_list_item_widget(str(it), list_widget, category, setting, allow_remove=(total > 1))
            lw_item.setSizeHint(widget.sizeHint())
            list_widget.addItem(lw_item)
            list_widget.setItemWidget(lw_item, widget)

    def process_qle_text(self, category: str, setting: str, qle: QLineEdit) -> None:
        """Process input for a specific text setting.

        Args:
            category (str): Settings category name.
            setting (str): Settings field name to update.
            qle (QLineEdit): The QLineEdit containing the new text.

        Returns:
            None

        """
        try:
            settings_obj = getattr(self, "_settings_cache", None) or self.settings_manager.settings
            setattr(getattr(settings_obj, category.lower()), setting.lower(), qle.text())
            self._settings_cache = settings_obj
            self._schedule_persist_settings()
        except (AttributeError, TypeError, ValueError, settings.ValidationError):
            logger.exception("Failed to set text setting %s.%s", category, setting)

    def process_qle_float(self, category: str, setting: str, qle: QLineEdit) -> None:
        """Process input for a specific float setting.

        Args:
            category (str): Settings category name.
            setting (str): Settings field name to update.
            qle (QLineEdit): The QLineEdit containing the new numeric text.

        Returns:
            None

        """
        try:
            value = float(qle.text())
            settings_obj = getattr(self, "_settings_cache", None) or self.settings_manager.settings
            setattr(getattr(settings_obj, category.lower()), setting.lower(), value)
            self._settings_cache = settings_obj
            self._schedule_persist_settings()
        except ValueError:
            pass  # Invalid float input; ignore
        except (AttributeError, TypeError, settings.ValidationError):
            logger.exception("Failed to set float setting %s.%s", category, setting)

    def process_qle_int(self, category: str, setting: str, qle: QLineEdit) -> None:
        """Process input for a specific integer setting.

        Args:
            category (str): Settings category name.
            setting (str): Settings field name to update.
            qle (QLineEdit): The QLineEdit containing the new numeric text.

        Returns:
            None

        """
        try:
            value = int(qle.text())
            settings_obj = getattr(self, "_settings_cache", None) or self.settings_manager.settings
            setattr(getattr(settings_obj, category.lower()), setting.lower(), value)
            self._settings_cache = settings_obj
            self._schedule_persist_settings()
        except ValueError:
            pass  # Invalid int input; ignore
        except (AttributeError, TypeError, settings.ValidationError):
            logger.exception("Failed to set int setting %s.%s", category, setting)

    def process_qcb(self, category: str, setting: str, checkbox: QCheckBox) -> None:
        """Process input for a specific boolean setting.

        Args:
            category (str): Settings category name.
            setting (str): Settings field name to update.
            checkbox (QCheckBox): The checkbox widget with the new state.

        Returns:
            None

        """
        try:
            settings_obj = getattr(self, "_settings_cache", None) or self.settings_manager.settings
            setattr(getattr(settings_obj, category.lower()), setting.lower(), checkbox.isChecked())
            self._settings_cache = settings_obj
            # Apply immediate UI change for always_on_top so the main window
            # updates right away instead of waiting for debounced persistence.
            if category.lower() == "gui" and setting.lower() == "always_on_top":
                try:
                    self.toggle_always_on_top(desired=checkbox.isChecked())
                except (AttributeError, RuntimeError, TypeError):
                    logger.exception("Failed to toggle always-on-top UI state immediately: %s")
            # Apply immediate UI change for minimize-to-tray so the behavior
            # takes effect without waiting for debounced persistence.
            if category.lower() == "gui" and setting.lower() == "minimize_to_tray":
                try:
                    self.toggle_minimize_to_tray(desired=checkbox.isChecked())
                except (AttributeError, RuntimeError, TypeError):
                    logger.exception("Failed to toggle minimize-to-tray UI state immediately")
            self._schedule_persist_settings()
        except (AttributeError, TypeError, settings.ValidationError):
            logger.exception("Failed to set checkbox setting %s.%s", category, setting)

    def process_qlw(self, category: str, setting: str, list_widget: QListWidget, *_: object) -> None:
        """Process input for a specific list setting.

        Accepts extra positional args from Qt signals and ignores them.

        Args:
            category (str): Settings category name.
            setting (str): Settings field name to update.
            list_widget (QListWidget): The widget containing the items.
            _ (object): Extra ignored args from Qt signals.

        Returns:
            None

        """
        # Collect the current items from the QListWidget and store them in settings
        items: list[str] = []
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            if item is None:
                continue
            # If we've set a custom widget, read the QLabel inside it; otherwise fall back to item.text()
            widget = list_widget.itemWidget(item)
            if widget is not None:
                lbl = widget.findChild(QLabel)
                if lbl is not None:
                    items.append(lbl.text())
                    continue
            text = item.text()
            if text:
                items.append(text)
        try:
            settings_obj = getattr(self, "_settings_cache", None) or self.settings_manager.settings
            # If updating currency order lists, delegate conversion to settings/currency helpers
            if category.lower() == "currency" and setting.lower() in ("poe1currencies", "poe2currencies"):
                game = settings_obj.currency.active_game
                league = settings_obj.currency.active_league
                raw = getattr(settings_obj.currency, setting.lower()) or {}
                try:
                    mapping = currency.compute_mapping_from_order(
                        game, league, items, existing_raw=raw, autoupdate=settings_obj.currency.autoupdate
                    )
                except (LookupError, ValueError, TypeError):
                    # Fallback to a conservative mapping (1 for each) if helper fails
                    mapping = dict.fromkeys(items, 1)
                setattr(getattr(settings_obj, category.lower()), setting.lower(), mapping)
            else:
                setattr(getattr(settings_obj, category.lower()), setting.lower(), items)

            # Cache and debounce persisting to avoid synchronous disk I/O on the UI thread
            self._settings_cache = settings_obj
            self._schedule_persist_settings()
        except (AttributeError, TypeError, ValueError, settings.ValidationError):
            logger.exception("Failed to update list setting %s.%s", category, setting)

    def _schedule_persist_settings(self, delay_ms: int = 200) -> None:
        """Schedule persisting cached settings after a short debounce delay.

        Subsequent calls while a persist is scheduled are ignored.
        """
        if getattr(self, "_persist_scheduled", False):
            return
        self._persist_scheduled = True
        QTimer.singleShot(delay_ms, self._flush_cached_settings)

    def _flush_cached_settings(self) -> None:
        """Persist cached settings via SettingsManager and refresh the cache."""
        self._persist_scheduled = False
        try:
            if getattr(self, "_settings_cache", None) is not None:
                self.settings_manager.set_settings(self._settings_cache)
                # Refresh cache from manager to pick up any normalization
                self._settings_cache = self.settings_manager.settings
        except (OSError, settings.YAMLError, settings.ValidationError, TypeError, ValueError):
            logger.exception("Failed to persist cached settings: %s")

    def _on_setting_changed(self, full_field: str, value: object) -> None:
        """Slot called when a setting is changed; updates the corresponding widget.

        The `full_field` is in the form "category.field".

        Args:
            full_field (str): Dot-separated field name ("category.field").
            value (object): New value for the setting.

        Returns:
            None

        """
        try:
            category, setting = full_field.split(".", 1)
        except ValueError:
            return
        category = category.lower()
        setting = setting.lower()

        if category == "keys":
            self._handle_key_setting(setting, value)
        elif category == "logic":
            self._handle_logic_setting(setting, value)
        elif category == "currency":
            self._handle_currency_setting(setting, value)
        elif category == "gui":
            self._handle_gui_setting(setting, value)

    def _handle_key_setting(self, setting: str, value: object) -> None:
        """Update key-related widgets when settings change.

        Args:
            setting (str): The specific key setting name.
            value (object): The new value for the setting.

        Returns:
            None

        """
        if setting in getattr(self, "key_lineedits", {}):
            le = self.key_lineedits[setting]
            with QSignalBlocker(le):
                le.setText(str(value))

    def _handle_logic_setting(self, setting: str, value: object) -> None:
        """Update logic-related widgets when settings change.

        Args:
            setting (str): Logic field name.
            value (object): New value for the logic setting.

        Returns:
            None

        """
        if setting == "discount_percent":
            with QSignalBlocker(self.discount_percent_le):
                self.discount_percent_le.setText(str(value))
        elif setting == "max_actual_discount":
            with QSignalBlocker(self.max_actual_discount_le):
                self.max_actual_discount_le.setText(str(value))
        elif setting == "enter_after_calcprice":
            with QSignalBlocker(self.enter_after_cb):
                self.enter_after_cb.setChecked(bool(value))

    def _handle_gui_setting(self, setting: str, value: object) -> None:
        """Update GUI-related widgets when settings change.

        Args:
            setting (str): GUI field name.
            value (object): New value for the GUI setting.

        Returns:
            None

        """
        if setting == "always_on_top":
            with QSignalBlocker(self.always_on_top_cb):
                self.always_on_top_cb.setChecked(bool(value))
            # Also update the main window flag to match the new setting
            try:
                self.toggle_always_on_top(desired=bool(value))
            except (AttributeError, RuntimeError, TypeError):
                logger.exception("Failed to toggle always-on-top from settings change: %s")
        elif setting == "minimize_to_tray":
            with QSignalBlocker(self.minimize_to_tray_cb):
                self.minimize_to_tray_cb.setChecked(bool(value))

    def _handle_currency_setting(self, setting: str, value: object) -> None:
        """Handle updates for currency-related settings.

        Args:
            setting (str): Currency settings field name.
            value (object): New value for the field.

        Returns:
            None

        """
        if setting == "assume_highest_currency":
            with QSignalBlocker(self.assume_highest_currency_cb):
                self.assume_highest_currency_cb.setChecked(bool(value))
        elif setting == "poe1currencies":
            with QSignalBlocker(self.p1c_list_widget):
                val = value or []
                items = list(val) if isinstance(val, Iterable) else []
                self._populate_list_widget(self.p1c_list_widget, items, "Currency", "poe1currencies")
            self.populate_currency_list()
        elif setting == "poe2currencies":
            with QSignalBlocker(self.p2c_list_widget):
                val = value or []
                items = list(val) if isinstance(val, Iterable) else []
                self._populate_list_widget(self.p2c_list_widget, items, "Currency", "poe2currencies")
            self.populate_currency_list()
        elif setting == "active_game":
            with QSignalBlocker(self.active_game_le):
                self.active_game_le.setText(str(value))
            self.populate_currency_list()
        elif setting == "active_league":
            with QSignalBlocker(self.active_league_le):
                self.active_league_le.setText(str(value))
        elif setting == "autoupdate":
            with QSignalBlocker(self.autoupdate_cb):
                self.autoupdate_cb.setChecked(bool(value))
        elif setting == "poe1leagues":
            with QSignalBlocker(self.p1l_list_widget):
                val = value or []
                items = list(val) if isinstance(val, Iterable) else []
                self._populate_list_widget(self.p1l_list_widget, items, "Currency", "poe1leagues")
            # update combo without triggering its signals
            with QSignalBlocker(self.league_combo):
                self.populate_league_combo()
        elif setting == "poe2leagues":
            with QSignalBlocker(self.p2l_list_widget):
                val = value or []
                items = list(val) if isinstance(val, Iterable) else []
                self._populate_list_widget(self.p2l_list_widget, items, "Currency", "poe2leagues")
            with QSignalBlocker(self.league_combo):
                self.populate_league_combo()

    def toggle_always_on_top(self, *, desired: bool | None = None) -> None:
        """Toggle the always-stays-on-top window flag.

        Returns:
            None

        """
        # Determine desired state: prefer explicit `desired` argument, then
        # fall back to cached GUI settings, then to persisted settings.
        if desired is not None:
            always_on_top = bool(desired)
        else:
            gui_settings = getattr(self, "_settings_cache", None)
            if gui_settings is not None:
                always_on_top = bool(gui_settings.gui.always_on_top)
            else:
                always_on_top = bool(settings.settings_manager.settings.gui.always_on_top)

        # Evaluate current flag once and compare explicitly.
        current_flag = bool(self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        if always_on_top and not current_flag:
            self.hide()
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, on=True)
            self.show()
        elif (not always_on_top) and current_flag:
            self.hide()
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, on=False)
            self.show()

    def _setup_tray_icon(self) -> None:  # noqa: C901
        """Create the system tray icon and its context menu."""
        # Guard against environments with no system tray support
        try:
            if not QSystemTrayIcon.isSystemTrayAvailable():
                logger.warning("System tray not available on this platform; minimize-to-tray disabled")
                return
        except Exception:
            # If the call fails for any reason, skip tray setup
            logger.exception("Failed to query system tray availability")
            return

        # Use existing app icon if set, otherwise fallback to bundled icon file
        icon = self.windowIcon() if not self.windowIcon().isNull() else QIcon(str(icon_path))

        # Create menu and actions (keep persistent parent references)
        menu = QMenu(self)
        show_action = QAction("Show PoEMarcut", self)
        # Hotkeys state action - reflects current state and toggles hotkeys when clicked
        hotkeys_text = "Hotkeys Enabled" if getattr(self, "hotkeys_enabled", False) else "Hotkeys Disabled"
        hotkeys_action = QAction(hotkeys_text, self)
        quit_action = QAction("Quit", self)
        menu.addAction(show_action)
        menu.addAction(hotkeys_action)
        menu.addSeparator()
        menu.addAction(quit_action)

        tray = QSystemTrayIcon(icon, self)
        tray.setContextMenu(menu)
        tray.setToolTip("PoEMarcut")

        def _on_show_triggered() -> None:
            try:
                self.show()
                # restore window state and raise
                self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
                self.activateWindow()
            except Exception:
                logger.exception("Failed to restore window from tray")

        def _on_quit_triggered() -> None:
            app = QApplication.instance()
            if app is not None:
                try:
                    app.quit()
                except Exception:
                    logger.exception("Failed to quit application from tray menu")

        show_action.triggered.connect(_on_show_triggered)
        hotkeys_action.triggered.connect(self.toggle_hotkeys)
        quit_action.triggered.connect(_on_quit_triggered)

        def _on_tray_activated(reason: QSystemTrayIcon.ActivationReason) -> None:
            # Restore on single-click or double-click depending on platform
            try:
                if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
                    _on_show_triggered()
            except (TypeError, RuntimeError):
                logger.exception("Tray activation handler failed")

        tray.activated.connect(_on_tray_activated)

        # Store references and make visible
        self._tray_icon = tray
        self._tray_menu = menu  # unfortunately the menu does not seem to work on Windows
        # Keep a reference to the hotkeys action so we can update its text when state changes
        self._tray_hotkeys_action = hotkeys_action
        try:
            tray.setVisible(True)
        except (RuntimeError, OSError):
            logger.exception("Failed to show system tray icon")

    def toggle_minimize_to_tray(self, *, desired: bool | None = None) -> None:
        """Enable or disable minimize-to-tray behavior and manage the tray icon.

        If `desired` is None, the current cached settings are consulted.
        """
        if desired is not None:
            enable = bool(desired)
        else:
            gui_settings = getattr(self, "_settings_cache", None)
            if gui_settings is not None:
                enable = bool(gui_settings.gui.minimize_to_tray)
            else:
                enable = bool(settings.settings_manager.settings.gui.minimize_to_tray)

        if enable:
            # Create tray icon if not already present
            if self._tray_icon is None:
                self._setup_tray_icon()
        # Hide and remove tray icon if present
        elif self._tray_icon is not None:
            try:
                self._tray_icon.hide()
            except (RuntimeError, OSError):
                logger.exception("Failed to hide tray icon")
            # clear references so icon/menu can be GC'd; ignore errors during cleanup
            with contextlib.suppress(Exception):
                self._tray_icon.setContextMenu(None)
            self._tray_icon = None
            self._tray_menu = None
            self._tray_hotkeys_action = None

    def changeEvent(self, event: QEvent) -> None:  # type: ignore[override]  # noqa: N802
        """Handle window state changes to implement minimize-to-tray behavior."""
        try:
            if event is not None and event.type() == QEvent.Type.WindowStateChange:
                # If the window was minimized and minimize-to-tray is enabled,
                # hide the window and keep the app running with a tray icon.
                minimized = bool(self.windowState() & Qt.WindowState.WindowMinimized)
                gui_settings = getattr(self, "_settings_cache", None)
                enabled = (
                    bool(gui_settings.gui.minimize_to_tray)
                    if gui_settings is not None
                    else bool(settings.settings_manager.settings.gui.minimize_to_tray)
                )
                if minimized and enabled:
                    # Ensure tray exists
                    if self._tray_icon is None:
                        self._setup_tray_icon()
                    # Hide window instead of showing in taskbar
                    try:
                        self.hide()
                    except Exception:
                        logger.exception("Failed to hide window for minimize-to-tray")
        except Exception:
            logger.exception("Error during changeEvent handling")
        # Always call base implementation
        with contextlib.suppress(Exception):
            super().changeEvent(event)  # type: ignore[misc]

    def toggle_settings_window(self) -> None:
        """Toggle visibility of the settings window.

        Returns:
            None

        """
        # Show/hide the separate top-level settings window and position it
        try:
            if self.settings_window.isVisible():
                self.settings_window.hide()
            else:
                # position to the right of the main window using frameGeometry to account for window decorations
                frame = self.frameGeometry()
                x = frame.x() + frame.width()
                y = frame.y()
                # Size to the layout's minimum hint so the window opens at minimal width
                self.settings_window.adjustSize()
                min_w = self.settings_window.minimumSizeHint().width()
                min_h = self.settings_window.sizeHint().height()
                self.settings_window.setMinimumWidth(min_w)
                self.settings_window.resize(min_w, min_h)
                self.settings_window.move(x, y)
                self.settings_window.show()
        except AttributeError:
            # fallback (shouldn't occur)
            return

    def eventFilter(self, a0: QObject | None, a1: QEvent | None) -> bool:  # noqa: N802 - Qt override uses camelCase
        """Track move events to keep the settings window positioned to the right.

        Args:
            a0 (QObject | None): The watched object.
            a1 (QEvent | None): The event being filtered.

        Returns:
            bool: True if the event was handled, otherwise delegates to super.

        """
        if (
            a0 is self
            and a1 is not None
            and a1.type() == QEvent.Type.Move
            and getattr(self, "settings_window", None) is not None
            and self.settings_window.isVisible()
        ):
            # Use frameGeometry to include the window frame/title bar
            frame = self.frameGeometry()
            x = frame.x() + frame.width() + 8
            y = frame.y()
            self.settings_window.move(x, y)
        return super().eventFilter(a0, a1)

    def closeEvent(self, a0: QCloseEvent | None) -> None:  # noqa: N802 pyqt override uses camelCase
        """Ensure the settings window is closed and the application exits when main window closes.

        Args:
            a0 (QCloseEvent | None): The close event passed by Qt.

        Returns:
            None

        """
        try:
            if getattr(self, "settings_window", None) is not None:
                # Close the secondary settings window if it's open
                with contextlib.suppress(RuntimeError):
                    self.settings_window.close()
        except (AttributeError, RuntimeError):
            logger.exception("Error while closing settings window during main window shutdown")
        # Quit the QApplication so the process exits even if other windows were open
        app = QApplication.instance()
        if app is not None:
            try:
                app.quit()
            except (RuntimeError, OSError):
                logger.exception("Failed to quit QApplication from closeEvent")
        # Accept the close event to proceed with shutdown (guard if None)
        if a0 is not None:
            a0.accept()

    def toggle_hotkeys(self) -> None:
        """Enable or disable the keyboard hotkeys listener.

        Returns:
            None

        """
        if not self.hotkeys_enabled:
            try:
                listener = keyboard.start_listener(blocking=False, on_stop=self._notify_hotkeys_listener_stopped)
            except (RuntimeError, OSError):
                logger.exception("Failed to start hotkeys listener.")
                return

            if listener is None:
                logger.warning("Hotkeys listener did not start (blocking returned None).")
                return

            self._set_hotkeys_ui_state(enabled=True)
        else:
            try:
                keyboard.stop_listener()
            except (RuntimeError, OSError):
                logger.exception("Failed to stop hotkeys listener.")
            self._set_hotkeys_ui_state(enabled=False)

    def _notify_hotkeys_listener_stopped(self) -> None:
        """Notify the GUI thread that the listener has stopped itself.

        Returns:
            None

        """
        self.hotkeys_listener_stopped.emit()

    def _on_hotkeys_listener_stopped(self) -> None:
        """Update button and indicator when listener exits from stop_key.

        Returns:
            None

        """
        self._set_hotkeys_ui_state(enabled=False)

    def _set_hotkeys_ui_state(self, *, enabled: bool) -> None:
        """Set hotkeys button text and indicator to match listener state.

        Args:
            enabled (bool): Whether hotkeys are enabled.

        Returns:
            None

        """
        self.hotkeys_enabled = enabled
        if enabled:
            self.hotkeys_button.setText("Disable hotkeys")
            self.indicator.setStyleSheet(qradiobutton_greenlight)
            self.indicator.setToolTip("Hotkeys enabled")
            # Update tray menu action text if present
            if self._tray_hotkeys_action is not None:
                try:
                    self._tray_hotkeys_action.setText("Hotkeys Enabled")
                except Exception:
                    logger.exception("Failed to update tray hotkeys action text to enabled")
            return
        self.hotkeys_button.setText("Enable hotkeys")
        self.indicator.setStyleSheet(qradiobutton_redlight)
        self.indicator.setToolTip("Hotkeys disabled")
        if self._tray_hotkeys_action is not None:
            try:
                self._tray_hotkeys_action.setText("Hotkeys Disabled")
            except Exception:
                logger.exception("Failed to update tray hotkeys action text to disabled")

    def populate_league_combo(self) -> None:
        """Populate the league combo box.

        Returns:
            None

        """
        settings_man: settings.SettingsManager = self.settings_manager
        self.league_combo.clear()
        # Map displayed item text -> original league id for reverse lookup
        self._league_display_to_id = {}
        for poe1league in settings_man.settings.currency.poe1leagues:
            display = LEAGUE_DISPLAY_OVERRIDES.get(poe1league.lower(), poe1league)
            item_text = f"{display} [PoE1]"
            self.league_combo.addItem(item_text)
            self._league_display_to_id[item_text] = poe1league
        for poe2league in settings_man.settings.currency.poe2leagues:
            display = LEAGUE_DISPLAY_OVERRIDES.get(poe2league.lower(), poe2league)
            item_text = f"{display} [PoE2]"
            self.league_combo.addItem(item_text)
            self._league_display_to_id[item_text] = poe2league
        # Select the currently active game/league from settings, if present
        try:
            active_game = settings_man.settings.currency.active_game
            active_league = settings_man.settings.currency.active_league
            desired_display = LEAGUE_DISPLAY_OVERRIDES.get(active_league.lower(), active_league)
            desired = f"{desired_display} [PoE1]" if active_game == 1 else f"{desired_display} [PoE2]"
            # Find and set without emitting signals
            idx = -1
            for i in range(self.league_combo.count()):
                if self.league_combo.itemText(i) == desired:
                    idx = i
                    break
            if idx >= 0:
                with QSignalBlocker(self.league_combo):
                    self.league_combo.setCurrentIndex(idx)
        except (AttributeError, TypeError, IndexError):
            logger.exception("Failed to set league_combo to active league from settings")

    def _make_currency_display_widget(self, currency_name: str, value_text: str | None) -> QWidget:
        """Create a compact QWidget showing a currency name and a value label beside it.

        `value_text` is expected to already be formatted (e.g. "100.00 chaos").

        Args:
            currency_name (str): The currency display name.
            value_text (str | None): Preformatted value text to show next to the name.

        Returns:
            QWidget: A small widget containing the currency name and value.

        """
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(4, 0, 4, 0)
        name_lbl = QLabel(currency_name)
        val_lbl = QLabel(value_text or "")
        val_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        layout.addWidget(name_lbl)
        layout.addWidget(val_lbl)
        layout.addStretch()
        return container

    def populate_currency_list(self) -> None:  # noqa: C901, PLR0912, PLR0915
        """Populate the main currency list for the currently active game.

        Returns:
            None

        """
        currency_settings = self.settings_manager.settings.currency
        raw_currencies = (
            currency_settings.poe1currencies if currency_settings.active_game == 1 else currency_settings.poe2currencies
        )
        currencies = list(raw_currencies.keys())

        # Refresh stored mapping values from live exchange rates for the active game/league.
        # Use a guard to avoid recursive re-entry when persisting settings_changed signals fire.
        self._updating_currency_values = getattr(self, "_updating_currency_values", False)
        game = currency_settings.active_game
        league = currency_settings.active_league
        if currencies and not self._updating_currency_values:
            try:
                updated_map: dict[str, int] = currency.compute_mapping_from_order(
                    game, league, currencies, existing_raw=raw_currencies, autoupdate=currency_settings.autoupdate
                )
            except (LookupError, ValueError, TypeError):
                # Fallback: preserve existing stored values where possible, else conservative 1
                updated_map = {}
                for name in currencies:
                    try:
                        updated_map[name] = int(raw_currencies.get(name, 1))
                    except (TypeError, ValueError):
                        updated_map[name] = 1

            # Persist only if mapping changed
            if updated_map != raw_currencies:
                try:
                    self._updating_currency_values = True
                    current = self.settings_manager.settings
                    new_settings = settings.PoEMSettings(
                        keys=settings.KeySettings(**current.keys.model_dump()),
                        logic=settings.LogicSettings(**current.logic.model_dump()),
                        currency=settings.CurrencySettings(**current.currency.model_dump()),
                        gui=settings.GuiSettings(**current.gui.model_dump()),
                    )
                    if currency_settings.active_game == 1:
                        new_settings.currency.poe1currencies = updated_map
                    else:
                        new_settings.currency.poe2currencies = updated_map
                    self.settings_manager.set_settings(new_settings)
                except (AttributeError, TypeError, ValueError, settings.ValidationError, RuntimeError, OSError):
                    logger.exception("Failed to persist updated currency mapping from exchange rates")
                finally:
                    self._updating_currency_values = False

        self.currency_list.clear()  # clear existing items before repopulating
        # Add a non-interactive header item at the top of the list
        header = QListWidgetItem("Configured currency conversions:")
        header.setFlags(Qt.ItemFlag.NoItemFlags)
        header.setTextAlignment(Qt.AlignmentFlag.AlignLeft)
        self.currency_list.addItem(header)
        if not currencies:
            return
        game = currency_settings.active_game
        league = currency_settings.active_league
        for idx, c in enumerate(currencies):
            # Compute rate of this currency in terms of the next currency (if any)
            rate: float | None = None
            rate_text = ""
            lower = currencies[idx + 1] if idx != len(currencies) - 1 else None
            if lower is not None:
                try:
                    rate = currency.get_exchange_rate(game, league, c, lower, autoupdate=currency_settings.autoupdate)
                    rate_text = f"({rate:.2f} {lower})"
                except (LookupError, ValueError, TypeError):
                    rate = None
                    rate_text = ""

            # For the final currency (no lower), display "(final)" as its value.
            display_value = rate_text if lower is not None else "(final)"
            widget = self._make_currency_display_widget(str(c), display_value)
            lw_item = QListWidgetItem()
            lw_item.setSizeHint(widget.sizeHint())
            self.currency_list.addItem(lw_item)
            self.currency_list.setItemWidget(lw_item, widget)

            # Always insert an arrow row after the currency row (final or not)
            try:
                adj: int = int(self.settings_manager.settings.logic.max_actual_discount)
            except (AttributeError, TypeError, ValueError):
                adj = 0
            arrow_text = "↓"
            if adj:
                arrow_text = f"↓ if 1 or discount >{adj}%"

            arrow_widget = QWidget()
            arrow_layout = QHBoxLayout(arrow_widget)
            arrow_layout.setContentsMargins(4, 0, 4, 0)
            arrow_label = QLabel(arrow_text)
            arrow_label.setStyleSheet(f"color: {poe_header_text_color};")
            arrow_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            arrow_layout.addWidget(arrow_label)
            arrow_layout.addStretch()
            arrow_item = QListWidgetItem()
            arrow_item.setSizeHint(arrow_widget.sizeHint())
            arrow_item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.currency_list.addItem(arrow_item)
            self.currency_list.setItemWidget(arrow_item, arrow_widget)

            # For non-final pairs, show the adjusted lower-currency value; for final, show 'vendor it'.
            if lower is not None and rate is not None:
                try:
                    discount = float(self.settings_manager.settings.logic.discount_percent)
                    adj_discount: int = round(discount)
                    adj_value = (1.0 - (discount / 100.0)) * float(rate)
                    adj_text = f"{int(adj_value)} {lower}" if adj_value >= 1 else f"1 {lower}"
                    adj_widget = self._make_currency_display_widget(f"{adj_discount}% off =", adj_text)
                    adj_item = QListWidgetItem()
                    adj_item.setSizeHint(adj_widget.sizeHint())
                    adj_item.setFlags(Qt.ItemFlag.NoItemFlags)
                    adj_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft)
                    self.currency_list.addItem(adj_item)
                    self.currency_list.setItemWidget(adj_item, adj_widget)
                except (AttributeError, TypeError, ValueError):
                    pass
            else:
                # Final currency: add a vendor-it adjusted item
                try:
                    vendor_widget = self._make_currency_display_widget("=", "vendor it")
                    vendor_item = QListWidgetItem()
                    vendor_item.setSizeHint(vendor_widget.sizeHint())
                    vendor_item.setFlags(Qt.ItemFlag.NoItemFlags)
                    vendor_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft)
                    self.currency_list.addItem(vendor_item)
                    self.currency_list.setItemWidget(vendor_item, vendor_widget)
                except (AttributeError, RuntimeError, TypeError, ValueError):
                    logger.exception("Failed to add vendor item to currency list")

            # Add a small non-interactive vertical spacer after each currency pair group
            try:
                spacer_height = 8
                spacer_widget = QWidget()
                spacer_widget.setFixedHeight(spacer_height)
                spacer_item = QListWidgetItem()
                spacer_item.setSizeHint(QSize(0, spacer_height))
                spacer_item.setFlags(Qt.ItemFlag.NoItemFlags)
                self.currency_list.addItem(spacer_item)
                self.currency_list.setItemWidget(spacer_item, spacer_widget)
            except (AttributeError, RuntimeError, TypeError, ValueError):
                logger.exception("Failed to add spacer after currency group")

        # Update the small label showing when the currency data was last updated
        try:
            self._update_currency_update_label()
        except (LookupError, TypeError, ValueError):
            with contextlib.suppress(Exception):
                self.currency_lastupdate_label.setText("")

    def populate_league_settings(self) -> None:
        """Refresh league-related widgets after leagues are updated.

        Returns:
            None

        """
        try:
            currency_settings = self.settings_manager.settings.currency

            # Update the PoE1/PoE2 league list widgets without emitting signals
            with QSignalBlocker(self.p1l_list_widget):
                items = currency_settings.poe1leagues if isinstance(currency_settings.poe1leagues, (set, list)) else []
                self._populate_list_widget(self.p1l_list_widget, items, "Currency", "poe1leagues")

            with QSignalBlocker(self.p2l_list_widget):
                items = currency_settings.poe2leagues if isinstance(currency_settings.poe2leagues, (set, list)) else []
                self._populate_list_widget(self.p2l_list_widget, items, "Currency", "poe2leagues")

            # Refresh the league combo and select active league without triggering signals
            with QSignalBlocker(self.league_combo):
                self.populate_league_combo()

            # Update the read-only displays for active game/league
            with QSignalBlocker(self.active_game_le):
                self.active_game_le.setText(str(currency_settings.active_game))
            with QSignalBlocker(self.active_league_le):
                self.active_league_le.setText(str(currency_settings.active_league))

            # Refresh main currency list and last-update label
            self.populate_currency_list()
        except (AttributeError, TypeError, ValueError, settings.ValidationError):
            logger.exception("Failed to populate league settings")

    def _update_currency_update_label(self) -> None:
        """Refresh `self.currency_update_label` with the latest currency mtime.

        Returns:
            None

        """
        currency_settings = self.settings_manager.settings.currency
        game = currency_settings.active_game
        league = currency_settings.active_league
        if not league:
            self.currency_lastupdate_label.setText("")
            return
        try:
            mtime = currency.get_update_time(game=game, league=league, autoupdate=currency_settings.autoupdate)
        except (LookupError, TypeError, ValueError):
            self.currency_lastupdate_label.setText("")
            return

        now = time.time()
        delta_seconds = int(max(0, now - float(mtime)))
        hours = delta_seconds // 3600
        minutes = (delta_seconds % 3600) // 60
        delta_str = f"{hours:02d}h:{minutes:02d}m"
        updated_clock = time.strftime("%I:%M %p", time.localtime(mtime))
        tz_abbr_raw = time.tzname[1] if time.localtime(mtime).tm_isdst > 0 else time.tzname[0]
        tz_abbr_filtered = "".join(ch for ch in tz_abbr_raw if "A" <= ch <= "Z")
        tz_abbr = tz_abbr_filtered or tz_abbr_raw
        self.currency_lastupdate_label.setText(
            f"Economy data for {league} last updated {delta_str} ago ({updated_clock} {tz_abbr})"
        )

    def _on_last_log_message(self, msg: str) -> None:
        """Slot invoked on the GUI thread when a new log message is emitted.

        Updates `self.log_output_label` if the message changed.

        Args:
            msg (str): The latest formatted log message.

        Returns:
            None

        """
        if not msg:
            return
        if getattr(self, "_last_log_shown", None) == msg:
            return
        try:
            # Elide long messages to fit the label's maximum width so it doesn't resize the UI.
            # Ensure we have a non-zero pixel width to elide against.
            max_w = int(self.log_output_label.maximumWidth() or self.log_output_label.sizeHint().width() or 200)
            fm = self.log_output_label.fontMetrics()
            elided = fm.elidedText(msg, Qt.TextElideMode.ElideRight, max_w)
            self.log_output_label.setText(elided)
            # Set the full message as a tooltip so users can read it on hover
            with contextlib.suppress(Exception):
                self.log_output_label.setToolTip(msg)
            self._last_log_shown = msg
        except (AttributeError, RuntimeError, TypeError):
            logger.exception("Failed to update log_output_label from emitted message")

    def _on_league_combo_changed(self, index: int) -> None:
        """Handle user selection in `league_combo` and persist active game/league.

        Items in the combo are formatted as "<league> [PoE1]" or "<league> [PoE2]".

        Args:
            index (int): The selected index in the combo box.

        Returns:
            None

        """
        try:
            text = self.league_combo.currentText() if index is None or index < 0 else self.league_combo.itemText(index)
            if not text:
                return

            # Determine game from suffix and map display text back to original id
            if text.endswith(" [PoE1]"):
                game = 1
            elif text.endswith(" [PoE2]"):
                game = 2
            else:
                return

            # Prefer reverse mapping created in populate_league_combo
            league = getattr(self, "_league_display_to_id", {}).get(text)
            if league is None:
                # Fall back to the raw displayed league text (strip suffix)
                league = text[: -len(" [PoE1]")] if game == 1 else text[: -len(" [PoE2]")]

            # Persist the selection (store original league id).
            # Build a fresh settings object and modify that to ensure
            # SettingsManager.set_settings sees a real change and emits
            # `settings_changed` signals.
            try:
                current = self.settings_manager.settings
                new_settings = settings.PoEMSettings(
                    keys=settings.KeySettings(**current.keys.model_dump()),
                    logic=settings.LogicSettings(**current.logic.model_dump()),
                    currency=settings.CurrencySettings(**current.currency.model_dump()),
                    gui=settings.GuiSettings(**current.gui.model_dump()),
                )
                try:
                    with new_settings.currency.delay_validation():
                        new_settings.currency.active_game = game
                        new_settings.currency.active_league = league
                    self.settings_manager.set_settings(new_settings)
                except (AttributeError, TypeError, ValueError, settings.ValidationError):
                    # Fall back to assigning without delay_validation on a fresh copy
                    try:
                        new_settings = settings.PoEMSettings(
                            keys=settings.KeySettings(**current.keys.model_dump()),
                            logic=settings.LogicSettings(**current.logic.model_dump()),
                            currency=settings.CurrencySettings(**current.currency.model_dump()),
                            gui=settings.GuiSettings(**current.gui.model_dump()),
                        )
                        new_settings.currency.active_game = game
                        new_settings.currency.active_league = league
                        self.settings_manager.set_settings(new_settings)
                    except (AttributeError, TypeError, ValueError, settings.ValidationError):
                        logger.exception("Failed to persist active game/league from league_combo selection (fallback)")
            except (AttributeError, TypeError, ValueError, settings.ValidationError):
                logger.exception("Failed to persist active game/league from league_combo selection")
        except (AttributeError, TypeError, ValueError, settings.ValidationError):
            logger.exception("Failed to persist active game/league from league_combo selection")

    def _check_github_update(self) -> None:
        """Check for update in background and update label if needed.

        Returns:
            None

        """
        try:
            available, _ver = update.is_github_update_available()
        except (OSError, RuntimeError):
            logger.exception("Failed to check github update availability")
            return
        # Emit a signal so the GUI thread updates the label safely
        try:
            # Emit only the version string (or None). Non-None means update available.
            self.github_update_ready.emit(_ver if available else None)
        except (RuntimeError, TypeError):
            logger.exception("Failed to emit github_update_ready signal")

    def _on_github_update_ready(self, ver: str | None) -> None:
        """Slot invoked on the GUI thread when github update check completes.

        `ver` is the latest version string if an update is available, or `None` otherwise.

        Args:
            ver (str | None): Latest version string if update available, else `None`.

        Returns:
            None

        """
        try:
            if ver is not None:
                # Make the label an external link to the releases page so clicks open the browser
                self.github_update_label.setText(f'<a href="{update.GITHUB_RELEASE_URL}">🔔Update {ver} available!</a>')
                self.github_update_label.setToolTip("Click to open the releases page on GitHub")
                # Allow QLabel to open external links directly; suppress if attribute missing
                with contextlib.suppress(Exception):
                    self.github_update_label.setOpenExternalLinks(True)
                # Show pointing-hand cursor to indicate clickability; suppress failures
                with contextlib.suppress(Exception):
                    self.github_update_label.setCursor(Qt.CursorShape.PointingHandCursor)
        except (AttributeError, TypeError, RuntimeError, ValueError):
            logger.exception("Failed to update github_update_label in _on_github_update_ready")

    def add_poe1_currency(self) -> None:
        """Add a PoE1 currency from the input box to settings, then update UI list from settings.

        Returns:
            None

        """
        self._add_currency(
            game=1,
            merchant_map=constants.POE1_MERCHANT_CURRENCIES,
            setting_field="poe1currencies",
            list_widget=self.p1c_list_widget,
            dialog_title="Add PoE1 currency",
        )

    def add_poe2_currency(self) -> None:
        """Add a PoE2 currency from the input box to settings, then update UI list from settings.

        Returns:
            None

        """
        self._add_currency(
            game=2,
            merchant_map=constants.POE2_MERCHANT_CURRENCIES,
            setting_field="poe2currencies",
            list_widget=self.p2c_list_widget,
            dialog_title="Add PoE2 currency",
        )

    def _add_currency(
        self,
        *,
        game: int,
        merchant_map: Mapping[str, str],
        setting_field: str,
        list_widget: QListWidget,
        dialog_title: str,
    ) -> None:
        """Shared logic for adding a PoE currency.

        - `game`: numeric game id passed to currency.get_exchange_rate
        - `merchant_map`: mapping of id->display name from `constants`
        - `setting_field`: field name on `settings_obj.currency` (e.g. 'poe1currencies')
        - `list_widget`: the QListWidget to refresh after adding
        - `dialog_title`: title for the input dialog

        Args:
            game (int): Game id (1 or 2).
            merchant_map (Mapping[str, str]): Mapping of merchant currency id to display name.
            setting_field (str): Attribute name on `settings_obj.currency` to update.
            list_widget (QListWidget): Widget to refresh after adding.
            dialog_title (str): Title for the input dialog.

        Returns:
            None

        """
        try:
            settings_obj = self.settings_manager.settings
            currency_settings = settings_obj.currency
            raw = getattr(currency_settings, setting_field) or {}

            # Show only currencies not already configured
            valid_keys = [k for k in merchant_map if k not in raw]
            if not valid_keys:
                return

            # Display friendly labels but keep a map back to the key
            display_map: dict[str, str] = {}
            display_items: list[str] = []
            for k in valid_keys:
                label = f"{merchant_map.get(k, k)}"
                display_items.append(label)
                display_map[label] = k

            choice, ok = QInputDialog.getItem(
                self, dialog_title, "Select currency:", display_items, current=0, editable=False
            )
            if not ok or not choice:
                return

            chosen_key = display_map.get(choice)
            if not chosen_key:
                return
            try:
                self.settings_manager.add_currency_and_persist(
                    game=game, setting_field=setting_field, chosen_key=chosen_key
                )
            except (AttributeError, TypeError, ValueError, settings.ValidationError, RuntimeError, OSError):
                logger.exception("Failed to persist added currency %s to %s", chosen_key, setting_field)
                return

            # Refresh UI list from settings
            try:
                with QSignalBlocker(list_widget):
                    updated = getattr(self.settings_manager.settings.currency, setting_field) or {}
                    self._populate_list_widget(list_widget, list(updated.keys()), "Currency", setting_field)
                self.populate_currency_list()
            except (AttributeError, RuntimeError, TypeError, ValueError):
                logger.exception("Failed to refresh currency UI for %s after adding %s", setting_field, chosen_key)
        except (AttributeError, TypeError, ImportError):
            logger.exception("Failed in _add_currency for %s", setting_field)

    def get_poe1_leagues(self) -> None:
        """Get PoE1 leagues, update settings, then update UI.

        Returns:
            None

        """
        # Fetch leagues in background to avoid blocking the GUI thread
        try:
            threading.Thread(target=lambda: self._fetch_leagues_bg(1), daemon=True).start()
            # Disable the button while fetch is in progress
            with contextlib.suppress(Exception):
                self.get_poe1_leagues_button.setEnabled(False)
        except (AttributeError, TypeError, ValueError, settings.ValidationError, RuntimeError, OSError):
            # Fallback to synchronous behavior if threading fails
            self._update_leagues_and_ui(game=1, setting_attr="poe1leagues")

    def get_poe2_leagues(self) -> None:
        """Get PoE2 leagues, update settings, then update UI.

        Returns:
            None

        """
        # Fetch leagues in background to avoid blocking the GUI thread
        try:
            threading.Thread(target=lambda: self._fetch_leagues_bg(2), daemon=True).start()
            # Disable the button while fetch is in progress
            with contextlib.suppress(Exception):
                self.get_poe2_leagues_button.setEnabled(False)
        except (AttributeError, TypeError, ValueError, settings.ValidationError, RuntimeError, OSError):
            # Fallback to synchronous behavior if threading fails
            self._update_leagues_and_ui(game=2, setting_attr="poe2leagues")

    def _update_leagues_and_ui(self, *, game: int, setting_attr: str) -> None:
        """Shared logic for updating leagues from the API and refreshing UI.

        Args:
            game (int): Game id (1 or 2).
            setting_attr (str): Attribute name on currency settings to update.

        Returns:
            None

        """
        leagues: set[str] | None = currency.get_leagues(game=game)
        try:
            current = self.settings_manager.settings
            new_settings = settings.PoEMSettings(
                keys=settings.KeySettings(**current.keys.model_dump()),
                logic=settings.LogicSettings(**current.logic.model_dump()),
                currency=settings.CurrencySettings(**current.currency.model_dump()),
                gui=settings.GuiSettings(**current.gui.model_dump()),
            )
            new_leagues = set(leagues or [])
            try:
                # Batch the update so validators run against the final consistent state
                with new_settings.currency.delay_validation():
                    setattr(new_settings.currency, setting_attr, new_leagues)
                    # If active_game matches and the active_league would become invalid,
                    # pick a sensible default from the new list to avoid transient warnings.
                    if new_settings.currency.active_game == game and (
                        new_settings.currency.active_league not in new_leagues and new_leagues
                    ):
                        new_settings.currency.active_league = sorted(new_leagues)[0]
                self.settings_manager.set_settings(new_settings)
            except (AttributeError, TypeError, ValueError):
                # Fallback to previous behavior if delay_validation isn't available or fails
                setattr(new_settings.currency, setting_attr, new_leagues)
                self.settings_manager.set_settings(new_settings)
        except (AttributeError, TypeError, ValueError, settings.ValidationError, RuntimeError, OSError):
            logger.exception("Failed to update %s from get_poe%d_leagues", setting_attr, game)
        # Always refresh UI widgets afterwards
        self.populate_league_combo()
        self.populate_league_settings()

    def _fetch_leagues_bg(self, game: int) -> None:
        """Background helper: fetch leagues and emit `leagues_ready` on completion.

        Keeps network I/O off the GUI thread. Emits (game, leagues_set_or_None).
        """
        try:
            leagues = currency.get_leagues(game=game)
        except (LookupError, TypeError, ValueError):
            leagues = None
        try:
            self.leagues_ready.emit(game, leagues)
        except (RuntimeError, TypeError):
            logger.exception("Failed to emit leagues_ready signal")

    def _on_leagues_ready(self, game: int, leagues: set | None) -> None:
        """Slot run on GUI thread when background league fetch completes.

        Persists updated leagues via settings and refreshes UI. Also re-enables
        the Get buttons that were disabled while fetching.
        """
        setting_attr = "poe1leagues" if game == 1 else "poe2leagues"
        try:
            current = self.settings_manager.settings
            new_settings = settings.PoEMSettings(
                keys=settings.KeySettings(**current.keys.model_dump()),
                logic=settings.LogicSettings(**current.logic.model_dump()),
                currency=settings.CurrencySettings(**current.currency.model_dump()),
                gui=settings.GuiSettings(**current.gui.model_dump()),
            )
            new_leagues = set(leagues or [])
            try:
                with new_settings.currency.delay_validation():
                    setattr(new_settings.currency, setting_attr, new_leagues)
                    if new_settings.currency.active_game == game and (
                        new_settings.currency.active_league not in new_leagues and new_leagues
                    ):
                        new_settings.currency.active_league = sorted(new_leagues)[0]
                self.settings_manager.set_settings(new_settings)
            except (AttributeError, TypeError, ValueError):
                setattr(new_settings.currency, setting_attr, new_leagues)
                self.settings_manager.set_settings(new_settings)
        except (AttributeError, TypeError, ValueError, settings.ValidationError, RuntimeError, OSError):
            logger.exception("Failed to persist %s from background league fetch", setting_attr)

        # Refresh UI regardless of persistence result
        try:
            self.populate_league_combo()
            self.populate_league_settings()
        except (AttributeError, TypeError, ValueError, settings.ValidationError, RuntimeError, OSError):
            logger.exception("Failed to refresh UI after league fetch")

        # Re-enable the appropriate button
        try:
            if game == 1:
                with contextlib.suppress(Exception):
                    self.get_poe1_leagues_button.setEnabled(True)
            else:
                with contextlib.suppress(Exception):
                    self.get_poe2_leagues_button.setEnabled(True)
        except (RuntimeError, TypeError, ValueError, settings.ValidationError, OSError):
            logger.exception("Failed to re-enable league fetch button")


class KeyOrKeyCodeValidator(QValidator):
    """Validate whether a string can be converted to a Key or KeyCode.

    Uses `poemarcut.keyboard.keyorkeycode_from_str` which raises on invalid
    values; this validator maps that to QValidator states.
    """

    def validate(self, a0: str | None, a1: int) -> tuple[QValidator.State, str, int]:
        """Validate a string as a valid Key or KeyCode.

        Args:
            a0 (str | None):  The string to validate.
            a1 (int):  The cursor position.

        Returns:
            tuple[QValidator.State, str, int]
            A tuple containing the validation state, the string, and cursor position.

        """
        if not a0:
            return (QValidator.State.Intermediate, "", a1)
        try:
            keyboard.keyorkeycode_from_str(key_str=a0)
        except ValueError:
            return (QValidator.State.Invalid, a0, a1)
        return (QValidator.State.Acceptable, a0, a1)


if __name__ == "__main__":
    stream_handler = logging.StreamHandler()  # log to console
    stream_handler.setLevel(logging.WARNING)
    file_handler = RotatingFileHandler(
        "poemarcut_gui.log", mode="a", maxBytes=5 * 1024 * 1024, backupCount=1, encoding="utf-8"
    )  # log to file with rotation, max size 5MB and 1 backup
    file_handler.setLevel(logging.WARNING)
    gui_handler = _LastLogHandler()  # log to the GUI's latest message label
    gui_handler.setLevel(logging.INFO)
    gui_handler.setFormatter(_EmojiFormatter("%(levelname)s%(message)s"))

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[stream_handler, file_handler, gui_handler],
    )

    logger.info("Starting PoEMarcut")
    app = QApplication(sys.argv)
    window = PoEMarcutGUI()
    window.show()
    sys.exit(app.exec())
