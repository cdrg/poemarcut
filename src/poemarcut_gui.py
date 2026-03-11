"""PoEMarcut GUI."""

import logging
import sys
from collections.abc import Iterable
from functools import partial
from logging.handlers import RotatingFileHandler
from pathlib import Path

from annotated_types import Gt, Lt
from PyQt6.QtCore import QSignalBlocker, Qt, pyqtSignal
from PyQt6.QtGui import QDoubleValidator, QFontDatabase, QIcon, QValidator
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from poemarcut import currency, keyboard, settings

logger = logging.getLogger(__name__)

# PoE-like color scheme
poe_header_text = "rgb(163, 139, 99)"
poe_header_style = f"color: {poe_header_text}; font-weight: bold; text-decoration: underline;"
poe_text = "rgb(170, 170, 170)"
poe_dark_bg = "rgb(34, 16, 4)"
poe_light_bg = "rgb(50, 30, 10)"
poe_edit_bg = "rgb(58, 51, 46)"

# width/height 2x border-radius = a circle
qradiobutton_light = (
    "QRadioButton::indicator { width: 24px; height: 24px; border-radius: 12px; background-color: black; }"
)
greenlight = "limegreen"
redlight = "salmon"
qradiobutton_greenlight = qradiobutton_light.replace("background-color: black", f"background-color: {greenlight}")
qradiobutton_redlight = qradiobutton_light.replace("background-color: black", f"background-color: {redlight}")

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


