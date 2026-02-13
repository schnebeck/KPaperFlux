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
    match_found = pyqtSignal(dict) # New: Emit each result as it is ready

    def __init__(self, folder, threshold=15000):
        super().__init__()
        self.folder = folder
        self.threshold = threshold
        self.engine = HybridEngine()
        self._is_cancelled = False

    def run(self):
        files = glob.glob(os.path.join(self.folder, "*.pdf"))
        if not files:
            self.finished.emit([])
            return

        self.status_msg.emit(f"Analyzing {len(files)} files...")
        natives_paths = []
        scans_paths = []

        for f in files:
            if self.engine.is_digital_born(f):
                natives_paths.append(f)
            else:
                scans_paths.append(f)

        # 1. TWO-STAGE PARALLEL CACHING
        self.status_msg.emit("Two-Stage Data Preparation (100/150 DPI)...")
        cache_100 = {}
        cache_150 = {}
        
        def render_file(p):
            try:
                doc = fitz.open(p)
                cache_100[p] = self.engine.pdf_page_to_numpy(doc, 0, dpi=100)
                cache_150[p] = self.engine.pdf_page_to_numpy(doc, 0, dpi=150)
                doc.close()
            except: pass

        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=4) as executor:
            # Check cancellation before starting heavy load
            if self._is_cancelled: return
            executor.map(render_file, natives_paths + scans_paths)

        self.status_msg.emit(f"Matching {len(scans_paths)} Scans (Smart Two-Stage)...")
        results = []
        available_natives = list(natives_paths)
        
        # Thresholds
        GREEDY_LIMIT_100 = 250  # Score threshold for 100 DPI (Confidence)
        REFINEMENT_COUNT = 3   # How many top candidates to check at 150 DPI

        for i, scan_file in enumerate(scans_paths):
            if self._is_cancelled: break
            self.progress.emit(i, len(scans_paths))
            scan_img_100 = cache_100.get(scan_file)
            if scan_img_100 is None: continue

            # --- STAGE 1: Fingerprinting (100 DPI) ---
            candidates = []
            for native_file in available_natives:
                score = self.engine.calculate_pair_score(
                    scan_file, native_file, 
                    native_img_cached=cache_100.get(native_file),
                    scan_img_cached=scan_img_100,
                    dpi=100
                )
                candidates.append((native_file, score))
            
            candidates.sort(key=lambda x: x[1])
            best_native, best_score = candidates[0]
            
            # --- STAGE 2: High-Precision Refinement (150 DPI) ---
            # Refining is needed if the gap to the next candidate is not large enough
            # OR if the score is not perfectly 'confident'
            needs_refinement = True
            if best_score < 100: # Very high confidence already
                if len(candidates) > 1 and candidates[1][1] > best_score * 5:
                    needs_refinement = False

            if needs_refinement:
                print(f"[DEBUG] Scan {os.path.basename(scan_file)}: Triggering 150 DPI Refinement (Stage 1 Best: {int(best_score)})")
                scan_img_150 = cache_150.get(scan_file)
                final_candidates = []
                for native_file, _ in candidates[:REFINEMENT_COUNT]:
                    precision_score = self.engine.calculate_pair_score(
                        scan_file, native_file,
                        native_img_cached=cache_150.get(native_file),
                        scan_img_cached=scan_img_150,
                        dpi=150
                    )
                    final_candidates.append((native_file, precision_score))
                
                final_candidates.sort(key=lambda x: x[1])
                best_native, best_score = final_candidates[0]
                print(f"[DEBUG] -> Stage 2 Final: {os.path.basename(best_native)} with Score {int(best_score)}")
            else:
                print(f"[DEBUG] Scan {os.path.basename(scan_file)}: Finalized at 100 DPI (Confident Match, Score: {int(best_score)})")

            # Pool management & Decision
            status = "Mismatch"
            # 1000 is a reasonable cutoff for ANY match (10% diff)
            if best_native and best_score < 1000: 
                status = "Match"
                # Pool reduction: Only remove if we are REALLY sure
                if best_score < GREEDY_LIMIT_100:
                    available_natives.remove(best_native)
            elif best_native:
                status = "Unsure"

            res = {
                "scan": scan_file, "native": best_native,
                "score": best_score, "status": status, "output_path": None
            }
            results.append(res)
            self.match_found.emit(res) # STREAMING: Send result immediately to GUI

        self.finished.emit(results)

