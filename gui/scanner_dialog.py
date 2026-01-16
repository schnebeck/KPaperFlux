from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, 
    QSpinBox, QPushButton, QProgressBar, QMessageBox
)
from PyQt6.QtCore import QThread, pyqtSignal, Qt
from typing import Optional
from core.scanner import get_scanner_driver, ScannerDriver
import os

class ScannerWorker(QThread):
    finished = pyqtSignal(str) # Path
    error = pyqtSignal(str)
    
    def __init__(self, driver: ScannerDriver, device: str, dpi: int, mode: str):
        super().__init__()
        self.driver = driver
        self.device = device
        self.dpi = dpi
        self.mode = mode
        
    def run(self):
        try:
            path = self.driver.scan_page(self.device, self.dpi, self.mode)
            if path:
                self.finished.emit(path)
            else:
                self.error.emit("Scan returned no data.")
        except Exception as e:
            self.error.emit(str(e))

class ScannerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Scanner"))
        self.resize(400, 200)
        
        self.driver = get_scanner_driver("auto")
        self.scanned_file = None
        
        self._init_ui()
        self._load_devices()
        
    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        # Device Selection
        self.device_combo = QComboBox()
        layout.addWidget(QLabel(self.tr("Device:")))
        layout.addWidget(self.device_combo)
        
        # Settings Layout
        settings_layout = QHBoxLayout()
        
        # DPI
        self.dpi_spin = QSpinBox()
        self.dpi_spin.setRange(75, 1200)
        self.dpi_spin.setValue(200)
        self.dpi_spin.setSuffix(" dpi")
        
        settings_layout.addWidget(QLabel(self.tr("Resolution:")))
        settings_layout.addWidget(self.dpi_spin)
        
        # Mode
        self.mode_combo = QComboBox()
        self.mode_combo.addItem(self.tr("Color"), "Color")
        self.mode_combo.addItem(self.tr("Gray"), "Gray")
        self.mode_combo.addItem(self.tr("Lineart"), "Lineart")
        
        settings_layout.addWidget(QLabel(self.tr("Mode:")))
        settings_layout.addWidget(self.mode_combo)
        
        layout.addLayout(settings_layout)
        
        # Progress
        self.progress = QProgressBar()
        self.progress.setRange(0, 0) # Indeterminate
        self.progress.setVisible(False)
        layout.addWidget(self.progress)
        
        # Buttons
        btn_layout = QHBoxLayout()
        self.scan_btn = QPushButton(self.tr("Scan"))
        self.scan_btn.clicked.connect(self.start_scan)
        self.scan_btn.setDefault(True)
        
        self.cancel_btn = QPushButton(self.tr("Cancel"))
        self.cancel_btn.clicked.connect(self.reject)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.scan_btn)
        btn_layout.addWidget(self.cancel_btn)
        
        layout.addLayout(btn_layout)
        
    def _load_devices(self):
        try:
            devices = self.driver.list_devices()
            if not devices:
                self.device_combo.addItem(self.tr("No devices found"), None)
                self.scan_btn.setEnabled(False)
            else:
                for dev in devices:
                    # dev: (name, vendor, model, type)
                    label = f"{dev[1]} {dev[2]} ({dev[3]})"
                    self.device_combo.addItem(label, dev[0])
                self.scan_btn.setEnabled(True)
        except Exception as e:
            QMessageBox.critical(self, self.tr("Error"), self.tr(f"Failed to list devices: {e}"))
            
    def start_scan(self):
        device_id = self.device_combo.currentData()
        if not device_id:
            return
            
        dpi = self.dpi_spin.value()
        mode = self.mode_combo.currentText() # NOTE: This might need adjustment if we want to send English mode to backend
        # Actually in _init_ui I added "Color", "data". 
        # But QComboBox.addItems only takes list of texts. 
        # I changed to addItem(text, userData).
        # We need to retrieve userData to send to backend if backend expects English.
        mode = self.mode_combo.currentData()
        if not mode: # Fallback if no user data (should not happen with my change)
             mode = self.mode_combo.currentText()

        self.scan_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setFormat(self.tr("Scanning..."))
        
        self.worker = ScannerWorker(self.driver, device_id, dpi, mode)
        self.worker.finished.connect(self.on_scan_finished)
        self.worker.error.connect(self.on_scan_error)
        self.worker.start()
        
    def on_scan_finished(self, path):
        self.progress.setVisible(False)
        self.scanned_file = path
        # Verify file exists
        if os.path.exists(path):
            QMessageBox.information(self, self.tr("Success"), self.tr("Scan completed successfully."))
            self.accept()
        else:
            self.on_scan_error(self.tr("Output file missing."))
            
    def on_scan_error(self, msg):
        self.progress.setVisible(False)
        self.scan_btn.setEnabled(True)
        QMessageBox.critical(self, self.tr("Scan Error"), msg)
        
    def get_scanned_file(self) -> Optional[str]:
        return self.scanned_file
