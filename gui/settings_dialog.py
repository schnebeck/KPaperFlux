from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QPushButton,
    QComboBox, QHBoxLayout, QFileDialog, QMessageBox, QLabel, QTabWidget, QWidget, QTextEdit,
    QSpinBox, QLayout, QCheckBox
)
import json
import sys
from typing import Optional
from PyQt6.QtCore import pyqtSignal, Qt, QTimer, QEvent, QCoreApplication

# Core Imports
from core.config import AppConfig
from core.ai_analyzer import AIAnalyzer

# GUI Imports
# Hinweis: Falls diese Module fehlen, muss die Dateistruktur entsprechend existieren.
try:
    from gui.vocabulary_settings import VocabularySettingsWidget
except ImportError:
    # Fallback Widget für Tests
    class VocabularySettingsWidget(QWidget):
        def __init__(self):
            super().__init__()
            QVBoxLayout(self).addWidget(QLabel("Vocabulary Settings Placeholder"))

# Hilfsfunktion für Message Boxen (Fallback, falls gui.utils fehlt)
try:
    from gui.utils import show_selectable_message_box
except ImportError:
    def show_selectable_message_box(parent, title, text, icon=QMessageBox.Icon.Information, buttons=QMessageBox.StandardButton.Ok):
        msg = QMessageBox(parent)
        msg.setWindowTitle(title)
        msg.setText(text)
        msg.setIcon(icon)
        msg.setStandardButtons(buttons)
        return msg.exec()

