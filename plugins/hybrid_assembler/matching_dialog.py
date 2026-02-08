import os
import glob
import fitz
import cv2
import numpy as np
import json
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog,
    QProgressBar, QCheckBox, QMessageBox, QFrame, QWidget
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSettings
from core.utils.hybrid_engine import HybridEngine

class MatchWorker(QThread):
    progress = pyqtSignal(int, int)
    finished = pyqtSignal(list)
    status_msg = pyqtSignal(str)

    def __init__(self, folder, threshold=15000):
        super().__init__()
        self.folder = folder
        self.threshold = threshold
        self.engine = HybridEngine()

    def run(self):
        files = glob.glob(os.path.join(self.folder, "*.pdf"))
        if not files:
            self.finished.emit([])
            return

        self.status_msg.emit(f"Analyzing {len(files)} files...")
        natives = []
        scans = []

        for i, f in enumerate(files):
            self.progress.emit(i, len(files))
            if self.engine.is_digital_born(f):
                natives.append(f)
            else:
                scans.append(f)

        self.status_msg.emit(f"Found {len(scans)} Scans, {len(natives)} Natives. Matching...")
        
        results = []
        total_matches = len(scans)
        
        for i, scan_file in enumerate(scans):
            self.progress.emit(i, total_matches)
            best_score = float('inf')
            best_native = None
            
            for native_file in natives:
                score = self.engine.calculate_pair_score(scan_file, native_file)
                if score < best_score:
                    best_score = score
                    best_native = native_file
            
            status = "Mismatch"
            if best_native and best_score < self.threshold:
                status = "Match"
            elif best_native:
                status = "Unsure"

            results.append({
                "scan": scan_file,
                "native": best_native,
                "score": best_score,
                "status": status,
                "output_path": None # Added to track assembled files
            })

        self.finished.emit(results)

class MergeWorker(QThread):
    finished = pyqtSignal(bool, str)

    def __init__(self, plugin, native, scan, output):
        super().__init__()
        self.plugin = plugin
        self.native = native
        self.scan = scan
        self.output = output

    def run(self):
        try:
            success = self.plugin.create_hybrid(self.native, self.scan, self.output)
            self.finished.emit(success, self.output)
        except Exception as e:
            self.finished.emit(False, str(e))

