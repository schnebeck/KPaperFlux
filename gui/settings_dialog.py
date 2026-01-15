from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QPushButton, 
    QComboBox, QHBoxLayout, QFileDialog, QMessageBox, QLabel
)
from PyQt6.QtCore import pyqtSignal
from core.config import AppConfig

class SettingsDialog(QDialog):
    """
    Dialog to configure application settings.
    """
    settings_changed = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Settings"))
        self.resize(500, 300)
        self.config = AppConfig()
        
        self._setup_ui()
        self._load_settings()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()
        
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
        
        layout.addLayout(form)
        
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
        
        # Trigger signal
        self.settings_changed.emit()
        self.accept()