class SettingsDialog(QDialog):

    """
    Dialog to configure application settings.
    """
    settings_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = parent.app_config if parent and hasattr(parent, 'app_config') else AppConfig()
        self.setWindowTitle(self.tr("Settings"))

        self._setup_ui()
        self.retranslate_ui()
        self._load_settings()

    def _setup_ui(self):
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

        # AI Backend Provider
        self.lbl_provider = QLabel("")
        self.combo_provider = QComboBox()
        self.combo_provider.addItems([
            "Gemini (Cloud)", 
            "Ollama (Local)", 
            "OpenAI (Cloud)", 
            "Anthropic (Cloud)"
        ])
        self.combo_provider.currentIndexChanged.connect(self._toggle_ai_provider_ui)
        form.addRow(self.lbl_provider, self.combo_provider)

        # Provider-specific fields for toggling visibility
        self.provider_fields = {
            "gemini": [],
            "ollama": [],
            "openai": [],
            "anthropic": []
        }

        def add_provider_row(provider, label_text, widget_or_layout):
            form.addRow(label_text, widget_or_layout)
            self.provider_fields[provider].append(widget_or_layout)

        # Gemini API Key
        self.lbl_api_key = QLabel("")
        self.api_key_layout = QHBoxLayout()
        self.api_key_layout.setContentsMargins(0, 0, 0, 0)
        self.edit_api_key = QLineEdit()
        self.edit_api_key.setPlaceholderText("google_api_key_...")
        self.edit_api_key.textChanged.connect(self._on_api_key_changed)
        self.btn_verify_key = QPushButton("")
        self.btn_verify_key.clicked.connect(lambda: self._refresh_models(silent=False))
        self.lbl_key_status = QLabel()
        self.lbl_key_status.setFixedSize(24, 24)
        self.api_key_layout.addWidget(self.edit_api_key, 1)
        self.api_key_layout.addWidget(self.lbl_key_status)
        self.api_key_layout.addWidget(self.btn_verify_key)
        add_provider_row("gemini", self.lbl_api_key, self.api_key_layout)

        # Gemini Model
        self.lbl_model = QLabel("")
        self.combo_model = QComboBox()
        self.combo_model.setEditable(True) 
        self.combo_model.addItems(self.config._cached_models)
        add_provider_row("gemini", self.lbl_model, self.combo_model)

        # Ollama URL
        self.lbl_ollama_url = QLabel("")
        self.edit_ollama_url = QLineEdit()
        self.edit_ollama_url.setPlaceholderText("http://localhost:11434")
        add_provider_row("ollama", self.lbl_ollama_url, self.edit_ollama_url)

        # Ollama Model
        self.lbl_ollama_model = QLabel("")
        self.edit_ollama_model = QLineEdit()
        self.edit_ollama_model.setPlaceholderText("llama3")
        add_provider_row("ollama", self.lbl_ollama_model, self.edit_ollama_model)

        # Ollama Test Connection
        self.btn_refresh_ollama = QPushButton(self.tr("Test Connection"))
        self.btn_refresh_ollama.clicked.connect(self._test_ollama_connection)
        add_provider_row("ollama", "", self.btn_refresh_ollama)

        # OpenAI Key
        self.lbl_openai_key = QLabel("")
        self.edit_openai_key = QLineEdit()
        self.edit_openai_key.setEchoMode(QLineEdit.EchoMode.Password)
        add_provider_row("openai", self.lbl_openai_key, self.edit_openai_key)

        # OpenAI Model
        self.lbl_openai_model = QLabel("")
        self.edit_openai_model = QLineEdit()
        self.edit_openai_model.setPlaceholderText("gpt-4o")
        add_provider_row("openai", self.lbl_openai_model, self.edit_openai_model)

        # Anthropic Key
        self.lbl_anthropic_key = QLabel("")
        self.edit_anthropic_key = QLineEdit()
        self.edit_anthropic_key.setEchoMode(QLineEdit.EchoMode.Password)
        add_provider_row("anthropic", self.lbl_anthropic_key, self.edit_anthropic_key)

        # Anthropic Model
        self.lbl_anthropic_model = QLabel("")
        self.edit_anthropic_model = QLineEdit()
        self.edit_anthropic_model.setPlaceholderText("claude-3-5-sonnet-20240620")
        add_provider_row("anthropic", self.lbl_anthropic_model, self.edit_anthropic_model)

        # AI Retries
        self.lbl_ai_retries = QLabel("")
        self.spin_ai_retries = QSpinBox()
        self.spin_ai_retries.setRange(0, 10)
        form.addRow(self.lbl_ai_retries, self.spin_ai_retries)

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

    def _load_settings(self):
        self.combo_lang.setCurrentText(self.config.get_language())
        self.edit_vault.setText(self.config.get_vault_path())
        self.edit_ocr.setText(self.config.get_ocr_binary())
        self.edit_transfer.setText(self.config.get_transfer_path())
        
        provider = self.config.get_ai_provider()
        p_map = {"gemini": 0, "ollama": 1, "openai": 2, "anthropic": 3}
        self.combo_provider.setCurrentIndex(p_map.get(provider, 0))
        
        self.combo_model.setCurrentText(self.config.get_gemini_model())
        self.edit_api_key.setText(self.config.get_api_key())
        
        self.edit_ollama_url.setText(self.config.get_ollama_url())
        self.edit_ollama_model.setText(self.config.get_ollama_model())

        self.edit_openai_key.setText(self.config.get_openai_key())
        self.edit_openai_model.setText(self.config.get_openai_model())

        self.edit_anthropic_key.setText(self.config.get_anthropic_key())
        self.edit_anthropic_model.setText(self.config.get_anthropic_model())
        
        self.spin_ai_retries.setValue(self.config.get_ai_retries())
        self._toggle_ai_provider_ui()

        # Restore verification status icon
        is_verified = self.config._get_setting("AI", self.config.KEY_API_VERIFIED, None)
        self._update_status_icon(is_verified)
        
        # Auto-refresh if cache is empty but API key is present
        if not self.config._cached_models and self.edit_api_key.text():
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(100, lambda: self._refresh_models(silent=True))

        self.edit_sig_private.setPlainText(self.config.get_private_signature())
        self.edit_sig_business.setPlainText(self.config.get_business_signature())

        # Logging
        self.combo_log_level.setCurrentText(self.config.get_log_level())
        cmp_levels = self.config.get_log_components()
        self.cb_debug_ai.setChecked(cmp_levels.get("ai") == "DEBUG")
        self.cb_debug_db.setChecked(cmp_levels.get("database") == "DEBUG")

    def _browse_vault(self):
        path = QFileDialog.getExistingDirectory(self, self.tr("Select Vault Directory"), self.edit_vault.text())
        if path:
            self.edit_vault.setText(path)

    def _browse_ocr(self):
        path, _ = QFileDialog.getOpenFileName(self, self.tr("Select OCR Binary"), self.edit_ocr.text())
        if path:
            self.edit_ocr.setText(path)

    def _browse_transfer(self):
        path = QFileDialog.getExistingDirectory(self, self.tr("Select Transfer Directory"), self.edit_transfer.text())
        if path:
            self.edit_transfer.setText(path)

    def _save_settings(self):
        self.config.set_language(self.combo_lang.currentText())
        self.config.set_vault_path(self.edit_vault.text())
        self.config.set_ocr_binary(self.edit_ocr.text())
        self.config.set_transfer_path(self.edit_transfer.text())
        
        provider = "gemini"
        if self.combo_provider.currentIndex() == 1: provider = "ollama"
        elif self.combo_provider.currentIndex() == 2: provider = "openai"
        elif self.combo_provider.currentIndex() == 3: provider = "anthropic"
        self.config.set_ai_provider(provider)
        
        self.config.set_gemini_model(self.combo_model.currentText())
        self.config.set_api_key(self.edit_api_key.text())
        
        self.config.set_ollama_url(self.edit_ollama_url.text())
        self.config.set_ollama_model(self.edit_ollama_model.text())

        self.config.set_openai_key(self.edit_openai_key.text())
        self.config.set_openai_model(self.edit_openai_model.text())

        self.config.set_anthropic_key(self.edit_anthropic_key.text())
        self.config.set_anthropic_model(self.edit_anthropic_model.text())
        
        self.config.set_ai_retries(self.spin_ai_retries.value())

        # Persist verification status if known (True/False/None)
        if hasattr(self, "_last_verify_result"):
             self.config._set_setting("AI", self.config.KEY_API_VERIFIED, self._last_verify_result)

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

    def _on_api_key_changed(self):
        """Triggers a silent refresh when the user finished typing/pasting a key."""
        # Reset status icon when key changes
        self._update_status_icon(None)
        self._last_verify_result = None

        if not hasattr(self, "_refresh_timer"):
            from PyQt6.QtCore import QTimer
            self._refresh_timer = QTimer()
            self._refresh_timer.setSingleShot(True)
            self._refresh_timer.timeout.connect(lambda: self._refresh_models(silent=True))
        
        # Debounce: wait for 1.5 seconds after last change
        self._refresh_timer.start(1500)

    def _update_status_icon(self, success: Optional[bool]):
        """Updates the status label with a green check or red X."""
        if success is True:
            # Using KDE/Qt Standard Pixmaps (Checkmark)
            icon = self.style().standardIcon(self.style().StandardPixmap.SP_DialogApplyButton)
            self.lbl_key_status.setPixmap(icon.pixmap(18, 18))
            self.lbl_key_status.setToolTip(self.tr("API Key Verified"))
        elif success is False:
            # Using KDE/Qt Standard Pixmaps (Cancel/X)
            icon = self.style().standardIcon(self.style().StandardPixmap.SP_DialogCancelButton)
            self.lbl_key_status.setPixmap(icon.pixmap(18, 18))
            self.lbl_key_status.setToolTip(self.tr("API Key Invalid"))
        else:
            self.lbl_key_status.clear()
            self.lbl_key_status.setToolTip("")

    def _refresh_models(self, silent=False):
        """Dynamic fetch of available Gemini models."""
        api_key = self.edit_api_key.text().strip()
        if not api_key:
            show_selectable_message_box(self, self.tr("Missing API Key"), self.tr("Please enter an API Key first."), icon=QMessageBox.Icon.Warning)
            return

        self.setCursor(Qt.CursorShape.WaitCursor)
        self.btn_verify_key.setEnabled(False)
        try:
            # We use a temporary analyzer to list models
            analyzer = AIAnalyzer(api_key, model_name=self.config.get_gemini_model())
            models = analyzer.list_models()
            
            if models:
                self._last_verify_result = True
                self._update_status_icon(True)
                current_model = self.combo_model.currentText()
                self.combo_model.clear()
                self.combo_model.addItems(models)
                self.config._cached_models = models.copy()
                # Recover selection if it was in the new list
                idx = self.combo_model.findText(current_model)
                if idx >= 0:
                    self.combo_model.setCurrentIndex(idx)
                else:
                    self.combo_model.setCurrentText(current_model)
            else:
                self._last_verify_result = False
                self._update_status_icon(False)
                if not silent:
                    show_selectable_message_box(
                        self, 
                        self.tr("Refresh Failed"), 
                        self.tr("API returned an empty model list. Please check if your API Key has access to Gemini models."), 
                        icon=QMessageBox.Icon.Warning
                    )
        except Exception as e:
            # Check for common auth errors
            error_msg = str(e)
            if "API_KEY_INVALID" in error_msg or "403" in error_msg:
                msg = self.tr("Invalid API Key or Permission Denied.")
            elif "429" in error_msg:
                msg = self.tr("Rate limit exceeded.")
            else:
                msg = f"{self.tr('Failed to list models')}:\n{error_msg}"
            
            if not silent:
                self._last_verify_result = False
                self._update_status_icon(False)
                show_selectable_message_box(self, self.tr("Error"), msg, icon=QMessageBox.Icon.Critical)
            else:
                print(f"[AI] Background model refresh failed: {msg}")
        finally:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.btn_verify_key.setEnabled(True)

    def _analyze_signature(self, id_type: str):
        """
        Phase 101: Analyze user signature with AI.
        id_type: 'PRIVATE' or 'BUSINESS'
        """
        if id_type == "PRIVATE":
            text = self.edit_sig_private.toPlainText()
        else:
            text = self.edit_sig_business.toPlainText()

        if not text.strip():
            show_selectable_message_box(self, self.tr("Missing Input"), self.tr("Please enter a signature text first."), icon=QMessageBox.Icon.Warning)
            return

        # Instantiate AI (Blocking for MVP)
        api_key = self.config.get_api_key()
        if not api_key:
             show_selectable_message_box(self, self.tr("Error"), self.tr("No API Key configured."), icon=QMessageBox.Icon.Critical)
             return

        # Show busy cursor
        self.setCursor(Qt.CursorShape.WaitCursor)
        try:
            # We assume gemini-2.0-flash or configure model
            analyzer = AIAnalyzer(api_key, model_name=self.config.get_gemini_model())
            profile = analyzer.parse_identity_signature(text)

            self.setCursor(Qt.CursorShape.ArrowCursor)

            if profile:
                # Save JSON
                json_str = profile.model_dump_json(indent=2)
                if id_type == "PRIVATE":
                    self.config.set_private_profile_json(json_str)
                    target_name = "Private"
                else:
                    self.config.set_business_profile_json(json_str)
                    target_name = "Business"

                # Show Result
                show_selectable_message_box(
                    self,
                    self.tr("Analysis Successful"),
                    f"Extracted {target_name} Profile:\n\n{json_str}\n\n(Saved to Config)",
                    icon=QMessageBox.Icon.Information
                )
            else:
                show_selectable_message_box(self, self.tr("Analysis Failed"), self.tr("AI returned no valid profile."), icon=QMessageBox.Icon.Warning)

        except Exception as e:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            show_selectable_message_box(self, self.tr("Error"), f"AI Error: {e}", icon=QMessageBox.Icon.Critical)

    def _toggle_ai_provider_ui(self):
        idx = self.combo_provider.currentIndex()
        form = self.tabs.widget(0).layout() # The QFormLayout on General tab
        
        for p_name, fields in self.provider_fields.items():
            visible = False
            if p_name == "gemini" and idx == 0: visible = True
            elif p_name == "ollama" and idx == 1: visible = True
            elif p_name == "openai" and idx == 2: visible = True
            elif p_name == "anthropic" and idx == 3: visible = True
            
            for field in fields:
                if isinstance(field, QLayout):
                    form.setRowVisible(field, visible)
                else:
                    form.setRowVisible(field, visible)

    def _test_ollama_connection(self):
        url = self.edit_ollama_url.text().strip()
        from core.ai.ollama_provider import OllamaProvider
        provider = OllamaProvider(url)
        
        self.setCursor(Qt.CursorShape.WaitCursor)
        try:
            models = provider.list_models()
            self.setCursor(Qt.CursorShape.ArrowCursor)
            if models:
                show_selectable_message_box(
                    self, 
                    self.tr("Success"), 
                    f"{self.tr('Connected to Ollama!')}\n\n{self.tr('Available models')}:\n" + "\n".join(models[:10]),
                    icon=QMessageBox.Icon.Information
                )
            else:
                show_selectable_message_box(
                    self, 
                    self.tr("Connection Failed"), 
                    self.tr("Connected to Ollama, but no models found. Please pull a model first (e.g., 'ollama pull llama3')."),
                    icon=QMessageBox.Icon.Warning
                )
        except Exception as e:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            show_selectable_message_box(self, self.tr("Connection Failed"), f"{self.tr('Could not connect to Ollama')}:\n{e}", icon=QMessageBox.Icon.Critical)

    def _open_log_file(self):
        """Attempts to open the log file with the system default viewer."""
        import subprocess
        log_path = self.config.get_log_file_path()
        if log_path.exists():
            if sys.platform == 'win32':
                os.startfile(log_path)
            elif sys.platform == 'darwin':
                subprocess.call(('open', str(log_path)))
            else:
                subprocess.call(('xdg-open', str(log_path)))
        else:
            show_selectable_message_box(self, self.tr("Log File Missing"), self.tr("The log file has not been created yet."), icon=QMessageBox.Icon.Information)

    def changeEvent(self, event):
        """Handle language change events."""
        if event and event.type() == QEvent.Type.LanguageChange:
            self.retranslate_ui()
        super().changeEvent(event)

    def retranslate_ui(self):
        """Updates all UI strings for on-the-fly localization."""
        self.setWindowTitle(self.tr("Settings"))
        
        # Tabs
        self.tabs.setTabText(0, self.tr("General"))
        self.tabs.setTabText(1, self.tr("Vocabulary"))
        self.tabs.setTabText(2, self.tr("Identity"))
        self.tabs.setTabText(3, self.tr("Logging"))

        # General Tab Labels
        self.lbl_lang.setText(self.tr("Language:"))
        self.lbl_vault.setText(self.tr("Vault Path:"))
        self.btn_vault.setText(self.tr("Browse..."))
        self.lbl_ocr.setText(self.tr("OCR Binary:"))
        self.btn_ocr.setText(self.tr("Browse..."))
        self.lbl_transfer.setText(self.tr("Transfer Folder:"))
        self.btn_transfer.setText(self.tr("Browse..."))
        self.lbl_provider.setText(self.tr("AI Backend:"))
        
        self.lbl_api_key.setText(self.tr("Gemini API Key:"))
        self.btn_verify_key.setText(self.tr("Verify"))
        self.lbl_model.setText(self.tr("Gemini Model:"))
        self.lbl_ollama_url.setText(self.tr("Ollama URL:"))
        self.lbl_ollama_model.setText(self.tr("Ollama Model:"))
        self.btn_refresh_ollama.setText(self.tr("Test Connection"))
        self.lbl_openai_key.setText(self.tr("OpenAI API Key:"))
        self.lbl_openai_model.setText(self.tr("OpenAI Model:"))
        self.lbl_anthropic_key.setText(self.tr("Anthropic API Key:"))
        self.lbl_anthropic_model.setText(self.tr("Anthropic Model:"))
        self.lbl_ai_retries.setText(self.tr("AI Validation Retries:"))
        self.spin_ai_retries.setSuffix(f" {self.tr('Retries')}")

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
