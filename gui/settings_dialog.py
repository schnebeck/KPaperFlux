"""
------------------------------------------------------------------------------
Project:        KPaperFlux
File:           gui/settings_dialog.py
Version:        1.0.0
Producer:       thorsten.schnebeck@gmx.net
Generator:      Antigravity
Description:    Settings dialog: language, vault and transfer paths, analysis
                engine connection and logging.
------------------------------------------------------------------------------
"""

from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QPushButton,
    QComboBox, QHBoxLayout, QFileDialog, QMessageBox, QLabel, QTabWidget, QWidget, QTextEdit,
    QSpinBox, QCheckBox, QTableWidget, QTableWidgetItem, QAbstractItemView, QToolButton, QGroupBox
)
from PyQt6.QtCore import pyqtSignal, Qt, QEvent, QUrl
from PyQt6.QtGui import QDesktopServices
from core.logger import get_logger
logger = get_logger("gui.settings_dialog")

# Core Imports
from core.config import AppConfig
from core.engines.fluxsense_adapter import ERROR_BACKEND_TIMEOUT, ERROR_BACKEND_UNREACHABLE
from core.engines.fluxsense_client import FluxSenseClient, FluxSenseError, create_fluxsense_client
from core.identity_parser import parse_identity_signature

# GUI Imports
from gui.vocabulary_settings import VocabularySettingsWidget

from gui.utils import show_selectable_message_box