class MatchingDialog(QDialog):
    finished_closing = pyqtSignal()

    def __init__(self, parent=None, plugin=None):
        super().__init__(parent)
        self.plugin = plugin
        self.pipeline = None
        if self.plugin and self.plugin.api:
            # Try to get from main_window first
            if hasattr(self.plugin.api, 'main_window') and self.plugin.api.main_window:
                self.pipeline = self.plugin.api.main_window.pipeline
            # Fallback to direct bridge if main_window not fully linked
            if not self.pipeline and hasattr(self.plugin.api, 'pipeline'):
                self.pipeline = self.plugin.api.pipeline

        self.setWindowTitle("Hybrid Matching-Dialog")
        
        # Geometry Persistence
        self.settings = QSettings("KPaperFlux", "MatchingDialog")
        self.restore_geometry()
        
        self.results = []
        
        # Set default folder from config if available
        # Initial folder logic: Settings -> Transfer -> Empty
        self.current_folder = self.settings.value("last_folder", "")
        if not self.current_folder and self.plugin and self.plugin.api and self.plugin.api.config:
            self.current_folder = self.plugin.api.config.get_transfer_path()

        self.__init_ui()

    def restore_geometry(self):
        geom = self.settings.value("geometry")
        if geom:
            self.restoreGeometry(geom)
        else:
            self.setMinimumSize(900, 600)
            self.resize(1000, 700)

    def closeEvent(self, event):
        self.settings.setValue("geometry", self.saveGeometry())
        # Store current folder if set
        if self.current_folder:
            self.settings.setValue("last_folder", self.current_folder)
        self.finished_closing.emit()
        super().closeEvent(event)

    def __init_ui(self):
        layout = QVBoxLayout(self)

        # Header / Description
        header = QLabel("<b>Hybrid Matching-Dialog</b><br>Finds pairs of scanned and native PDFs in a folder to merge them.")
        header.setStyleSheet("font-size: 14px;")
        layout.addWidget(header)

        # Folder Selection
        folder_layout = QHBoxLayout()
        self.lbl_folder = QLabel(self.current_folder if self.current_folder else "No folder selected.")
        btn_browse = QPushButton("Browse Folder...")
        btn_browse.clicked.connect(self.on_browse)
        folder_layout.addWidget(self.lbl_folder, 1)
        folder_layout.addWidget(btn_browse)
        layout.addLayout(folder_layout)

        # Options
        options_layout = QHBoxLayout()
        self.chk_delete_originals = QCheckBox("Delete original files after successful merge")
        options_layout.addWidget(self.chk_delete_originals)
        layout.addLayout(options_layout)

        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        self.lbl_status = QLabel("")
        layout.addWidget(self.lbl_status)

        # Results Table
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Scan File", "Best Native Match", "Score", "Status", "Actions"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

        # Actions
        btn_layout = QHBoxLayout()
        self.btn_scan = QPushButton("Start Analysis")
        self.btn_scan.clicked.connect(self.start_analysis)
        self.btn_scan.setStyleSheet("font-weight: bold; padding: 8px;")
        
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.close)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_scan)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

    def on_browse(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder to Scan")
        if folder:
            self.lbl_folder.setText(folder)
            self.current_folder = folder

    def start_analysis(self):
        if not hasattr(self, 'current_folder') or not os.path.exists(self.current_folder):
            QMessageBox.warning(self, "Error", "Please select a valid folder first.")
            return

        self.btn_scan.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.table.setRowCount(0)
        
        self.worker = MatchWorker(self.current_folder)
        self.worker.progress.connect(self.on_progress)
        self.worker.status_msg.connect(self.lbl_status.setText)
        self.worker.finished.connect(self.on_finished)
        self.worker.start()

    def on_progress(self, current, total):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)

    def on_finished(self, results):
        self.results = results
        self.btn_scan.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.lbl_status.setText(f"Analysis complete. Found {len(results)} potential scans.")
        self.populate_table()

    def populate_table(self):
        self.table.setRowCount(len(self.results))
        for i, res in enumerate(self.results):
            scan_name = os.path.basename(res["scan"])
            native_name = os.path.basename(res["native"]) if res["native"] else "-"
            
            self.table.setItem(i, 0, QTableWidgetItem(scan_name))
            self.table.setItem(i, 1, QTableWidgetItem(native_name))
            
            score_item = QTableWidgetItem(str(int(res["score"]) if res["score"] != float('inf') else "∞"))
            self.table.setItem(i, 2, score_item)
            
            status_text = res["status"]
            if res.get("output_path"):
                status_text = "Assembled"
                
            status_item = QTableWidgetItem(status_text)
            if status_text == "Match" or status_text == "Assembled":
                status_item.setForeground(Qt.GlobalColor.green if status_text == "Match" else Qt.GlobalColor.blue)
            elif status_text == "Unsure":
                status_item.setForeground(Qt.GlobalColor.darkYellow)
            self.table.setItem(i, 3, status_item)

            # Actions cell
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(2, 2, 2, 2)
            
            if res.get("output_path"):
                btn_view_res = QPushButton("View Result")
                btn_view_res.clicked.connect(lambda checked, r=res: self.on_view_result(r))
                btn_import = QPushButton("Import")
                btn_import.setStyleSheet("font-weight: bold; color: #2e7d32;")
                btn_import.clicked.connect(lambda checked, r=res: self.on_import_result(r))
                actions_layout.addWidget(btn_view_res)
                actions_layout.addWidget(btn_import)
            else:
                btn_view = QPushButton("View")
                btn_view.setToolTip("Side-by-side comparison")
                btn_view.clicked.connect(lambda checked, r=res: self.on_view(r))
                
                btn_merge = QPushButton("Merge")
                btn_merge.setEnabled(res["status"] != "Mismatch")
                btn_merge.clicked.connect(lambda checked, r=res: self.on_merge(r))
                
                actions_layout.addWidget(btn_view)
                actions_layout.addWidget(btn_merge)
            self.table.setCellWidget(i, 4, actions_widget)

    def on_view(self, res):
        from gui.comparison_dialog import ComparisonDialog
        if not res["native"] or not res["scan"]:
            return
            
        dlg = ComparisonDialog(self)
        dlg.load_comparison(res["native"], res["scan"])
        dlg.exec()

    def on_merge(self, res):
        if not res["native"] or not res["scan"]:
            return
            
        # Determine starting folder for save dialog
        last_save_dir = self.settings.value("last_save_dir", "")
        if not last_save_dir and self.plugin and self.plugin.api and self.plugin.api.config:
            last_save_dir = self.plugin.api.config.get_transfer_path()
        
        # Ask for output location
        out_name = os.path.basename(res["native"]).replace(".pdf", "_hybrid.pdf")
        initial_path = os.path.join(last_save_dir, out_name) if last_save_dir else out_name
        
        out_path, _ = QFileDialog.getSaveFileName(
            self, "Save Hybrid PDF", initial_path, "PDF Files (*.pdf)"
        )
        
        if out_path:
            # Store the directory for next time
            save_dir = os.path.dirname(out_path)
            self.settings.setValue("last_save_dir", save_dir)
            
            # Disable UI and show status
            self.btn_scan.setEnabled(False)
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 0) # Pulsing progress
            self.lbl_status.setText(f"Creating Hybrid PDF: {os.path.basename(out_path)}...")
            self.table.setEnabled(False)
            
            self.merge_worker = MergeWorker(self.plugin, res["native"], res["scan"], out_path)
            self.merge_worker.finished.connect(lambda s, p, r=res: self.on_merge_finished(s, p, r))
            self.merge_worker.start()

    def on_merge_finished(self, success, out_path, res):
        self.btn_scan.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.table.setEnabled(True)
        self.lbl_status.setText("Merge complete.")
        
        if success:
            res["output_path"] = out_path # Mark as assembled
            self.populate_table() # Refresh UI
            
            QMessageBox.information(self, "Success", f"Hybrid PDF created successfully:\n{out_path}")
            if self.chk_delete_originals.isChecked():
                try:
                    os.remove(res["scan"])
                    os.remove(res["native"])
                    # We don't refresh all (start_analysis) because we want to keep the state in the table
                except Exception as e:
                    print(f"Error deleting originals: {e}")
        else:
            QMessageBox.critical(self, "Error", f"Failed to create hybrid PDF: {out_path}")

    def on_view_result(self, res):
        """Shows the generated hybrid PDF in the internal viewer."""
        from gui.pdf_viewer import DualPdfViewerWidget
        path = res.get("output_path")
        if path and os.path.exists(path):
            # For simplicity, we can use the ComparisonDialog or a separate view.
            # Here we just open the single file in a ComparisonDialog but with the same path left/right
            # Or better: Add a single-view method.
            from gui.comparison_dialog import ComparisonDialog
            dlg = ComparisonDialog(self)
            dlg.setWindowTitle(f"Preview: {os.path.basename(path)}")
            # Just load it on both sides to use the existing UI
            dlg.load_comparison(path, path)
            dlg.exec()

    def on_import_result(self, res):
        """Imports the generated hybrid PDF using the standard application import flow."""
        path = res.get("output_path")
        if not path or not os.path.exists(path):
            return
            
        main_win = None
        if self.plugin and self.plugin.api and self.plugin.api.main_window:
            main_win = self.plugin.api.main_window
            
        if main_win:
            # Use the standard import UI flow
            main_win.handle_dropped_files([str(path)])
            
            # Since the import happens in the background/async in the worker, 
            # we just visually update the list to show we triggered it.
            res["status"] = "Sent to Import"
            self.populate_table()
        else:
            QMessageBox.warning(self, "Import Error", "Main window not available for standard import.")
