from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, 
    QSpinBox, QPushButton, QProgressBar, QMessageBox, QCheckBox,
    QStackedWidget, QWidget, QFormLayout
)
from PyQt6.QtCore import QThread, pyqtSignal, Qt, QTimer
from PyQt6.QtGui import QPixmap
from typing import Optional, List, Tuple
from core.scanner import get_scanner_driver, ScannerDriver
import os
import tempfile
import pikepdf

class DeviceDiscoveryWorker(QThread):
    """Asynchronous scanner discovery to prevent UI freeze."""
    finished = pyqtSignal(list)
    error = pyqtSignal(str)
    
    def __init__(self, driver: ScannerDriver):
        super().__init__()
        self.driver = driver
        
    def run(self):
        try:
            devices = self.driver.list_devices()
            self.finished.emit(devices)
        except Exception as e:
            self.error.emit(str(e))

class ScannerWorker(QThread):
    finished = pyqtSignal(str) # Path
    error = pyqtSignal(str)
    progress_update = pyqtSignal(int, int)
    
    def __init__(self, driver: ScannerDriver, device: str, dpi: int, mode: str, use_adf: bool, duplex: bool, duplex_mode: str):
        super().__init__()
        self.driver = driver
        self.device = device
        self.dpi = dpi
        self.mode = mode
        self.use_adf = use_adf
        self.duplex = duplex
        self.duplex_mode = duplex_mode
        
    def run(self):
        try:
            paths = self.driver.scan_pages(
                self.device, self.dpi, self.mode, 
                self.use_adf, self.duplex, self.duplex_mode,
                progress_callback=self.progress_update.emit
            )
            
            if not paths:
                self.error.emit("Scan returned no data.")
                return

            if len(paths) == 1:
                self.finished.emit(paths[0])
            else:
                # Merge into one PDF
                fd, out_path = tempfile.mkstemp(suffix=".pdf", prefix="scan_batch_")
                os.close(fd)
                
                with pikepdf.new() as combined:
                    for p in paths:
                        with pikepdf.open(p) as src:
                            combined.pages.extend(src.pages)
                        try: os.remove(p) # Cleanup individual pages
                        except: pass
                    combined.save(out_path)
                
                self.finished.emit(out_path)
                
        except Exception as e:
            self.error.emit(str(e))

class ScannerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Scanner"))
        self.setMinimumWidth(480)
        
        self.driver = get_scanner_driver("auto")
        self.scanned_file = None
        
        # Determine image path
        self.icon_path = "/home/schnebeck/Dokumente/Projects/KPaperFlux/resources/images/scanner_icon.png"
        
        self._init_ui()
        self._load_devices()
        
    def _init_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(15)
        
        self.stack = QStackedWidget()
        
        # --- PAGE 0: LOADING ---
        self.loading_page = QWidget()
        loading_layout = QVBoxLayout(self.loading_page)
        loading_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        if os.path.exists(self.icon_path):
            img_label = QLabel()
            pix = QPixmap(self.icon_path).scaled(100, 100, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            img_label.setPixmap(pix)
            img_label.setMargin(10)
            loading_layout.addWidget(img_label, alignment=Qt.AlignmentFlag.AlignCenter)
        
        self.loading_label = QLabel(self.tr("Searching for scanners..."))
        self.loading_label.setStyleSheet("font-weight: bold; color: #555; font-size: 14px;")
        loading_layout.addWidget(self.loading_label, alignment=Qt.AlignmentFlag.AlignCenter)
        
        self.search_progress = QProgressBar()
        self.search_progress.setRange(0, 0)
        self.search_progress.setFixedSize(280, 4)
        loading_layout.addWidget(self.search_progress, alignment=Qt.AlignmentFlag.AlignCenter)
        
        self.stack.addWidget(self.loading_page)
        
        # --- PAGE 1: SETTINGS ---
        self.settings_page = QWidget()
        settings_main_layout = QHBoxLayout(self.settings_page)
        settings_main_layout.setContentsMargins(0, 0, 0, 0)
        settings_main_layout.setSpacing(15)
        
        # Left Panel (Icon)
        if os.path.exists(self.icon_path):
            self.side_icon = QLabel()
            pix = QPixmap(self.icon_path).scaled(80, 80, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.side_icon.setPixmap(pix)
            self.side_icon.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
            settings_main_layout.addWidget(self.side_icon)
        
        # Right Panel (Form)
        right_panel = QVBoxLayout()
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(10)
        
        self.device_combo = QComboBox()
        self.device_combo.setMinimumHeight(30)
        form.addRow(self.tr("Device:"), self.device_combo)
        
        self.dpi_spin = QSpinBox()
        self.dpi_spin.setRange(75, 1200)
        self.dpi_spin.setValue(200)
        self.dpi_spin.setSuffix(" dpi")
        self.dpi_spin.setMinimumHeight(30)
        form.addRow(self.tr("Resolution:"), self.dpi_spin)
        
        self.mode_combo = QComboBox()
        self.mode_combo.addItem(self.tr("Color"), "Color")
        self.mode_combo.addItem(self.tr("Gray"), "Gray")
        self.mode_combo.addItem(self.tr("Lineart"), "Lineart")
        self.mode_combo.setMinimumHeight(30)
        form.addRow(self.tr("Mode:"), self.mode_combo)
        
        right_panel.addLayout(form)
        
        # ADF & Duplex
        adv_layout = QVBoxLayout()
        adv_layout.setContentsMargins(0, 10, 0, 0)
        adv_layout.setSpacing(8)
        
        self.chk_adf = QCheckBox(self.tr("Use Automatic Document Feeder (ADF)"))
        self.chk_adf.setToolTip(self.tr("Enables the automatic paper tray for scanning multiple pages at once."))
        
        self.chk_duplex = QCheckBox(self.tr("Duplex Scan (Double-Sided)"))
        self.chk_duplex.toggled.connect(self._on_duplex_toggled)
        
        adv_layout.addWidget(self.chk_adf)
        adv_layout.addWidget(self.chk_duplex)
        
        # Duplex Mode Sub-Settings
        self.duplex_settings = QWidget()
        duplex_layout = QFormLayout(self.duplex_settings)
        duplex_layout.setContentsMargins(20, 0, 0, 0) # Indent
        
        self.combo_duplex_mode = QComboBox()
        self.combo_duplex_mode.addItem(self.tr("Long Edge (Standard)"), "LongEdge")
        self.combo_duplex_mode.addItem(self.tr("Short Edge (Flip)"), "ShortEdge")
        duplex_layout.addRow(self.tr("Duplex Orientation:"), self.combo_duplex_mode)
        
        self.duplex_settings.setVisible(False)
        adv_layout.addWidget(self.duplex_settings)
        
        right_panel.addLayout(adv_layout)
        settings_main_layout.addLayout(right_panel)
        
        self.stack.addWidget(self.settings_page)
        self.main_layout.addWidget(self.stack)
        
        # Bottom Progress (Only during scan)
        self.scan_progress = QProgressBar()
        self.scan_progress.setVisible(False)
        self.main_layout.addWidget(self.scan_progress)
        
        # Buttons
        btn_layout = QHBoxLayout()
        self.scan_btn = QPushButton(self.tr("Start Scan"))
        self.scan_btn.setMinimumSize(110, 36)
        self.scan_btn.setStyleSheet("font-weight: bold;")
        self.scan_btn.setEnabled(False)
        self.scan_btn.clicked.connect(self.start_scan)
        self.scan_btn.setDefault(True)
        
        self.cancel_btn = QPushButton(self.tr("Cancel"))
        self.cancel_btn.setMinimumSize(90, 36)
        self.cancel_btn.clicked.connect(self.reject)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.scan_btn)
        btn_layout.addWidget(self.cancel_btn)
        self.main_layout.addLayout(btn_layout)
        
    def _on_duplex_toggled(self, checked):
        self.duplex_settings.setVisible(checked)
        if checked:
            self.chk_adf.setChecked(True) # Duplex usually implies ADF
            
    def _load_devices(self):
        self.discovery_worker = DeviceDiscoveryWorker(self.driver)
        self.discovery_worker.finished.connect(self._on_devices_found)
        self.discovery_worker.error.connect(self._on_discovery_error)
        self.discovery_worker.start()
        
    def _on_devices_found(self, devices: List[Tuple[str, str, str, str]]):
        self.device_combo.clear()
        if not devices:
            self.device_combo.addItem(self.tr("No devices found"), None)
            self.scan_btn.setEnabled(False)
            self.loading_label.setText(self.tr("No scanners detected."))
            self.search_progress.setVisible(False)
        else:
            for dev in devices:
                label = f"{dev[1]} {dev[2]}"
                self.device_combo.addItem(label, dev[0])
            self.scan_btn.setEnabled(True)
            self.stack.setCurrentIndex(1)
            QTimer.singleShot(50, self.adjustSize)
            
    def _on_discovery_error(self, msg):
        self.loading_label.setText(self.tr("Discovery Error"))
        self.search_progress.setVisible(False)
        QMessageBox.warning(self, self.tr("Discovery Failed"), msg)
        
    def start_scan(self):
        device_id = self.device_combo.currentData()
        if not device_id: return
            
        self.scan_btn.setEnabled(False)
        self.scan_progress.setVisible(True)
        self.scan_progress.setRange(0, 0)
        self.scan_progress.setFormat(self.tr("Initializing..."))
        
        self.worker = ScannerWorker(
            self.driver, device_id, 
            self.dpi_spin.value(),
            self.mode_combo.currentData(),
            self.chk_adf.isChecked(),
            self.chk_duplex.isChecked(),
            self.combo_duplex_mode.currentData()
        )
        self.worker.finished.connect(self.on_scan_finished)
        self.worker.error.connect(self.on_scan_error)
        self.worker.progress_update.connect(self.on_progress)
        self.worker.start()
        
    def on_progress(self, current, total):
        if total > 0:
            self.scan_progress.setRange(0, total)
            self.scan_progress.setValue(current)
            self.scan_progress.setFormat(self.tr(f"Scanning page {current} of {total}..."))
        else:
            self.scan_progress.setRange(0, 0)
            self.scan_progress.setFormat(self.tr(f"Scanning page {current}..."))

    def on_scan_finished(self, path):
        self.scan_progress.setVisible(False)
        self.scanned_file = path
        if os.path.exists(path):
            self.accept()
        else:
            self.on_scan_error(self.tr("Output file missing."))
            
    def on_scan_error(self, msg):
        self.scan_progress.setVisible(False)
        self.scan_btn.setEnabled(True)
        QMessageBox.critical(self, self.tr("Scan Error"), msg)
        
    def get_scanned_file(self) -> Optional[str]:
        return self.scanned_file
