"""PoEMarcut GUI."""

import logging
import sys
import threading
import time
from functools import partial
from logging.handlers import RotatingFileHandler
from pathlib import Path

from annotated_types import Gt, Lt
from PyQt6.QtCore import Qt, pyqtSignal
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
    QMainWindow,
    QPushButton,
    QRadioButton,
    QTextEdit,
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


class PoEMarcutGUI(QMainWindow):
    """GUI for PoE Marcut.

    Displays price suggestions and access to settings.
    """

    # Emitted when background currency fetch completes (dict with 'success' and 'lines' or 'error' keys)
    currency_data_ready = pyqtSignal(object)

    def __init__(self) -> None:
        """Initialize the PoEMarcut GUI window and set up the user interface."""
        super().__init__()
        self.setWindowTitle("PoE Marcut")
        self.setGeometry(400, 100, 650, 600)

        self.custom_font_family: str = "default"
        font_path: Path = Path(__file__).parent.parent / "assets" / "Fontin-Regular.otf"
        font_id: int = QFontDatabase.addApplicationFont(str(font_path))
        if font_id == -1:
            logger.warning("Failed to load custom font, using default.")
        else:
            families = QFontDatabase.applicationFontFamilies(font_id)
            self.custom_font_family = families[0] if families else "default"

        icon_path: Path = Path(__file__).parent.parent / "assets" / "icon.ico"
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
        self.currency_data_ready.connect(self._display_currency_suggestions)

        self.show_currency_suggestions()

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
        self.league_combo.currentIndexChanged.connect(self.show_currency_suggestions)
        main_layout.addWidget(self.league_combo, 2, 0, 1, 1)

        self.currency_text: QTextEdit = QTextEdit("")
        self.currency_text.setReadOnly(True)
        main_layout.addWidget(self.currency_text, 3, 0, 1, 3)

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
        settings_man: settings.SettingsManager = settings.SettingsManager()

        self.side_settings_layout: QHBoxLayout = QHBoxLayout()

        ### left panel of settings
        lefthalf_layout: QVBoxLayout = QVBoxLayout()
        ## set up components for Keys settings fields
        keys_settings: settings.KeySettings = settings_man.settings.keys
        keys_settings_header: QLabel = QLabel("Keys settings")
        keys_settings_header.setStyleSheet(poe_header_style)
        lefthalf_layout.addWidget(keys_settings_header)
        # loop through all key fields
        for field_name, field_value in keys_settings:
            row_layout: QHBoxLayout = QHBoxLayout()
            field_info = keys_settings.__class__.model_fields[field_name]
            setting_label: QLabel = QLabel(f"{field_name}:".replace("_", " "))
            setting_label.setToolTip(field_info.description or "")
            row_layout.addWidget(setting_label, stretch=1)

            lineedit: QLineEdit = QLineEdit(str(field_value))
            self.key_validator = KeyOrKeyCodeValidator()
            lineedit.setValidator(self.key_validator)
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
        self.p1c_list_widget.addItems(currency_settings.poe1currencies)
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
        self.p2c_list_widget.addItems(currency_settings.poe2currencies)
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
        self.p1l_list_widget.addItems(currency_settings.poe1leagues)
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
        self.p2l_list_widget.addItems(currency_settings.poe2leagues)
        self.p2l_list_widget.currentItemChanged.connect(
            partial(self.process_qlw, "Currency", "poe2leagues", self.p2l_list_widget)
        )
        p2l_list_layout.addWidget(self.p2l_list_widget)
        righthalf_layout.addLayout(p2l_list_layout)

        # poe1 leagues button
        self.get_poe1_leagues_button: QPushButton = QPushButton("Get PoE1 leagues...")
        self.get_poe1_leagues_button.clicked.connect(self.get_poe1_leagues)
        righthalf_layout.addWidget(self.get_poe1_leagues_button)
        # poe2 leagues button
        self.get_poe2_leagues_button: QPushButton = QPushButton("Get PoE2 leagues...")
        self.get_poe2_leagues_button.clicked.connect(self.get_poe2_leagues)
        righthalf_layout.addWidget(self.get_poe2_leagues_button)

        self.side_settings_layout.addLayout(righthalf_layout)

    def process_qle_text(self, category: str, setting: str, qle: QLineEdit) -> None:
        """Process input for a specific text setting."""
        settings.SettingsManager().set_setting(category, setting, qle.text())

    def process_qle_float(self, category: str, setting: str, qle: QLineEdit) -> None:
        """Process input for a specific float setting."""
        try:
            value = float(qle.text())
            settings.SettingsManager().set_setting(category, setting, value)
        except ValueError:
            pass  # Invalid float input; ignore

    def process_qcb(self, category: str, setting: str, checkbox: QCheckBox) -> None:
        """Process input for a specific boolean setting."""
        settings.SettingsManager().set_setting(category, setting, checkbox.isChecked())

    def process_qlw(self, category: str, setting: str, list_widget: QListWidget) -> None:
        """Process input for a specific list setting."""

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
                listener = keyboard.start_listener(blocking=False)
            except Exception:
                logger.exception("Failed to start hotkeys listener.")
                return

            if listener is None:
                logger.warning("Hotkeys listener did not start (blocking returned None).")
                return

            self.hotkeys_enabled = True
            self.hotkeys_button.setText("Disable hotkeys")
            self.indicator.setStyleSheet(qradiobutton_greenlight)
            self.indicator.setToolTip("Hotkeys enabled.")
        else:
            try:
                keyboard.stop_listener()
            except Exception:
                logger.exception("Failed to stop hotkeys listener.")
            self.hotkeys_enabled = False
            self.hotkeys_button.setText("Enable hotkeys")
            self.indicator.setStyleSheet(qradiobutton_redlight)
            self.indicator.setToolTip("Hotkeys disabled.")

    def populate_league_combo(self) -> None:
        """Populate the league combo box."""
        settings_man: settings.SettingsManager = settings.SettingsManager()
        self.league_combo.clear()
        for poe1league in settings_man.settings.currency.poe1leagues:
            self.league_combo.addItem(f"{poe1league} [PoE1]")
        for poe2league in settings_man.settings.currency.poe2leagues:
            self.league_combo.addItem(f"{poe2league} [PoE2]")

    def populate_league_settings(self) -> None:
        """Populate the league settings."""

    def get_poe1_leagues(self) -> None:
        """Get PoE1 leagues, update settings and UI."""
        leagues: list[str] | None = currency.get_leagues(game=1)
        settings.SettingsManager().set_setting("currency", "poe1leagues", leagues)
        self.populate_league_combo()
        self.populate_league_settings()

    def get_poe2_leagues(self) -> None:
        """Get PoE2 leagues, update settings and UI."""
        leagues: list[str] | None = currency.get_leagues(game=2)
        settings.SettingsManager().set_setting("currency", "poe2leagues", leagues)
        self.populate_league_combo()
        self.populate_league_settings()

    def show_currency_suggestions(self) -> None:
        """Fetch and display currency suggestions for the selected league + game."""
        if self.league_combo.currentText() == "" or "[" not in self.league_combo.currentText():
            return
        # Parse selection and show a quick loading message
        league, game_str = self.league_combo.currentText().replace("]", "").split(" [")
        if game_str == "PoE1":
            settings.SettingsManager().set_setting("currency", "active_game", 1)
        else:
            settings.SettingsManager().set_setting("currency", "active_game", 2)
        settings.SettingsManager().set_setting("currency", "active_league", league)
        self.currency_text.setText(f"Loading currency data for {self.league_combo.currentText()}...")

        # Run in background thread so UI stays responsive
        game = 1 if game_str == "PoE1" else 2
        thread = threading.Thread(target=self._show_currency_worker, args=(league, game), daemon=True)
        thread.start()

    def _show_currency_worker(self, league: str, game: int) -> None:
        """Background worker that fetches currency data and emits signal with formatted lines."""
        lines: list[str] = []
        try:
            chaos_val, primary_currency = currency.get_currency_value(game=game, league=league, currency_name="chaos")
        except (LookupError, ValueError) as e:
            logger.warning("Could not fetch chaos value for %s: %s", league, e)
            self.currency_data_ready.emit(
                {
                    "success": False,
                    "error": f"Could not retrieve currency data for {league}. This is expected if the league is not active.",
                }
            )
            return

        settings_man: settings.SettingsManager = settings.SettingsManager()

        if primary_currency == "chaos":
            try:
                divine_val = currency.get_currency_value(game=game, league=league, currency_name="divine")[0]
                chaos_val = 1 / divine_val
            except (LookupError, ValueError) as e:
                # Fallback if divine fetch fails
                logger.warning("Could not fetch divine value for %s: %s", league, e)
            primary_currency = "divine"

        primary_chaos_adj: float = 1 / chaos_val * settings_man.settings.logic.adjustment_factor
        last_updated = currency.get_update_time(game, league)

        time_diff = time.time() - last_updated
        diff_hours = int(time_diff // 3600)
        diff_mins = int((time_diff % 3600) // 60)
        lines.append(
            f"PoE{game} currency data for {league} last updated: {diff_hours}h:{diff_mins:02d}m ago ({time.ctime(last_updated)})"
        )
        lines.append("Suggested new currency if current price is 1, based on economy data:")
        lines.append(
            f"{settings_man.settings.logic.adjustment_factor}x 1 {primary_currency.capitalize()} ({1 / chaos_val:.2f} Chaos)"
        )
        lines.append(f" = {int(primary_chaos_adj)} Chaos ({primary_chaos_adj:.2f})")
        if game == 1:
            lines.append(f"{settings_man.settings.logic.adjustment_factor}x 1 Chaos")
            lines.append(" = Just vendor it already!")
        else:
            try:
                chaos_exalt_val: float = currency.get_exchange_rate(
                    game=game, league=league, from_currency="chaos", to_currency="exalted"
                )
            except (LookupError, ValueError) as e:
                logger.warning("Could not fetch exalted value for %s: %s", league, e)
                self.currency_data_ready.emit(
                    {
                        "success": False,
                        "error": f"Could not retrieve currency data for {league}. This is expected if the league is not active.",
                    }
                )
                return

            lines.append(f"{settings_man.settings.logic.adjustment_factor}x 1 Chaos ({chaos_exalt_val:.2f} Exalted)")
            lines.append(
                f" = {int(chaos_exalt_val * settings_man.settings.logic.adjustment_factor)} Exalted ({(chaos_exalt_val * settings_man.settings.logic.adjustment_factor):.2f})"
            )
            lines.append(f"{settings_man.settings.logic.adjustment_factor}x 1 Exalted")
            lines.append(" = Just vendor it already!")

        self.currency_data_ready.emit({"success": True, "lines": lines})

    def _display_currency_suggestions(self, payload: dict) -> None:
        """Slot to display currency suggestion lines emitted by the background worker."""
        if not payload.get("success"):
            self.currency_text.setText(payload.get("error", "Error fetching currency data."))
            return

        lines: list[str] = payload.get("lines", [])
        if not lines:
            self.currency_text.setText("No data available.")
            return

        # Show first line as main text, append the rest
        self.currency_text.setText(lines[0])
        for line in lines[1:]:
            self.currency_text.append(line)


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
