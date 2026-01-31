from PyQt6.QtWidgets import (    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, 
    QSpinBox, QPushButton, QProgressBar, QMessageBox, QCheckBox,
    QStackedWidget, QWidget, QFormLayout, QFrame
)
from gui.utils import show_selectable_message_box
from PyQt6.QtCore import QThread, pyqtSignal, Qt, QTimer, QSettings
from PyQt6.QtGui import QPixmap, QIcon
from typing import Optional, List, Tuple
from core.scanner import get_scanner_driver, ScannerDriver
import os
import tempfile
import pikepdf

class DeviceDiscoveryWorker(QThread):
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
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    progress_update = pyqtSignal(int, int)
    
    def __init__(self, driver: ScannerDriver, device: str, dpi: int, mode: str, source: str, duplex_mode: str, page_format: str):
        super().__init__()
        self.driver = driver
        self.device = device
        self.dpi = dpi
        self.mode = mode
        self.source = source
        self.duplex_mode = duplex_mode
        self.page_format = page_format
        
    def run(self):
        try:
            paths = self.driver.scan_pages(
                self.device, self.dpi, self.mode, 
                self.source, self.duplex_mode,
                self.page_format,
                progress_callback=self.progress_update.emit
            )
            
            if not paths:
                self.error.emit("Scan returned no data.")
                return

            if len(paths) == 1:
                self.finished.emit(paths[0])
            else:
                fd, out_path = tempfile.mkstemp(suffix=".pdf", prefix="scan_batch_")
                os.close(fd)
                with pikepdf.new() as combined:
                    for p in paths:
                        with pikepdf.open(p) as src:
                            combined.pages.extend(src.pages)
                        try: os.remove(p)
                        except: pass
                    combined.save(out_path)
                self.finished.emit(out_path)
        except Exception as e:
            self.error.emit(str(e))

class ScannerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Scanner"))
        self.setMinimumWidth(520)
        
        self.settings = QSettings("KPaperFlux", "Scanner")
        self.driver = get_scanner_driver("auto")
        self.scanned_file = None
        self.discovery_running = False
        
        # Resolve icon path relative to project root
        from pathlib import Path
        base_dir = Path(__file__).resolve().parent.parent
        self.icon_path = str(base_dir / "resources" / "images" / "scanner_icon.png")
        
        self._init_ui()
        self._load_saved_settings()
        self._start_discovery()
        
    def _init_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(15)
        
        self.stack = QStackedWidget()
        
        # PAGE 0: LOADING
        self.loading_page = QWidget()
        loading_layout = QVBoxLayout(self.loading_page)
        loading_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if os.path.exists(self.icon_path):
            img = QLabel()
            img.setPixmap(QPixmap(self.icon_path).scaled(100, 100, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            loading_layout.addWidget(img, alignment=Qt.AlignmentFlag.AlignCenter)
        self.loading_label = QLabel(self.tr("Suche nach Scannern..."))
        self.loading_label.setStyleSheet("font-weight: bold; color: #555;")
        loading_layout.addWidget(self.loading_label, alignment=Qt.AlignmentFlag.AlignCenter)
        self.search_progress = QProgressBar()
        self.search_progress.setRange(0, 0)
        self.search_progress.setFixedSize(250, 4)
        loading_layout.addWidget(self.search_progress, alignment=Qt.AlignmentFlag.AlignCenter)
        self.stack.addWidget(self.loading_page)
        
        # PAGE 1: SETTINGS
        self.settings_page = QWidget()
        settings_main_layout = QHBoxLayout(self.settings_page)
        settings_main_layout.setContentsMargins(0, 0, 0, 0)
        
        if os.path.exists(self.icon_path):
            self.side_icon = QLabel()
            self.side_icon.setPixmap(QPixmap(self.icon_path).scaled(90, 90, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            self.side_icon.setStyleSheet("border: 1px solid #ddd; background: white; border-radius: 4px; padding: 5px;")
            self.side_icon.setAlignment(Qt.AlignmentFlag.AlignTop)
            settings_main_layout.addWidget(self.side_icon)
        
        right_panel = QVBoxLayout()
        form = QFormLayout()
        
        # Device selection with Rescan button
        device_layout = QHBoxLayout()
        self.device_combo = QComboBox()
        self.device_combo.setMinimumHeight(30)
        
        self.rescan_btn = QPushButton()
        self.rescan_btn.setToolTip(self.tr("Scannerliste aktualisieren"))
        self.rescan_btn.setFixedSize(30, 30)
        self.rescan_btn.setIcon(self.style().standardIcon(self.style().StandardPixmap.SP_BrowserReload))
        self.rescan_btn.clicked.connect(self.trigger_rescan)
        
        device_layout.addWidget(self.device_combo, 1)
        device_layout.addWidget(self.rescan_btn)
        
        form.addRow(self.tr("Gerät:"), device_layout)
        self.device_combo.currentIndexChanged.connect(self._on_device_changed)
        
        self.source_combo = QComboBox()
        self.source_combo.setMinimumHeight(30)
        self.source_combo.currentIndexChanged.connect(self._on_source_changed)
        form.addRow(self.tr("Quelle:"), self.source_combo)
        
        self.dpi_spin = QSpinBox()
        self.dpi_spin.setRange(75, 1200)
        self.dpi_spin.setValue(200)
        self.dpi_spin.setSuffix(" dpi")
        self.dpi_spin.setMinimumHeight(30)
        form.addRow(self.tr("Auflösung:"), self.dpi_spin)
        
        self.mode_combo = QComboBox()
        self.mode_combo.addItem(self.tr("Farbe"), "Color")
        self.mode_combo.addItem(self.tr("Graustufen"), "Gray")
        self.mode_combo.setMinimumHeight(30)
        form.addRow(self.tr("Modus:"), self.mode_combo)
        
        self.format_combo = QComboBox()
        self.format_combo.addItem(self.tr("A4 (210 x 297 mm)"), "A4")
        self.format_combo.addItem(self.tr("US Letter"), "Letter")
        self.format_combo.addItem(self.tr("US Legal"), "Legal")
        self.format_combo.addItem(self.tr("Maximal"), "Max")
        self.format_combo.setMinimumHeight(30)
        form.addRow(self.tr("Papierformat:"), self.format_combo)
        
        right_panel.addLayout(form)
        
        self.duplex_settings = QFrame()
        self.duplex_settings.setStyleSheet("background-color: #f9f9f9; border: 1px solid #eee; border-radius: 4px;")
        duplex_layout = QFormLayout(self.duplex_settings)
        duplex_layout.setContentsMargins(10, 10, 10, 10)
        self.combo_duplex_mode = QComboBox()
        self.combo_duplex_mode.addItem(self.tr("Lange Seite (Standard)"), "LongEdge")
        self.combo_duplex_mode.addItem(self.tr("Kurze Seite (Umblättern)"), "ShortEdge")
        duplex_layout.addRow(self.tr("Zirkulär:"), self.combo_duplex_mode)
        self.duplex_settings.setVisible(False)
        right_panel.addWidget(self.duplex_settings)
        
        right_panel.addStretch()
        
        settings_main_layout.addLayout(right_panel)
        self.stack.addWidget(self.settings_page)
        self.main_layout.addWidget(self.stack)
        
        self.scan_progress = QProgressBar()
        self.scan_progress.setVisible(False)
        self.main_layout.addWidget(self.scan_progress)
        
        btn_layout = QHBoxLayout()
        self.scan_btn = QPushButton(self.tr("Scan starten"))
        self.scan_btn.setMinimumSize(110, 36)
        self.scan_btn.setEnabled(False)
        self.scan_btn.clicked.connect(self.start_scan)
        self.scan_btn.setDefault(True)
        
        self.cancel_btn = QPushButton(self.tr("Abbrechen"))
        self.cancel_btn.setMinimumSize(90, 36)
        self.cancel_btn.clicked.connect(self.reject)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.scan_btn)
        btn_layout.addWidget(self.cancel_btn)
        self.main_layout.addLayout(btn_layout)

    def _load_saved_settings(self):
        """Restore last used scanner settings."""
        last_dev_id = self.settings.value("last_device_id")
        last_dev_label = self.settings.value("last_device_label")
        
        if last_dev_id:
            # Pre-populate with cached device
            self.device_combo.addItem(last_dev_label, last_dev_id)
            self.scan_btn.setEnabled(True)
            self.stack.setCurrentIndex(1) # Show settings immediately
            
        # Restore other options
        self.dpi_spin.setValue(int(self.settings.value("last_dpi", 200)))
        
        mode = self.settings.value("last_mode", "Color")
        idx = self.mode_combo.findData(mode)
        if idx >= 0: self.mode_combo.setCurrentIndex(idx)
        
        fmt = self.settings.value("last_page_format", "A4")
        idx = self.format_combo.findData(fmt)
        if idx >= 0: self.format_combo.setCurrentIndex(idx)
        
        # We restore source AFTER device is loaded in _on_devices_found
        
        duplex_mode = self.settings.value("last_duplex_mode", "LongEdge")
        idx = self.combo_duplex_mode.findData(duplex_mode)
        if idx >= 0: self.combo_duplex_mode.setCurrentIndex(idx)
        
    def _save_current_settings(self):
        """Persist current scanner settings."""
        device_id = self.device_combo.currentData()
        if device_id:
            self.settings.setValue("last_device_id", device_id)
            self.settings.setValue("last_device_label", self.device_combo.currentText())
        
        self.settings.setValue("last_dpi", self.dpi_spin.value())
        self.settings.setValue("last_mode", self.mode_combo.currentData())
        self.settings.setValue("last_page_format", self.format_combo.currentData())
        self.settings.setValue("last_source", self.source_combo.currentText())
        self.settings.setValue("last_duplex_mode", self.combo_duplex_mode.currentData())

    def _on_device_changed(self, index):
        """Called when user selects another scanner."""
        device_id = self.device_combo.currentData()
        if not device_id: return
        
        # Update sources
        sources = self.driver.get_source_list(device_id)
        self.source_combo.clear()
        self.source_combo.addItems(sources)
        
        # Try to restore last source
        last_src = self.settings.value("last_source")
        if last_src:
             idx = self.source_combo.findText(last_src)
             if idx >= 0: self.source_combo.setCurrentIndex(idx)

    def _on_source_changed(self, index):
        """Update UI based on source (e.g. Duplex options)."""
        src = self.source_combo.currentText()
        is_duplex = any(kw in src for kw in ["Duplex", "Beidseitig", "Zweiseitig"])
        self.duplex_settings.setVisible(is_duplex)
        QTimer.singleShot(50, self.adjustSize)
            
    def _start_discovery(self):
        if self.discovery_running: return
        self.discovery_running = True
        self.discovery_worker = DeviceDiscoveryWorker(self.driver)
        self.discovery_worker.finished.connect(self._on_devices_found)
        self.discovery_worker.error.connect(self._on_discovery_error)
        self.discovery_worker.start()

    def trigger_rescan(self):
        """Manually trigger a full device rescan."""
        self.loading_label.setText(self.tr("Suche nach Scannern..."))
        self.search_progress.setVisible(True)
        self.stack.setCurrentIndex(0) # Back to loading page
        QTimer.singleShot(50, self.adjustSize)
        self._start_discovery()
        
    def _on_devices_found(self, devices):
        print(f"[DEBUG] ScannerDialog received {len(devices)} devices: {devices}")
        self.discovery_running = False
        saved_id = self.settings.value("last_device_id")
        
        self.device_combo.clear()
        if not devices:
            self.device_combo.addItem(self.tr("Keine Geräte gefunden"), None)
            self.loading_label.setText(self.tr("Keine Scanner erkannt."))
            self.search_progress.setVisible(False)
            # We stay in loading view if nothing found during initial scan,
            # or go back to settings if user just wants to see "nothing found".
            if self.stack.currentIndex() == 0:
                 # If we were in settings and rescanned, let's go back and show "nothing"
                 pass
        else:
            selected_idx = 0
            for i, dev in enumerate(devices):
                backend = dev[0].split(":")[0] if ":" in dev[0] else "sane"
                label = f"[{backend}] {dev[1]} {dev[2]}"
                self.device_combo.addItem(label, dev[0])
                if dev[0] == saved_id:
                    selected_idx = i
            
            self.device_combo.setCurrentIndex(selected_idx)
            self.scan_btn.setEnabled(True)
            
            if self.stack.currentIndex() == 0:
                self.stack.setCurrentIndex(1)
                QTimer.singleShot(100, self.adjustSize)
            
    def _on_discovery_error(self, msg):
        self.discovery_running = False
        self.loading_label.setText(self.tr("Fehler bei der Suche"))
        self.search_progress.setVisible(False)
        show_selectable_message_box(self, self.tr("Suche fehlgeschlagen"), msg, icon=QMessageBox.Icon.Warning)
        if self.stack.currentIndex() == 0:
             # Try to show settings anyway if we have cached data
             if self.device_combo.count() > 0:
                  self.stack.setCurrentIndex(1)
        
    def start_scan(self):
        device_id = self.device_combo.currentData()
        if not device_id: return
            
        self._save_current_settings()
        
        self.scan_btn.setEnabled(False)
        self.scan_progress.setVisible(True)
        self.scan_progress.setRange(0, 0)
        
        self.worker = ScannerWorker(
            self.driver, device_id, self.dpi_spin.value(), self.mode_combo.currentData(), 
            self.source_combo.currentText(), self.combo_duplex_mode.currentData(),
            self.format_combo.currentData()
        )
        self.worker.finished.connect(self.on_scan_finished)
        self.worker.error.connect(self.on_scan_error)
        self.worker.progress_update.connect(self.on_progress)
        self.worker.start()
        
    def on_progress(self, current, total):
        if total > 0:
            self.scan_progress.setRange(0, total)
            self.scan_progress.setValue(current)
            self.scan_progress.setFormat(self.tr(f"Scanne Seite {current} von {total}..."))
        else:
            self.scan_progress.setRange(0, 0)
            self.scan_progress.setFormat(self.tr(f"Scanne Seite {current}..."))

    def on_scan_finished(self, path):
        self.scan_progress.setVisible(False)
        self.scanned_file = path
        if os.path.exists(path): self.accept()
        else: self.on_scan_error(self.tr("Datei fehlt."))
            
    def on_scan_error(self, msg):
        self.scan_progress.setVisible(False)
        self.scan_btn.setEnabled(True)
        show_selectable_message_box(self, self.tr("Fehler"), msg, icon=QMessageBox.Icon.Critical)
        
    def get_scanned_file(self) -> Optional[str]:
        return self.scanned_file