class PoEMarcutGUI(QMainWindow):
    """GUI for PoE Marcut.

    Displays price suggestions and access to settings.
    """

    # Emitted when background currency fetch completes (dict with 'success' and 'lines' or 'error' keys)
    currency_data_ready = pyqtSignal(object)
    # Emitted when keyboard listener stops itself (e.g. stop_key pressed)
    hotkeys_listener_stopped = pyqtSignal()

    def __init__(self) -> None:
        """Initialize the PoEMarcut GUI window and set up the user interface."""
        super().__init__()
        # Use the shared SettingsManager singleton
        self.settings_man: settings.SettingsManager = settings.settings_manager
        self.setWindowTitle("PoE Marcut")
        self.setGeometry(400, 100, 450, 600)

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
            f"QMainWindow {{ color: {poe_header_text}; background-color: {poe_dark_bg}; }} "
            f"QLabel {{ color: {poe_text}; }} "
            f"QLineEdit {{ color: {poe_text}; background-color: {poe_edit_bg}; }} "
            f"QTextEdit {{ color: {poe_header_text}; background-color: {poe_light_bg}; }} "
            f"QCheckBox {{ color: {poe_header_text}; }} "
            f"QCheckBox::indicator {{ border: 1px solid; border-color: {poe_text}; }} "
            f"QCheckBox::indicator:checked {{ background-color: {poe_header_text}; }} "
            f"QComboBox {{ }} "
            f"QListWidget {{ color: {poe_header_text}; background-color: {poe_light_bg}; border: 1px solid {poe_header_text}; }} "
            f"QToolTip {{ color: {poe_text}; background-color: {poe_light_bg}; border: 1px solid {poe_header_text}; }}"
        )

        self.init_ui()

        # Signal used to update the UI from a background thread
        self.hotkeys_listener_stopped.connect(self._on_hotkeys_listener_stopped)

    def init_ui(self) -> None:
        """Set up the user interface components."""
        central: QWidget = QWidget()
        main_layout: QGridLayout = QGridLayout()

        self.currency_header: QLabel = QLabel("Currency Information")
        self.currency_header.setStyleSheet(poe_header_style)
        main_layout.addWidget(self.currency_header, 0, 0, 1, 1)
        self.pin_checkbox: QCheckBox = QCheckBox("Always on top")
        self.pin_checkbox.setToolTip("Always stay on top of other windows")
        self.pin_checkbox.stateChanged.connect(self.toggle_always_on_top)
        main_layout.addWidget(self.pin_checkbox, 0, 2, 1, 1)

        main_layout.addWidget(QLabel("Choose league:"), 1, 0, 1, 1)
        self.league_combo: QComboBox = QComboBox()
        self.populate_league_combo()
        # Update active game/league when the user selects a league
        self.league_combo.currentIndexChanged.connect(self._on_league_combo_changed)
        main_layout.addWidget(self.league_combo, 2, 0, 1, 1)

        self.currency_list: QListWidget = QListWidget()
        main_layout.addWidget(self.currency_list, 3, 0, 1, 3)
        self.populate_currency_list()

        self.settings_button: QPushButton = QPushButton("Settings...")
        self.settings_button.clicked.connect(self.toggle_settings_panel)
        main_layout.addWidget(self.settings_button, 4, 0, 1, 1)

        self.hotkeys_enabled: bool = False  # State for hotkeys button

        self.hotkeys_button: QPushButton = QPushButton("Enable hotkeys")
        self.hotkeys_button.clicked.connect(self.toggle_hotkeys)
        main_layout.addWidget(self.hotkeys_button, 4, 1, 1, 1)

        self.indicator = QRadioButton()
        self.indicator.setEnabled(False)  # Disable user interaction
        main_layout.addWidget(self.indicator, 4, 2, 1, 1)

        self.toggle_hotkeys()  # Enable hotkeys on start

        central.setLayout(main_layout)
        self.setCentralWidget(central)

        self.settings_panel: QFrame = QFrame()
        self.settings_panel.setStyleSheet(
            f".QFrame {{ background-color: {poe_light_bg}; border: 1px solid {poe_header_text}; }}"
        )
        self.settings_panel.setFrameShape(QFrame.Shape.StyledPanel)

        self.setup_settings_sidebar()

        self.settings_panel.setLayout(self.side_settings_layout)
        self.settings_panel.hide()  # Start hidden

        main_layout.addWidget(self.settings_panel, 1, 2, 4, 1)

    def setup_settings_sidebar(self) -> None:  # noqa: PLR0915
        """Set up the settings sidebar."""
        settings_man: settings.SettingsManager = self.settings_man

        self.side_settings_layout: QHBoxLayout = QHBoxLayout()

        ### left panel of settings
        lefthalf_layout: QVBoxLayout = QVBoxLayout()
        ## set up components for Keys settings fields
        keys_settings: settings.KeySettings = settings_man.settings.keys
        keys_settings_header: QLabel = QLabel("Keys settings")
        keys_settings_header.setStyleSheet(poe_header_style)
        lefthalf_layout.addWidget(keys_settings_header)
        # loop through all key fields
        # store line edits so we can update them when settings change
        self.key_lineedits: dict[str, QLineEdit] = {}
        for field_name, field_value in keys_settings:
            row_layout: QHBoxLayout = QHBoxLayout()
            field_info = keys_settings.__class__.model_fields[field_name]
            setting_label: QLabel = QLabel(f"{field_name}:".replace("_", " "))
            setting_label.setToolTip(field_info.description or "")
            row_layout.addWidget(setting_label, stretch=1)

            lineedit: QLineEdit = QLineEdit(str(field_value))
            self.key_validator = KeyOrKeyCodeValidator()
            lineedit.setValidator(self.key_validator)
            # update settings when the user finishes editing
            lineedit.editingFinished.connect(partial(self.process_qle_text, "Keys", field_name, lineedit))
            self.key_lineedits[field_name] = lineedit
            row_layout.addWidget(lineedit, stretch=1)
            lefthalf_layout.addLayout(row_layout)

        ## set up components for Logic settings fields
        logic_settings: settings.LogicSettings = settings_man.settings.logic
        logic_settings_header: QLabel = QLabel("Logic settings")
        logic_settings_header.setStyleSheet(poe_header_style)
        lefthalf_layout.addWidget(logic_settings_header)

        # adjustment factor field
        af_row_layout: QHBoxLayout = QHBoxLayout()
        af_setting_label: QLabel = QLabel("Adjustment factor")
        af_field_info = logic_settings.__class__.model_fields["adjustment_factor"]
        af_setting_label.setToolTip(af_field_info.description or "")
        af_row_layout.addWidget(af_setting_label, stretch=1)
        self.adj_factor_le: QLineEdit = QLineEdit(str(logic_settings.adjustment_factor))
        gt_val: float = float("-inf")
        lt_val: float = float("inf")
        for metadata in af_field_info.metadata:
            if isinstance(metadata, Gt):
                gt_val = float(str(metadata.gt))
            elif isinstance(metadata, Lt):
                lt_val = float(str(metadata.lt))
        self.adj_factor_le.setValidator(
            QDoubleValidator(bottom=gt_val, top=lt_val, decimals=2, parent=self.adj_factor_le)
        )
        self.adj_factor_le.returnPressed.connect(
            partial(self.process_qle_float, "Logic", "adjustment_factor", self.adj_factor_le)
        )
        self.adj_factor_le.editingFinished.connect(
            partial(self.process_qle_float, "Logic", "adjustment_factor", self.adj_factor_le)
        )
        af_row_layout.addWidget(self.adj_factor_le, stretch=1)
        lefthalf_layout.addLayout(af_row_layout)

        # min actual factor field
        maf_row_layout: QHBoxLayout = QHBoxLayout()
        maf_setting_label: QLabel = QLabel("Min actual factor")
        maf_field_info = logic_settings.__class__.model_fields["min_actual_factor"]
        maf_setting_label.setToolTip(maf_field_info.description or "")
        maf_row_layout.addWidget(maf_setting_label, stretch=1)
        self.min_actual_factor_le: QLineEdit = QLineEdit(str(logic_settings.min_actual_factor))
        gt_val: float = float("-inf")
        lt_val: float = float("inf")
        for metadata in maf_field_info.metadata:
            if isinstance(metadata, Gt):
                gt_val = float(str(metadata.gt))
            elif isinstance(metadata, Lt):
                lt_val = float(str(metadata.lt))
        self.min_actual_factor_le.setValidator(
            QDoubleValidator(bottom=gt_val, top=lt_val, decimals=2, parent=self.min_actual_factor_le)
        )
        self.min_actual_factor_le.returnPressed.connect(
            partial(self.process_qle_float, "Logic", "min_actual_factor", self.min_actual_factor_le)
        )
        self.min_actual_factor_le.editingFinished.connect(
            partial(self.process_qle_float, "Logic", "min_actual_factor", self.min_actual_factor_le)
        )
        maf_row_layout.addWidget(self.min_actual_factor_le, stretch=1)
        lefthalf_layout.addLayout(maf_row_layout)

        # enter after calcprice field
        eac_row_layout: QHBoxLayout = QHBoxLayout()
        eac_setting_label: QLabel = QLabel("Enter after calcprice")
        eac_field_info = logic_settings.__class__.model_fields["enter_after_calcprice"]
        eac_setting_label.setToolTip(eac_field_info.description or "")
        eac_row_layout.addWidget(eac_setting_label, stretch=1)
        self.enter_after_cb: QCheckBox = QCheckBox("")
        self.enter_after_cb.setChecked(logic_settings.enter_after_calcprice)
        self.enter_after_cb.stateChanged.connect(
            partial(self.process_qcb, "Logic", "enter_after_calcprice", self.enter_after_cb)
        )
        eac_row_layout.addWidget(self.enter_after_cb, stretch=1)
        lefthalf_layout.addLayout(eac_row_layout)

        lefthalf_layout.addStretch()
        self.side_settings_layout.addLayout(lefthalf_layout)

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

        # active game field
        ag_row_layout: QHBoxLayout = QHBoxLayout()
        ag_setting_label: QLabel = QLabel("Active game")
        ag_field_info = currency_settings.__class__.model_fields["active_game"]
        ag_setting_label.setToolTip(ag_field_info.description or "")
        ag_row_layout.addWidget(ag_setting_label, stretch=1)
        self.active_game_le: QLineEdit = QLineEdit(str(currency_settings.active_game))
        self.active_game_le.setReadOnly(True)
        ag_row_layout.addWidget(self.active_game_le, stretch=1)
        middle_layout.addLayout(ag_row_layout)

        # active league field
        al_row_layout: QHBoxLayout = QHBoxLayout()
        al_setting_label: QLabel = QLabel("Active league")
        al_field_info = currency_settings.__class__.model_fields["active_league"]
        al_setting_label.setToolTip(al_field_info.description or "")
        al_row_layout.addWidget(al_setting_label, stretch=1)
        self.active_league_le: QLineEdit = QLineEdit(str(currency_settings.active_league))
        self.active_league_le.setReadOnly(True)
        al_row_layout.addWidget(self.active_league_le, stretch=1)
        middle_layout.addLayout(al_row_layout)

        middle_layout.addStretch()
        self.side_settings_layout.addLayout(middle_layout)

        ### right panel of settings
        righthalf_layout: QVBoxLayout = QVBoxLayout()

        blank_header: QLabel = QLabel("Currency settings")
        blank_header.setStyleSheet("color: transparent;")
        righthalf_layout.addWidget(blank_header)

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
        righthalf_layout.addLayout(au_row_layout)

        # poe1leagues field
        p1l_list_layout: QVBoxLayout = QVBoxLayout()
        p1l_setting_label: QLabel = QLabel("PoE1 leagues")
        p1l_field_info = currency_settings.__class__.model_fields["poe1leagues"]
        p1l_setting_label.setToolTip(p1l_field_info.description or "")
        p1l_list_layout.addWidget(p1l_setting_label)

        self.p1l_list_widget = QListWidget()
        self._populate_list_widget(self.p1l_list_widget, currency_settings.poe1leagues, "Currency", "poe1leagues")
        self.p1l_list_widget.currentItemChanged.connect(
            partial(self.process_qlw, "Currency", "poe1leagues", self.p1l_list_widget)
        )
        p1l_list_layout.addWidget(self.p1l_list_widget)
        righthalf_layout.addLayout(p1l_list_layout)

        # poe2leagues field
        p2l_list_layout: QVBoxLayout = QVBoxLayout()
        p2l_setting_label: QLabel = QLabel("PoE2 leagues")
        p2l_field_info = currency_settings.__class__.model_fields["poe2leagues"]
        p2l_setting_label.setToolTip(p2l_field_info.description or "")
        p2l_list_layout.addWidget(p2l_setting_label)

        self.p2l_list_widget = QListWidget()
        self._populate_list_widget(self.p2l_list_widget, currency_settings.poe2leagues, "Currency", "poe2leagues")
        self.p2l_list_widget.currentItemChanged.connect(
            partial(self.process_qlw, "Currency", "poe2leagues", self.p2l_list_widget)
        )
        p2l_list_layout.addWidget(self.p2l_list_widget)
        righthalf_layout.addLayout(p2l_list_layout)

        # poe1 leagues button
        self.get_poe1_leagues_button: QPushButton = QPushButton("Get PoE1 leagues...")
        self.get_poe1_leagues_button.setToolTip("Replace the PoE1 leagues with the list from GGG")
        self.get_poe1_leagues_button.clicked.connect(self.get_poe1_leagues)
        righthalf_layout.addWidget(self.get_poe1_leagues_button)
        # poe2 leagues button
        self.get_poe2_leagues_button: QPushButton = QPushButton("Get PoE2 leagues...")
        self.get_poe2_leagues_button.setToolTip("Replace the PoE2 leagues with the list from GGG")
        self.get_poe2_leagues_button.clicked.connect(self.get_poe2_leagues)
        righthalf_layout.addWidget(self.get_poe2_leagues_button)

        self.side_settings_layout.addLayout(righthalf_layout)

        # React to external setting changes and update widgets
        try:
            self.settings_man.settings_changed.connect(self._on_setting_changed)
        except Exception:
            logger.exception("Failed to connect settings_changed signal")

    def _make_list_item_widget(self, text: str, list_widget: QListWidget, category: str, setting: str) -> QWidget:
        """Create a QWidget containing a label and an 'X' remove button for a list item.

        The remove button will delete the item from the QListWidget and update settings.
        """
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        label = QLabel(text)
        layout.addWidget(label, stretch=1)
        remove_btn = QPushButton("X")
        remove_btn.setFixedWidth(28)
        remove_btn.clicked.connect(partial(self._remove_list_item, list_widget, text, category, setting))
        layout.addWidget(remove_btn)
        return container

    def _make_currency_display_widget(self, currency_name: str, value_text: str | None) -> QWidget:
        """Create a compact QWidget showing a currency name and a value label beside it.

        `value_text` is expected to already be formatted (e.g. "100.00 chaos").
        """
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(4, 2, 4, 2)
        name_lbl = QLabel(currency_name)
        val_lbl = QLabel(value_text or "")
        val_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        layout.addWidget(name_lbl)
        layout.addSpacing(8)
        layout.addWidget(val_lbl)
        layout.addStretch()
        return container

    def _remove_list_item(self, list_widget: QListWidget, text: str, category: str, setting: str) -> None:
        """Remove the first matching item with `text` from `list_widget` and save settings."""
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            if item is None:
                continue
            w = list_widget.itemWidget(item)
            item_text = None
            if w is not None:
                lbl = w.findChild(QLabel)
                if lbl is not None:
                    item_text = lbl.text()
            else:
                item_text = item.text()
            if item_text == text:
                list_widget.takeItem(i)
                break
        # Persist the new list to settings
        try:
            self.process_qlw(category, setting, list_widget)
        except Exception:
            logger.exception("Failed to persist list after removal %s.%s", category, setting)

    def _populate_list_widget(
        self, list_widget: QListWidget, items: Iterable[str] | None, category: str, setting: str
    ) -> None:
        """Clear and populate `list_widget` with `items`, using item widgets with remove buttons."""
        list_widget.clear()
        if not items:
            return
        # Ensure deterministic order for sets
        if isinstance(items, set):
            items = sorted(items)
        for it in items:
            lw_item = QListWidgetItem()
            widget = self._make_list_item_widget(str(it), list_widget, category, setting)
            lw_item.setSizeHint(widget.sizeHint())
            list_widget.addItem(lw_item)
            list_widget.setItemWidget(lw_item, widget)

    def process_qle_text(self, category: str, setting: str, qle: QLineEdit) -> None:
        """Process input for a specific text setting."""
        try:
            self.settings_man.set_setting(category, setting, qle.text())
        except Exception:
            logger.exception("Failed to set text setting %s.%s", category, setting)

    def process_qle_float(self, category: str, setting: str, qle: QLineEdit) -> None:
        """Process input for a specific float setting."""
        try:
            value = float(qle.text())
            self.settings_man.set_setting(category, setting, value)
        except ValueError:
            pass  # Invalid float input; ignore
        except Exception:
            logger.exception("Failed to set float setting %s.%s", category, setting)

    def process_qcb(self, category: str, setting: str, checkbox: QCheckBox) -> None:
        """Process input for a specific boolean setting."""
        try:
            self.settings_man.set_setting(category, setting, checkbox.isChecked())
        except Exception:
            logger.exception("Failed to set checkbox setting %s.%s", category, setting)

    def process_qlw(self, category: str, setting: str, list_widget: QListWidget, *_: object) -> None:
        """Process input for a specific list setting.

        Accepts extra positional args from Qt signals and ignores them.
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
            self.settings_man.set_setting(category, setting, items)
        except Exception:
            logger.exception("Failed to update list setting %s.%s", category, setting)

    def _on_setting_changed(self, full_field: str, value: object) -> None:
        """Slot called when a setting is changed; updates the corresponding widget.

        The `full_field` is in the form "category.field".
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

    def _handle_key_setting(self, setting: str, value: object) -> None:
        """Update key-related widgets when settings change."""
        if setting in getattr(self, "key_lineedits", {}):
            le = self.key_lineedits[setting]
            with QSignalBlocker(le):
                le.setText(str(value))

    def _handle_logic_setting(self, setting: str, value: object) -> None:
        """Update logic-related widgets when settings change."""
        if setting == "adjustment_factor":
            with QSignalBlocker(self.adj_factor_le):
                self.adj_factor_le.setText(str(value))
        elif setting == "min_actual_factor":
            with QSignalBlocker(self.min_actual_factor_le):
                self.min_actual_factor_le.setText(str(value))
        elif setting == "enter_after_calcprice":
            with QSignalBlocker(self.enter_after_cb):
                self.enter_after_cb.setChecked(bool(value))

    def _handle_currency_setting(self, setting: str, value: object) -> None:
        """Handle updates for currency-related settings."""
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

    def toggle_always_on_top(self) -> None:
        """Toggle the always-stays-on-top window flag."""
        self.hide()
        if self.pin_checkbox.isChecked():
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, on=True)
        else:
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, on=False)
        self.show()

    def toggle_settings_panel(self) -> None:
        """Toggle visibility of the settings panel."""
        if self.settings_panel.isVisible():
            self.settings_panel.hide()
        else:
            self.settings_panel.show()

    def toggle_hotkeys(self) -> None:
        """Enable or disable the keyboard hotkeys listener."""
        if not self.hotkeys_enabled:
            try:
                listener = keyboard.start_listener(blocking=False, on_stop=self._notify_hotkeys_listener_stopped)
            except Exception:
                logger.exception("Failed to start hotkeys listener.")
                return

            if listener is None:
                logger.warning("Hotkeys listener did not start (blocking returned None).")
                return

            self._set_hotkeys_ui_state(enabled=True)
        else:
            try:
                keyboard.stop_listener()
            except Exception:
                logger.exception("Failed to stop hotkeys listener.")
            self._set_hotkeys_ui_state(enabled=False)

    def _notify_hotkeys_listener_stopped(self) -> None:
        """Notify the GUI thread that the listener has stopped itself."""
        self.hotkeys_listener_stopped.emit()

    def _on_hotkeys_listener_stopped(self) -> None:
        """Update button and indicator when listener exits from stop_key."""
        self._set_hotkeys_ui_state(enabled=False)

    def _set_hotkeys_ui_state(self, *, enabled: bool) -> None:
        """Set hotkeys button text and indicator to match listener state."""
        self.hotkeys_enabled = enabled
        if enabled:
            self.hotkeys_button.setText("Disable hotkeys")
            self.indicator.setStyleSheet(qradiobutton_greenlight)
            self.indicator.setToolTip("Hotkeys enabled")
            return
        self.hotkeys_button.setText("Enable hotkeys")
        self.indicator.setStyleSheet(qradiobutton_redlight)
        self.indicator.setToolTip("Hotkeys disabled")

    def populate_league_combo(self) -> None:
        """Populate the league combo box."""
        settings_man: settings.SettingsManager = self.settings_man
        self.league_combo.clear()
        for poe1league in settings_man.settings.currency.poe1leagues:
            self.league_combo.addItem(f"{poe1league} [PoE1]")
        for poe2league in settings_man.settings.currency.poe2leagues:
            self.league_combo.addItem(f"{poe2league} [PoE2]")
        # Select the currently active game/league from settings, if present
        try:
            active_game = settings_man.settings.currency.active_game
            active_league = settings_man.settings.currency.active_league
            desired = f"{active_league} [PoE1]" if active_game == 1 else f"{active_league} [PoE2]"
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

    def populate_currency_list(self) -> None:
        """Populate the main currency list for the currently active game."""
        currency_settings = self.settings_man.settings.currency
        currencies = (
            currency_settings.poe1currencies if currency_settings.active_game == 1 else currency_settings.poe2currencies
        )
        self.currency_list.clear()
        if not currencies:
            return
        game = currency_settings.active_game
        league = currency_settings.active_league
        for idx, c in enumerate(currencies):
            # Compute rate of this currency in terms of the next currency (if any)
            rate_text = ""
            if idx != len(currencies) - 1:
                try:
                    rate = currency.get_exchange_rate(game, league, c, currencies[idx + 1])
                    rate_text = f"({rate:.2f} {currencies[idx + 1]})"
                except (LookupError, ValueError, TypeError):
                    rate_text = ""

            widget = self._make_currency_display_widget(str(c), rate_text)
            lw_item = QListWidgetItem()
            lw_item.setSizeHint(widget.sizeHint())
            self.currency_list.addItem(lw_item)
            self.currency_list.setItemWidget(lw_item, widget)

            # Insert a centered, non-interactive downward arrow between currencies
            if idx != len(currencies) - 1:
                arrow = QListWidgetItem("↓")
                arrow.setFlags(Qt.ItemFlag.NoItemFlags)
                arrow.setTextAlignment(Qt.AlignmentFlag.AlignLeft)
                self.currency_list.addItem(arrow)

    def populate_league_settings(self) -> None:
        """Populate the league settings."""

    def _on_league_combo_changed(self, index: int) -> None:
        """Handle user selection in `league_combo` and persist active game/league.

        Items in the combo are formatted as "<league> [PoE1]" or "<league> [PoE2]".
        """
        try:
            text = self.league_combo.currentText() if index is None or index < 0 else self.league_combo.itemText(index)
            if not text:
                return
            if text.endswith(" [PoE1]"):
                game = 1
                league = text[: -len(" [PoE1]")]
            elif text.endswith(" [PoE2]"):
                game = 2
                league = text[: -len(" [PoE2]")]
            else:
                return

            # Persist the selection
            self.settings_man.set_setting("currency", "active_game", game)
            self.settings_man.set_setting("currency", "active_league", league)
        except (AttributeError, TypeError, ValueError, settings.ValidationError):
            logger.exception("Failed to persist active game/league from league_combo selection")

    def get_poe1_leagues(self) -> None:
        """Get PoE1 leagues, update settings and UI."""
        leagues: list[str] | None = currency.get_leagues(game=1)
        try:
            self.settings_man.set_setting("currency", "poe1leagues", leagues)
        except Exception:
            logger.exception("Failed to update poe1leagues from get_poe1_leagues")
        self.populate_league_combo()
        self.populate_league_settings()

    def get_poe2_leagues(self) -> None:
        """Get PoE2 leagues, update settings and UI."""
        leagues: list[str] | None = currency.get_leagues(game=2)
        try:
            self.settings_man.set_setting("currency", "poe2leagues", leagues)
        except Exception:
            logger.exception("Failed to update poe2leagues from get_poe2_leagues")
        self.populate_league_combo()
        self.populate_league_settings()


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
            keyboard.keyorkeycode_from_str(a0)
        except ValueError:
            return (QValidator.State.Invalid, a0, a1)
        return (QValidator.State.Acceptable, a0, a1)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),  # Output to console
            RotatingFileHandler(
                "poemarcut_gui.log", mode="a", maxBytes=5 * 1024 * 1024, backupCount=1, encoding="utf-8"
            ),  # Output to file, max 5 MB
        ],
    )

    app = QApplication(sys.argv)
    window = PoEMarcutGUI()
    window.show()
    sys.exit(app.exec())
