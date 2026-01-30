from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QPushButton,
    QComboBox, QHBoxLayout, QFileDialog, QMessageBox, QLabel, QTabWidget, QWidget, QTextEdit
)
from PyQt6.QtCore import pyqtSignal, Qt
import json

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
        self.setWindowTitle(self.tr("Settings"))
        self.resize(600, 500)
        self.config = AppConfig()

        self._setup_ui()
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
        self.combo_lang = QComboBox()
        self.combo_lang.addItems(["en", "de"])
        form.addRow(self.tr("Language:"), self.combo_lang)

        # Vault Path
        self.edit_vault = QLineEdit()
        self.btn_vault = QPushButton(self.tr("Browse..."))
        self.btn_vault.clicked.connect(self._browse_vault)
        h_vault = QHBoxLayout()
        h_vault.addWidget(self.edit_vault)
        h_vault.addWidget(self.btn_vault)
        form.addRow(self.tr("Vault Path:"), h_vault)

        # OCR Binary
        self.edit_ocr = QLineEdit()
        self.btn_ocr = QPushButton(self.tr("Browse..."))
        self.btn_ocr.clicked.connect(self._browse_ocr)
        h_ocr = QHBoxLayout()
        h_ocr.addWidget(self.edit_ocr)
        h_ocr.addWidget(self.btn_ocr)
        form.addRow(self.tr("OCR Binary:"), h_ocr)

        # Gemini Model
        self.combo_model = QComboBox()
        self.combo_model.setEditable(True) # Allow custom models
        self.combo_model.addItems([
            "gemini-2.0-flash",
            "gemini-1.5-flash",
            "gemini-1.5-flash-001",
            "gemini-1.5-pro",
            "gemini-pro"
        ])
        form.addRow(self.tr("Gemini Model:"), self.combo_model)

        # API Key
        self.edit_api_key = QLineEdit()
        self.edit_api_key.setPlaceholderText("google_api_key_...")
        form.addRow(self.tr("API Key:"), self.edit_api_key)

        self.tabs.addTab(general_tab, self.tr("General"))

        # --- Vocabulary Tab ---
        self.vocab_widget = VocabularySettingsWidget()
        self.tabs.addTab(self.vocab_widget, self.tr("Vocabulary"))

        # --- Identity Tab (Phase 100) ---
        identity_tab = QWidget()
        form_ident = QFormLayout(identity_tab)

        # Private
        self.edit_sig_private = QTextEdit()
        self.edit_sig_private.setPlaceholderText("Max Mustermann\nMusterstraße 1...")
        self.edit_sig_private.setMaximumHeight(80)

        btn_analyze_priv = QPushButton(self.tr("Analyze Private Signature with AI"))
        btn_analyze_priv.setToolTip(self.tr("Extract structured data (Aliases, Address Parts) for better recognition."))
        btn_analyze_priv.clicked.connect(lambda: self._analyze_signature("PRIVATE"))

        form_ident.addRow(self.tr("Private Signature:\n(For Output/Debitor detection)"), self.edit_sig_private)
        form_ident.addRow("", btn_analyze_priv)

        # Business
        self.edit_sig_business = QTextEdit()
        self.edit_sig_business.setPlaceholderText("My Company GmbH\nGeschäftsführer: ...")
        self.edit_sig_business.setMaximumHeight(80)

        btn_analyze_bus = QPushButton(self.tr("Analyze Business Signature with AI"))
        btn_analyze_bus.setToolTip(self.tr("Extract structured data (Aliases, Address Parts) for better recognition."))
        btn_analyze_bus.clicked.connect(lambda: self._analyze_signature("BUSINESS"))

        form_ident.addRow(self.tr("Business Signature:\n(For Output/Debitor detection)"), self.edit_sig_business)
        form_ident.addRow("", btn_analyze_bus)

        form_ident.addRow(QLabel(self.tr("Note: If these signatures appear in 'Sender', the document is OUTGOING.")))

        self.tabs.addTab(identity_tab, self.tr("Identity"))

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
        self.combo_model.setCurrentText(self.config.get_gemini_model())
        self.edit_api_key.setText(self.config.get_api_key())

        self.edit_sig_private.setPlainText(self.config.get_private_signature())
        self.edit_sig_business.setPlainText(self.config.get_business_signature())

    def _browse_vault(self):
        path = QFileDialog.getExistingDirectory(self, self.tr("Select Vault Directory"), self.edit_vault.text())
        if path:
            self.edit_vault.setText(path)

    def _browse_ocr(self):
        path, _ = QFileDialog.getOpenFileName(self, self.tr("Select OCR Binary"), self.edit_ocr.text())
        if path:
            self.edit_ocr.setText(path)

    def _save_settings(self):
        self.config.set_language(self.combo_lang.currentText())
        self.config.set_vault_path(self.edit_vault.text())
        self.config.set_ocr_binary(self.edit_ocr.text())
        self.config.set_gemini_model(self.combo_model.currentText())
        self.config.set_api_key(self.edit_api_key.text())

        self.config.set_private_signature(self.edit_sig_private.toPlainText())
        self.config.set_business_signature(self.edit_sig_business.toPlainText())

        # Trigger signal
        self.settings_changed.emit()
        self.accept()

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