class SettingsDialog(QDialog):

    """
    Dialog to configure application settings.
    """
    settings_changed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget]=None, plugin_manager=None) -> None:
        super().__init__(parent)
        self.config = parent.app_config if parent and hasattr(parent, 'app_config') else AppConfig()
        self.plugin_manager = plugin_manager
        self.setWindowTitle(self.tr("Settings"))

        self._setup_ui()
        self.retranslate_ui()
        self._load_settings()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Tabs
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # --- General Tab ---
        general_tab = QWidget()
        form = QFormLayout(general_tab)

        # Language
        self.lbl_lang = QLabel("")
        self.combo_lang = QComboBox()
        self.combo_lang.addItems(["en", "de"])
        form.addRow(self.lbl_lang, self.combo_lang)

        # Vault Path
        self.lbl_vault = QLabel("")
        self.edit_vault = QLineEdit()
        self.btn_vault = QPushButton("")
        self.btn_vault.clicked.connect(self._browse_vault)
        h_vault = QHBoxLayout()
        h_vault.setContentsMargins(0, 0, 0, 0)
        h_vault.addWidget(self.edit_vault)
        h_vault.addWidget(self.btn_vault)
        form.addRow(self.lbl_vault, h_vault)

        # OCR Binary
        self.lbl_ocr = QLabel("")
        self.edit_ocr = QLineEdit()
        self.btn_ocr = QPushButton("")
        self.btn_ocr.clicked.connect(self._browse_ocr)
        h_ocr = QHBoxLayout()
        h_ocr.setContentsMargins(0, 0, 0, 0)
        h_ocr.addWidget(self.edit_ocr)
        h_ocr.addWidget(self.btn_ocr)
        form.addRow(self.lbl_ocr, h_ocr)

        # Transfer Path (Phase 2.1)
        self.lbl_transfer = QLabel("")
        self.edit_transfer = QLineEdit()
        self.btn_transfer = QPushButton("")
        self.btn_transfer.clicked.connect(self._browse_transfer)
        h_transfer = QHBoxLayout()
        h_transfer.setContentsMargins(0, 0, 0, 0)
        h_transfer.addWidget(self.edit_transfer)
        h_transfer.addWidget(self.btn_transfer)
        form.addRow(self.lbl_transfer, h_transfer)

        # Analysis Engine (FluxSense)
        self.lbl_engine_mode = QLabel("")
        self.combo_engine_mode = QComboBox()
        self.combo_engine_mode.addItem("", AppConfig.FLUXSENSE_MODE_LIBRARY)
        self.combo_engine_mode.addItem("", AppConfig.FLUXSENSE_MODE_REST)
        self.combo_engine_mode.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.combo_engine_mode.currentIndexChanged.connect(self._toggle_engine_mode_ui)
        form.addRow(self.lbl_engine_mode, self.combo_engine_mode)

        self.lbl_engine_llm_url = QLabel("")
        self.edit_engine_llm_url = QLineEdit()
        form.addRow(self.lbl_engine_llm_url, self.edit_engine_llm_url)

        self.lbl_engine_url = QLabel("")
        self.edit_engine_url = QLineEdit()
        self.edit_engine_url.setPlaceholderText(AppConfig.DEFAULT_FLUXSENSE_URL)
        form.addRow(self.lbl_engine_url, self.edit_engine_url)

        self.lbl_engine_timeout = QLabel("")
        self.spin_engine_timeout = QSpinBox()
        self.spin_engine_timeout.setRange(30, 14400)
        self.spin_engine_timeout.setSingleStep(60)
        form.addRow(self.lbl_engine_timeout, self.spin_engine_timeout)

        self.lbl_engine_parallel = QLabel("")
        self.spin_engine_parallel = QSpinBox()
        self.spin_engine_parallel.setRange(1, AppConfig.MAX_ANALYSIS_CONCURRENCY)
        form.addRow(self.lbl_engine_parallel, self.spin_engine_parallel)

        self.lbl_engine_note = QLabel("")
        self.lbl_engine_note.setWordWrap(True)
        form.addRow("", self.lbl_engine_note)

        self.btn_test_engine = QPushButton("")
        self.btn_test_engine.clicked.connect(self._test_engine_connection)
        form.addRow("", self.btn_test_engine)

        # Advanced -> Energy management (optional, collapsed, library mode only)
        self.btn_engine_advanced = QToolButton()
        self.btn_engine_advanced.setCheckable(True)
        self.btn_engine_advanced.setChecked(False)
        self.btn_engine_advanced.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.btn_engine_advanced.setArrowType(Qt.ArrowType.RightArrow)
        self.btn_engine_advanced.toggled.connect(self._toggle_engine_advanced)
        form.addRow("", self.btn_engine_advanced)

        self.box_energy = QGroupBox("")
        energy_form = QFormLayout(self.box_energy)
        self.lbl_energy_note = QLabel("")
        self.lbl_energy_note.setWordWrap(True)
        energy_form.addRow(self.lbl_energy_note)
        self.lbl_wol_url = QLabel("")
        self.edit_wol_url = QLineEdit()
        energy_form.addRow(self.lbl_wol_url, self.edit_wol_url)
        self.lbl_wol_device = QLabel("")
        self.edit_wol_device = QLineEdit()
        energy_form.addRow(self.lbl_wol_device, self.edit_wol_device)
        self.lbl_wol_token = QLabel("")
        self.edit_wol_token = QLineEdit()
        energy_form.addRow(self.lbl_wol_token, self.edit_wol_token)
        self.box_energy.setVisible(False)
        form.addRow(self.box_energy)

        self.tabs.addTab(general_tab, self.tr("General"))

        # --- Vocabulary Tab ---
        self.vocab_widget = VocabularySettingsWidget()
        self.tabs.addTab(self.vocab_widget, self.tr("Vocabulary"))

        # --- Identity Tab (Phase 100) ---
        identity_tab = QWidget()
        form_ident = QFormLayout(identity_tab)

        # Private
        self.lbl_sig_private = QLabel("")
        self.edit_sig_private = QTextEdit()
        self.edit_sig_private.setMaximumHeight(80)

        self.btn_analyze_priv = QPushButton("")
        self.btn_analyze_priv.clicked.connect(lambda: self._analyze_signature("PRIVATE"))

        form_ident.addRow(self.lbl_sig_private, self.edit_sig_private)
        form_ident.addRow("", self.btn_analyze_priv)

        # Business
        self.lbl_sig_business = QLabel("")
        self.edit_sig_business = QTextEdit()
        self.edit_sig_business.setMaximumHeight(80)

        self.btn_analyze_bus = QPushButton("")
        self.btn_analyze_bus.clicked.connect(lambda: self._analyze_signature("BUSINESS"))

        form_ident.addRow(self.lbl_sig_business, self.edit_sig_business)
        form_ident.addRow("", self.btn_analyze_bus)

        self.lbl_sig_note = QLabel("")
        form_ident.addRow(self.lbl_sig_note)

        form_ident.addRow(QLabel(self.tr("Note: If these signatures appear in 'Sender', the document is OUTGOING.")))

        self.tabs.addTab(identity_tab, self.tr("Identity"))

        # --- Logging Tab ---
        logging_tab = QWidget()
        form_log = QFormLayout(logging_tab)
 
        self.lbl_log_level = QLabel("")
        self.combo_log_level = QComboBox()
        self.combo_log_level.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        form_log.addRow(self.lbl_log_level, self.combo_log_level)
 
        self.cb_debug_ai = QCheckBox("")
        form_log.addRow("", self.cb_debug_ai)
 
        self.cb_debug_db = QCheckBox("")
        form_log.addRow("", self.cb_debug_db)
 
        self.btn_open_log = QPushButton("")
        self.btn_open_log.clicked.connect(self._open_log_file)
        form_log.addRow("", self.btn_open_log)
 
        self.tabs.addTab(logging_tab, "")

        # --- Plugins Tab ---
        plugins_tab = QWidget()
        plugins_layout = QVBoxLayout(plugins_tab)

        self.lbl_plugins_count = QLabel("")
        plugins_layout.addWidget(self.lbl_plugins_count)

        self.tbl_plugins = QTableWidget()
        self.tbl_plugins.setColumnCount(4)
        self.tbl_plugins.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl_plugins.setAlternatingRowColors(True)
        self.tbl_plugins.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl_plugins.horizontalHeader().setStretchLastSection(True)
        self.tbl_plugins.verticalHeader().setVisible(False)
        plugins_layout.addWidget(self.tbl_plugins)

        self.lbl_plugin_dirs = QLabel("")
        self.lbl_plugin_dirs.setWordWrap(True)
        plugins_layout.addWidget(self.lbl_plugin_dirs)

        self._populate_plugins_tab()

        self.tabs.addTab(plugins_tab, self.tr("Plugins"))

        # Buttons
        btn_box = QHBoxLayout()
        self.btn_save = QPushButton(self.tr("Save"))
        self.btn_save.clicked.connect(self._save_settings)
        self.btn_cancel = QPushButton(self.tr("Cancel"))
        self.btn_cancel.clicked.connect(self.reject)

        btn_box.addStretch()
        btn_box.addWidget(self.btn_save)
        btn_box.addWidget(self.btn_cancel)
        layout.addLayout(btn_box)

    def _populate_plugins_tab(self) -> None:
        """Fills the plugins table with data from the plugin manager."""
        col_headers = [
            self.tr("Name"),
            self.tr("Version"),
            self.tr("Author"),
            self.tr("Description"),
        ]
        self.tbl_plugins.setHorizontalHeaderLabels(col_headers)

        if self.plugin_manager is None:
            self.lbl_plugins_count.setText(self.tr("Loaded Plugins (%d)") % 0)
            self.tbl_plugins.setRowCount(1)
            item = QTableWidgetItem(self.tr("Plugin manager not available."))
            self.tbl_plugins.setItem(0, 0, item)
            self.lbl_plugin_dirs.setText("")
            return

        plugin_list = self.plugin_manager.get_plugin_info_list()
        count = len(plugin_list)
        self.lbl_plugins_count.setText(self.tr("Loaded Plugins (%d)") % count)

        if count == 0:
            self.tbl_plugins.setRowCount(1)
            item = QTableWidgetItem(self.tr("No plugins loaded."))
            self.tbl_plugins.setItem(0, 0, item)
        else:
            self.tbl_plugins.setRowCount(count)
            for row, info in enumerate(plugin_list):
                self.tbl_plugins.setItem(row, 0, QTableWidgetItem(info.get("name", "")))
                self.tbl_plugins.setItem(row, 1, QTableWidgetItem(info.get("version", "")))
                self.tbl_plugins.setItem(row, 2, QTableWidgetItem(info.get("author", "")))
                self.tbl_plugins.setItem(row, 3, QTableWidgetItem(info.get("description", "")))

        dirs = getattr(self.plugin_manager, "plugin_dirs", [])
        if dirs:
            dirs_str = ", ".join(str(d) for d in dirs)
            self.lbl_plugin_dirs.setText(f"{self.tr('Plugin directory:')} {dirs_str}")
        else:
            self.lbl_plugin_dirs.setText("")

    def _load_settings(self) -> None:
        self.combo_lang.setCurrentText(self.config.get_language())
        self.edit_vault.setText(self.config.get_vault_path())
        self.edit_ocr.setText(self.config.get_ocr_binary())
        self.edit_transfer.setText(self.config.get_transfer_path())
        
        mode_idx = self.combo_engine_mode.findData(self.config.get_fluxsense_mode())
        self.combo_engine_mode.setCurrentIndex(max(0, mode_idx))
        self.edit_engine_url.setText(self.config.get_fluxsense_url())
        self.edit_engine_llm_url.setText(self.config.get_fluxsense_llm_url())
        wol = self.config.get_fluxsense_wol()
        self.edit_wol_url.setText(wol["url"])
        self.edit_wol_device.setText(wol["device"])
        self.edit_wol_token.setText(wol["token_command"])
        self.spin_engine_timeout.setValue(self.config.get_fluxsense_timeout())
        self.spin_engine_parallel.setValue(self.config.get_analysis_concurrency())
        self._toggle_engine_mode_ui()

        self.edit_sig_private.setPlainText(self.config.get_private_signature())
        self.edit_sig_business.setPlainText(self.config.get_business_signature())

        # Logging
        self.combo_log_level.setCurrentText(self.config.get_log_level())
        cmp_levels = self.config.get_log_components()
        self.cb_debug_ai.setChecked(cmp_levels.get("ai") == "DEBUG")
        self.cb_debug_db.setChecked(cmp_levels.get("database") == "DEBUG")

    def _browse_vault(self) -> None:
        path = QFileDialog.getExistingDirectory(self, self.tr("Select Vault Directory"), self.edit_vault.text())
        if path:
            self.edit_vault.setText(path)

    def _browse_ocr(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, self.tr("Select OCR Binary"), self.edit_ocr.text())
        if path:
            self.edit_ocr.setText(path)

    def _browse_transfer(self) -> None:
        path = QFileDialog.getExistingDirectory(self, self.tr("Select Transfer Directory"), self.edit_transfer.text())
        if path:
            self.edit_transfer.setText(path)

    def _save_settings(self) -> None:
        self.config.set_language(self.combo_lang.currentText())
        self.config.set_vault_path(self.edit_vault.text())
        self.config.set_ocr_binary(self.edit_ocr.text())
        self.config.set_transfer_path(self.edit_transfer.text())
        
        self._store_engine_settings()

        self.config.set_private_signature(self.edit_sig_private.toPlainText())
        self.config.set_business_signature(self.edit_sig_business.toPlainText())

        # Logging
        self.config.set_log_level(self.combo_log_level.currentText())
        cmp_levels = {}
        if self.cb_debug_ai.isChecked():
            cmp_levels["ai"] = "DEBUG"
        if self.cb_debug_db.isChecked():
            cmp_levels["database"] = "DEBUG"
        self.config.set_log_components(cmp_levels)

        # Trigger signal
        self.settings_changed.emit()
        self.accept()

    def _store_engine_settings(self) -> None:
        """Persists the FluxSense engine settings from the dialog (empty values = FluxSense's config)."""
        self.config.set_fluxsense_mode(self.combo_engine_mode.currentData() or AppConfig.DEFAULT_FLUXSENSE_MODE)
        self.config.set_fluxsense_url(self.edit_engine_url.text().strip() or AppConfig.DEFAULT_FLUXSENSE_URL)
        self.config.set_fluxsense_llm_url(self.edit_engine_llm_url.text().strip())
        self.config.set_fluxsense_timeout(self.spin_engine_timeout.value())
        self.config.set_fluxsense_wol(self.edit_wol_url.text().strip(), self.edit_wol_device.text().strip(),
                                      self.edit_wol_token.text().strip())
        self.config.set_analysis_concurrency(self.spin_engine_parallel.value())

    def _energy_hooks(self) -> dict:
        """FluxSense hook overrides from the energy-management fields (only filled values)."""
        hooks = {"wol_url": self.edit_wol_url.text().strip(), "wol_device": self.edit_wol_device.text().strip(),
                 "wol_token_command": self.edit_wol_token.text().strip()}
        return {key: value for key, value in hooks.items() if value}

    def _create_engine_client(self) -> FluxSenseClient:
        """Creates a FluxSense client from the values currently shown in the dialog."""
        return create_fluxsense_client(
            self.combo_engine_mode.currentData() or AppConfig.DEFAULT_FLUXSENSE_MODE,
            self.edit_engine_url.text().strip() or AppConfig.DEFAULT_FLUXSENSE_URL,
            self.spin_engine_timeout.value(),
            llm_url=self.edit_engine_llm_url.text().strip(),
            hooks=self._energy_hooks(),
        )

    def _toggle_engine_mode_ui(self) -> None:
        """Library mode: AI server URL and energy management; REST mode: the FluxSense service URL."""
        form = self.tabs.widget(0).layout()
        is_rest = self.combo_engine_mode.currentData() == AppConfig.FLUXSENSE_MODE_REST
        form.setRowVisible(self.edit_engine_url, is_rest)
        form.setRowVisible(self.edit_engine_llm_url, not is_rest)
        form.setRowVisible(self.btn_engine_advanced, not is_rest)
        form.setRowVisible(self.box_energy, not is_rest and self.btn_engine_advanced.isChecked())

    def _toggle_engine_advanced(self, expanded: bool) -> None:
        """Expands or collapses the optional energy-management section."""
        self.btn_engine_advanced.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        self.box_energy.setVisible(expanded)
        self._toggle_engine_mode_ui()

    def _failure_text(self, error_code: Optional[str], url: Optional[str]) -> str:
        """Generic message for an unreachable or slow AI server; mentions waking only if energy management is set up."""
        where = url or self.tr("the configured address")
        if error_code == ERROR_BACKEND_TIMEOUT:
            text = self.tr("AI server at %s did not answer in time. Please try again later or increase the analysis timeout.") % where
        else:
            text = self.tr("AI server not reachable at %s. Please check the AI server settings.") % where
        if self._energy_hooks().get("wol_url"):
            text += "\n" + self.tr("Energy management is configured: the AI server may still be waking up.")
        return text

    def _test_engine_connection(self) -> None:
        """Checks FluxSense and its AI server (lists models, analyzes nothing)."""
        client = self._create_engine_client()
        self.setCursor(Qt.CursorShape.WaitCursor)
        try:
            health = client.health()
        except FluxSenseError as e:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            if e.error_code in (ERROR_BACKEND_UNREACHABLE, ERROR_BACKEND_TIMEOUT):
                text = self._failure_text(e.error_code, client.server_url())
            else:
                text = self.tr("FluxSense is not available:") + f"\n{e}"
            show_selectable_message_box(self, self.tr("Connection Failed"), text, icon=QMessageBox.Icon.Critical)
            return
        self.setCursor(Qt.CursorShape.ArrowCursor)

        version = str(health.get("version", "?"))
        if health.get("llm_backend"):
            show_selectable_message_box(self, self.tr("Success"),
                                        self.tr("FluxSense %s is ready.") % version, icon=QMessageBox.Icon.Information)
        else:
            show_selectable_message_box(self, self.tr("Connection Failed"),
                                        self._failure_text(ERROR_BACKEND_UNREACHABLE, health.get("server_url") or client.server_url()),
                                        icon=QMessageBox.Icon.Warning)

    def _analyze_signature(self, id_type: str) -> None:
        """
        Turns the signature text into a structured identity profile via the
        FluxSense LLM backend (library mode) and saves it.

        Args:
            id_type: 'PRIVATE' or 'BUSINESS'.
        """
        if id_type == "PRIVATE":
            text = self.edit_sig_private.toPlainText()
        else:
            text = self.edit_sig_business.toPlainText()

        if not text.strip():
            show_selectable_message_box(self, self.tr("Missing Input"), self.tr("Please enter a signature text first."), icon=QMessageBox.Icon.Warning)
            return

        self.setCursor(Qt.CursorShape.WaitCursor)
        try:
            profile = parse_identity_signature(text, self._create_engine_client())
        except FluxSenseError as e:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            show_selectable_message_box(self, self.tr("Error"), self.tr("AI Error: %s") % e, icon=QMessageBox.Icon.Critical)
            return
        self.setCursor(Qt.CursorShape.ArrowCursor)

        if not profile:
            show_selectable_message_box(self, self.tr("Analysis Failed"), self.tr("AI returned no valid profile."), icon=QMessageBox.Icon.Warning)
            return

        json_str = profile.model_dump_json(indent=2)
        if id_type == "PRIVATE":
            self.config.set_private_profile_json(json_str)
            message = self.tr("Extracted private profile (saved):")
        else:
            self.config.set_business_profile_json(json_str)
            message = self.tr("Extracted business profile (saved):")
        show_selectable_message_box(self, self.tr("Analysis Successful"), f"{message}\n\n{json_str}",
                                    icon=QMessageBox.Icon.Information)

    def _open_log_file(self) -> None:
        """Attempts to open the log file with the system default viewer."""
        log_path = self.config.get_log_file_path()
        if log_path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_path)))
        else:
            show_selectable_message_box(self, self.tr("Log File Missing"), self.tr("The log file has not been created yet."), icon=QMessageBox.Icon.Information)

    def changeEvent(self, event: QEvent) -> None:
        """Handle language change events."""
        if event and event.type() == QEvent.Type.LanguageChange:
            self.retranslate_ui()
        super().changeEvent(event)

    def retranslate_ui(self) -> None:
        """Updates all UI strings for on-the-fly localization."""
        self.setWindowTitle(self.tr("Settings"))
        
        # Tabs
        self.tabs.setTabText(0, self.tr("General"))
        self.tabs.setTabText(1, self.tr("Vocabulary"))
        self.tabs.setTabText(2, self.tr("Identity"))
        self.tabs.setTabText(3, self.tr("Logging"))
        self.tabs.setTabText(4, self.tr("Plugins"))

        # General Tab Labels
        self.lbl_lang.setText(self.tr("Language:"))
        self.lbl_vault.setText(self.tr("Vault Path:"))
        self.btn_vault.setText(self.tr("Browse..."))
        self.lbl_ocr.setText(self.tr("OCR Binary:"))
        self.btn_ocr.setText(self.tr("Browse..."))
        self.lbl_transfer.setText(self.tr("Transfer Folder:"))
        self.btn_transfer.setText(self.tr("Browse..."))
        self.lbl_engine_mode.setText(self.tr("Analysis Engine (FluxSense):"))
        self.combo_engine_mode.setItemText(0, self.tr("Library (in-process)"))
        self.combo_engine_mode.setItemText(1, self.tr("REST service"))
        self.lbl_engine_url.setText(self.tr("FluxSense URL:"))
        self.lbl_engine_llm_url.setText(self.tr("AI Server URL:"))
        self.edit_engine_llm_url.setPlaceholderText(self.tr("Empty: use the FluxSense configuration"))
        self.edit_engine_llm_url.setToolTip(self.tr("OpenAI-compatible endpoint of your AI server. Leave empty to keep the value from the FluxSense configuration."))
        self.lbl_engine_timeout.setText(self.tr("Analysis Timeout:"))
        self.spin_engine_timeout.setSuffix(f" {self.tr('s')}")
        self.lbl_engine_note.setText(self.tr("Models and all further AI settings come from the FluxSense configuration (~/.config/fluxsense/config.toml)."))
        self.lbl_engine_parallel.setText(self.tr("Parallel Analyses:"))
        self.spin_engine_parallel.setToolTip(self.tr("Number of documents analyzed at the same time (the AI backend serves several requests in parallel)."))
        self.btn_test_engine.setText(self.tr("Test Connection"))
        self.btn_engine_advanced.setText(self.tr("Advanced"))
        self.box_energy.setTitle(self.tr("Energy management"))
        self.lbl_energy_note.setText(self.tr("Only needed for an AI server that sleeps when idle: FluxSense then requests it from a WOL-Server before analyzing. Leave empty for an always-on server."))
        self.lbl_wol_url.setText(self.tr("WOL-Server URL:"))
        self.lbl_wol_device.setText(self.tr("Device:"))
        self.lbl_wol_token.setText(self.tr("Token command:"))
        self.edit_wol_token.setPlaceholderText(self.tr("Command that prints the API token (e.g. a keyring lookup)"))
        self.edit_wol_token.setToolTip(self.tr("The token itself is never stored, only the command that prints it."))

        # Identity Tab
        self.lbl_sig_private.setText(self.tr("Private Signature:\n(For Output/Debitor detection)"))
        self.edit_sig_private.setPlaceholderText(self.tr("Max Mustermann\nMusterstraße 1..."))
        self.btn_analyze_priv.setText(self.tr("Analyze Private Signature with AI"))
        self.btn_analyze_priv.setToolTip(self.tr("Extract structured data (Aliases, Address Parts) for better recognition."))
        self.lbl_sig_business.setText(self.tr("Business Signature:\n(For Output/Debitor detection)"))
        self.edit_sig_business.setPlaceholderText(self.tr("My Company GmbH\nGeschäftsführer: ..."))
        self.btn_analyze_bus.setText(self.tr("Analyze Business Signature with AI"))
        self.btn_analyze_bus.setToolTip(self.tr("Extract structured data (Aliases, Address Parts) for better recognition."))
        self.lbl_sig_note.setText(self.tr("Note: If these signatures appear in 'Sender', the document is OUTGOING."))

        # Logging Tab
        self.lbl_log_level.setText(self.tr("Global Log Level:"))
        self.cb_debug_ai.setText(self.tr("Verbose AI Debugging (Raw Prompts/Responses)"))
        self.cb_debug_db.setText(self.tr("Verbose Database Debugging (SQL Queries)"))
        self.btn_open_log.setText(self.tr("Open Log File"))

        # Buttons
        self.btn_save.setText(self.tr("Save"))
        self.btn_cancel.setText(self.tr("Cancel"))