class MergeWorker(QThread):
    finished = pyqtSignal(bool, str)

    def __init__(self, plugin, native, scan, output):
        super().__init__()
        self.plugin = plugin
        self.native = native
        self.scan = scan
        self.output = output
        self._is_cancelled = False

    def run(self):
        if self._is_cancelled: return
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
        """Cleanup on close: stop all threads and batch processes."""
        print("[Hybrid] Closing dialog. Cleaning up processes...")
        
        # 1. Stop MatchWorker
        if hasattr(self, 'worker') and self.worker.isRunning():
            self.worker._is_cancelled = True
            self.worker.quit()
            self.worker.wait(500) # Give it 500ms to exit gracefully
            if self.worker.isRunning():
                self.worker.terminate()
        
        # 2. Stop Merge Queue
        self._merge_queue = []
        self._is_batch_merging = False
        
        # 3. Stop MergeWorker
        if hasattr(self, 'merge_worker') and self.merge_worker.isRunning():
            self.merge_worker._is_cancelled = True
            self.merge_worker.quit()
            self.merge_worker.wait(500)
            if self.merge_worker.isRunning():
                self.merge_worker.terminate()

        # 4. Persistence
        self.settings.setValue("geometry", self.saveGeometry())
        if hasattr(self, 'current_folder') and self.current_folder:
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
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Scan File", "Best Native Match", "Status", "Actions"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

        # Actions
        btn_layout = QHBoxLayout()
        
        # Primary Action Button (Smart Workflow Button)
        self.btn_primary_action = QPushButton("Start Analysis")
        self.btn_primary_action.setToolTip("Start scanning folder or process results")
        self.btn_primary_action.setEnabled(True)
        self.btn_primary_action.clicked.connect(self.on_primary_action)
        self.btn_primary_action.setStyleSheet("min-width: 180px; padding: 8px; font-weight: bold;")
        
        common_style = "min-width: 100px; padding: 6px;"
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.close)
        btn_close.setStyleSheet(common_style)
        
        btn_layout.addWidget(self.btn_primary_action)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)
        
        # Internal state for workflow management
        self._merge_queue = []
        self._is_batch_merging = False
        self._is_analyzing = False
        self._current_mode = "SCAN"

    def on_browse(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder to Scan")
        if folder:
            self.lbl_folder.setText(folder)
            self.current_folder = folder

    def start_analysis(self):
        if not hasattr(self, 'current_folder') or not os.path.exists(self.current_folder):
            QMessageBox.warning(self, "Error", "Please select a valid folder first.")
            return

        self._is_analyzing = True
        self.update_button_states()
        self.progress_bar.setVisible(True)
        self.results = [] # Clear previous
        self.worker = MatchWorker(self.current_folder)
        self.worker.progress.connect(self.on_progress)
        self.worker.status_msg.connect(self.lbl_status.setText)
        self.worker.match_found.connect(self.on_match_found) # REAL-TIME STREAMING
        self.worker.finished.connect(self.on_finished)
        self.worker.start()

    def on_progress(self, current, total):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)

    def on_match_found(self, res):
        self.results.append(res)
        self.populate_table()

    def on_finished(self, results):
        self.results = results
        self._is_analyzing = False
        self.progress_bar.setVisible(False)
        self.lbl_status.setText(f"Analysis complete. Found {len(results)} potential scans.")
        self.populate_table()
        self.update_button_states()

    def populate_table(self):
        self.table.setRowCount(len(self.results))
        for i, res in enumerate(self.results):
            scan_name = os.path.basename(res["scan"])
            native_name = os.path.basename(res["native"]) if res["native"] else "-"
            
            self.table.setItem(i, 0, QTableWidgetItem(scan_name))
            self.table.setItem(i, 1, QTableWidgetItem(native_name))
            
            status_text = res["status"]
            if res.get("output_path") and res.get("status") != "Imported":
                status_text = "Assembled"
                
            status_item = QTableWidgetItem(status_text)
            
            # Reset colors if already processed or in progress
            if status_text in ["Assembled", "Imported", "Merging..."]:
                # Default colors
                pass
            elif res.get("verified") is True:
                status_item.setText(f"✓ {status_text}")
                status_item.setForeground(Qt.GlobalColor.green)
            elif res.get("verified") is False:
                status_item.setText(f"✗ {status_text}")
                status_item.setForeground(Qt.GlobalColor.red)
            elif status_text == "Match":
                status_item.setForeground(Qt.GlobalColor.green)
            elif status_text == "Unsure":
                status_item.setForeground(Qt.GlobalColor.darkYellow)
            
            self.table.setItem(i, 2, status_item)

            # Actions cell
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(4, 2, 4, 2)
            actions_layout.setSpacing(5)
            
            btn_style = "min-width: 85px;"

            if res.get("output_path") and res.get("status") != "Imported":
                btn_view_res = QPushButton("View")
                btn_view_res.setStyleSheet(btn_style)
                btn_view_res.clicked.connect(lambda checked, r=res: self.on_view_result(r))
                btn_import = QPushButton("Import")
                btn_import.setStyleSheet(btn_style + " font-weight: bold; color: #2e7d32;")
                btn_import.clicked.connect(lambda checked, r=res: self.on_import_result(r))
                actions_layout.addWidget(btn_view_res)
                actions_layout.addWidget(btn_import)
            elif res.get("status") == "Imported":
                lbl_imported = QLabel("Imported ✓")
                lbl_imported.setAlignment(Qt.AlignmentFlag.AlignCenter)
                actions_layout.addWidget(lbl_imported)
            else:
                btn_view = QPushButton("Verify")
                btn_view.setStyleSheet(btn_style)
                btn_view.setToolTip("Side-by-side comparison and verification")
                btn_view.clicked.connect(lambda checked, r=res: self.on_view(r))
                
                btn_merge = QPushButton("Merge")
                btn_merge.setStyleSheet(btn_style)
                btn_merge.setEnabled(res["status"] != "Mismatch" or res.get("verified") is True)
                btn_merge.clicked.connect(lambda checked, r=res: self.on_merge(r))
                
                actions_layout.addWidget(btn_view)
                actions_layout.addWidget(btn_merge)
            self.table.setCellWidget(i, 3, actions_widget)
        
        self.update_button_states()

    def update_button_states(self):
        """Enable/Disable primary action button based on workflow state."""
        if self._is_analyzing:
            self.btn_primary_action.setText("Analyzing...")
            self.btn_primary_action.setEnabled(False)
            return

        mergeable = [r for r in self.results if not r.get("output_path") and (r["status"] == "Match" or r.get("verified") is True)]
        importable = [r for r in self.results if r.get("output_path") and r.get("status") != "Imported"]
        
        if len(mergeable) >= 2:
            self.btn_primary_action.setText("Merge Matched")
            self.btn_primary_action.setEnabled(True)
            self._current_mode = "MERGE"
        elif len(importable) >= 2:
            self.btn_primary_action.setText("Import Merged")
            self.btn_primary_action.setEnabled(True)
            self._current_mode = "IMPORT"
        else:
            self.btn_primary_action.setText("Start Analysis")
            self.btn_primary_action.setEnabled(True)
            self._current_mode = "SCAN"

    def on_primary_action(self):
        """Dispatches action based on the current smart-button mode."""
        if self._current_mode == "SCAN":
            self.start_analysis()
        elif self._current_mode == "MERGE":
            self.on_merge_all()
        elif self._current_mode == "IMPORT":
            self.on_import_all()

    def on_view(self, res):
        from gui.comparison_dialog import ComparisonDialog
        if not res["native"] or not res["scan"]:
            return
            
        dlg = ComparisonDialog(self)
        dlg.load_comparison(res["native"], res["scan"])
        # Connect the assessment signal
        dlg.match_assessed.connect(lambda is_correct: self.on_match_assessed(res, is_correct))
        dlg.exec()

    def on_match_assessed(self, res, is_correct):
        """Callback for user decision in ComparisonDialog."""
        res["verified"] = is_correct
        if is_correct:
            res["status"] = "Match"
        else:
            res["status"] = "Mismatch"
        self.populate_table()

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
            self._process_merge(res, out_path)

    def _process_merge(self, res, out_path):
        """Internal helper to start a single merge."""
        # Store the directory for next time
        save_dir = os.path.dirname(out_path)
        self.settings.setValue("last_save_dir", save_dir)
        
        # Disable UI and show status
        self.btn_primary_action.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0) # Pulsing progress
        self.lbl_status.setText(f"Creating Hybrid PDF: {os.path.basename(out_path)}...")
        self.table.setEnabled(False)
        
        res["status"] = "Merging..."
        self.populate_table()
        
        self.merge_worker = MergeWorker(self.plugin, res["native"], res["scan"], out_path)
        self.merge_worker.finished.connect(lambda s, p, r=res: self.on_merge_finished(s, p, r))
        self.merge_worker.start()

    def on_merge_all(self):
        """Batch merge all confident/verified matches."""
        pending = [r for r in self.results if not r.get("output_path") and (r["status"] == "Match" or r.get("verified") is True)]
        if not pending:
            QMessageBox.information(self, "Batch Merge", "No pending matches found to merge.")
            return
            
        # Ask for output folder once
        last_save_dir = self.settings.value("last_save_dir", "")
        out_dir = QFileDialog.getExistingDirectory(self, "Select Output Folder for Hybrid PDFs", last_save_dir)
        
        if out_dir:
            self.settings.setValue("last_save_dir", out_dir)
            self._merge_queue = []
            for res in pending:
                out_name = os.path.basename(res["native"]).replace(".pdf", "_hybrid.pdf")
                out_path = os.path.join(out_dir, out_name)
                self._merge_queue.append((res, out_path))
            
            self._is_batch_merging = True
            self._process_next_batch_merge()

    def _process_next_batch_merge(self):
        if not self._merge_queue:
            self._is_batch_merging = False
            self.table.setEnabled(True)
            self.update_button_states() # Refresh button text/state
            self.progress_bar.setVisible(False)
            self.lbl_status.setText("Batch merge complete.")
            return

        res, out_path = self._merge_queue.pop(0)
        self._process_merge(res, out_path)

    def on_merge_finished(self, success, out_path, res):
        if not self._is_batch_merging:
            self.progress_bar.setVisible(False)
            self.table.setEnabled(True)
            self.update_button_states()
            
        if success:
            res["output_path"] = out_path
            self.lbl_status.setText(f"Merge success: {os.path.basename(out_path)}")
            if self.chk_delete_originals.isChecked():
                try:
                    os.remove(res["scan"])
                    os.remove(res["native"])
                except: pass
        else:
            QMessageBox.warning(self, "Error", f"Failed to merge: {os.path.basename(out_path)}")

        self.populate_table()
        
        if self._is_batch_merging:
            self._process_next_batch_merge()
        elif success:
            QMessageBox.information(self, "Success", f"Hybrid PDF created:\n{out_path}")

    def on_import_all(self):
        """Import all assembled PDFs in one go."""
        importable = [r for r in self.results if r.get("output_path")]
        if not importable:
            QMessageBox.information(self, "Import All", "No assembled documents found to import.")
            return
            
        count = 0
        for res in importable:
            self.on_import_result(res)
            count += 1
            
        QMessageBox.information(self, "Import All", f"Triggered import for {count} documents.")

    def on_view_result(self, res):
        """Shows the generated hybrid PDF in the internal viewer."""
        from gui.comparison_dialog import ComparisonDialog
        path = res.get("output_path")
        if path and os.path.exists(path):
            dlg = ComparisonDialog(self)
            dlg.setWindowTitle(f"Preview: {os.path.basename(path)}")
            dlg.load_comparison(path, path)
            dlg.exec()

    def on_import_result(self, res):
        """Imports the generated hybrid PDF using the standard application import flow."""
        path = res.get("output_path")
        if not path or not os.path.exists(path):
            return
            
        main_win = getattr(self.plugin.api, 'main_window', None) if self.plugin and self.plugin.api else None
            
        if main_win:
            main_win.handle_dropped_files([str(path)])
            res["status"] = "Imported"
            self.populate_table()
        else:
            QMessageBox.warning(self, "Import Error", "Main window not available for standard import.")
