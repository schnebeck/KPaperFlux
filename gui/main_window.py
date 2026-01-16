from typing import Optional
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFileDialog, 
    QMessageBox, QSplitter, QMenuBar, QMenu, QCheckBox, QDialog, QDialogButtonBox, QStatusBar
)
from PyQt6.QtGui import QAction, QIcon, QDragEnterEvent, QDropEvent, QCloseEvent
from PyQt6.QtCore import Qt
import sys
import platform
import os
import PyQt6.QtCore
import shutil
from core.pipeline import PipelineProcessor
from core.database import DatabaseManager
from core.stamper import DocumentStamper
from gui.document_list import DocumentListWidget
from core.stamper import DocumentStamper
from gui.document_list import DocumentListWidget
from gui.metadata_editor import MetadataEditorWidget
from gui.pdf_viewer import PdfViewerWidget
from gui.filter_widget import FilterWidget
from gui.settings_dialog import SettingsDialog
from gui.filter_widget import FilterWidget
from gui.settings_dialog import SettingsDialog

class MainWindow(QMainWindow):
    """
    Main application window for KPaperFlux.
    """
    def __init__(self, pipeline: Optional[PipelineProcessor] = None, db_manager: Optional[DatabaseManager] = None):
        super().__init__()
        self.pipeline = pipeline
        self.db_manager = db_manager
        
        # If pipeline is provided but db_manager checks, try to extract db from pipeline
        if self.pipeline and not self.db_manager:
            self.db_manager = self.pipeline.db

        self.setWindowTitle(self.tr("KPaperFlux"))
        self.setWindowIcon(QIcon("resources/icon.png"))
        self.resize(1000, 700)
        self.setAcceptDrops(True)
        
        self.create_menu_bar()
        
        # Central Widget & Main Layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Main Splitter (Left Pane | Right Pane)
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.main_splitter)
        
        # --- Left Pane (Filter | List | Editor) ---
        self.left_pane_splitter = QSplitter(Qt.Orientation.Vertical)
        
        # 1. Filter (Fixed/Small)
        # Note: Splitter usually takes widgets directly.
        # But FilterWidget might need a container or simply add it.
        self.filter_widget = FilterWidget()
        self.left_pane_splitter.addWidget(self.filter_widget)
        
        # 2. Document List
        if self.db_manager:
            self.list_widget = DocumentListWidget(self.db_manager)
            self.list_widget.document_selected.connect(self.on_document_selected)
            self.list_widget.delete_requested.connect(self.delete_document_slot)
            self.list_widget.reprocess_requested.connect(self.reprocess_document_slot)
            self.list_widget.merge_requested.connect(self.merge_documents_slot)
            self.list_widget.export_requested.connect(self.export_documents_slot)
            self.list_widget.stamp_requested.connect(self.stamp_document_slot)
            self.list_widget.tags_update_requested.connect(self.manage_tags_slot)
            self.list_widget.document_count_changed.connect(self.update_status_bar)
            
            # Connect Filter
            self.filter_widget.filter_changed.connect(self.list_widget.apply_filter)
            
            self.left_pane_splitter.addWidget(self.list_widget)
            self.list_widget.refresh_list()
        else:
            self.list_widget = QWidget() # Placeholder
            self.left_pane_splitter.addWidget(self.list_widget)
            
        # 3. Metadata Editor
        self.editor_widget = MetadataEditorWidget(self.db_manager)
        self.editor_widget.metadata_saved.connect(self.list_widget.refresh_list)
        self.left_pane_splitter.addWidget(self.editor_widget)
        
        # Add Left Pane to Main Splitter
        self.main_splitter.addWidget(self.left_pane_splitter)
        
        # --- Right Pane (PDF Viewer) ---
        self.pdf_viewer = PdfViewerWidget()
        self.pdf_viewer.stamp_requested.connect(self.stamp_document_slot)
        self.pdf_viewer.tags_update_requested.connect(self.manage_tags_slot)
        self.pdf_viewer.export_requested.connect(self.export_documents_slot)
        self.pdf_viewer.reprocess_requested.connect(self.reprocess_document_slot)
        self.pdf_viewer.delete_requested.connect(self.delete_document_slot)
        self.main_splitter.addWidget(self.pdf_viewer)
        
        # Set Initial Sizes
        # Left Pane: 10% Filter, 60% List, 30% Editor
        # Height ratio. QSplitter uses pixels or absolute sizes initially.
        # Let's assume height 700. Filter ~70, List ~420, Editor ~210.
        self.left_pane_splitter.setSizes([70, 420, 210])
        self.left_pane_splitter.setCollapsible(0, False) # Keep filter visible
        
        # Main Splitter: Left 40%, Right 60%
        # Width 1000. Left 400, Right 600.
        # Main Splitter: Left 40%, Right 60%
        # Width 1000. Left 400, Right 600.
        self.main_splitter.setSizes([400, 600])

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage(self.tr("Ready"))

    def create_menu_bar(self):
        menubar = self.menuBar()
        
        # -- File Menu --
        file_menu = menubar.addMenu(self.tr("&File"))
        
        action_import = QAction(self.tr("&Import Document"), self)
        action_import.setShortcut("Ctrl+O")
        action_import.triggered.connect(self.import_document_slot)
        file_menu.addAction(action_import)
        
        action_scan = QAction(self.tr("&Scan..."), self)
        action_scan.setShortcut("Ctrl+S")
        action_scan.triggered.connect(self.open_scanner_slot)
        # action_scan.setEnabled(False) # Now enabled
        file_menu.addAction(action_scan)
        
        action_print = QAction(self.tr("&Print"), self)
        action_print.setShortcut("Ctrl+P")
        action_print.setEnabled(False) # Placeholder
        file_menu.addAction(action_print)
        
        file_menu.addSeparator()
        
        action_delete = QAction(self.tr("&Delete Selected"), self)
        action_delete.setShortcut("Del")
        action_delete.triggered.connect(self.delete_selected_slot)
        file_menu.addAction(action_delete)
        
        file_menu.addSeparator()
        
        action_exit = QAction(self.tr("E&xit"), self)
        action_exit.setShortcut("Ctrl+Q")
        action_exit.triggered.connect(self.close)
        file_menu.addAction(action_exit)
        
        # -- View Menu --
        view_menu = menubar.addMenu(self.tr("&View"))
        
        action_refresh = QAction(self.tr("&Refresh List"), self)
        action_refresh.setShortcut("F5")
        action_refresh.triggered.connect(self.refresh_list_slot)
        view_menu.addAction(action_refresh)
        
        action_extra = QAction(self.tr("Show Extra Data"), self)
        action_extra.setShortcut("Ctrl+E")
        action_extra.setCheckable(True)
        action_extra.setChecked(True) # Default Checked?
        action_extra.triggered.connect(self.toggle_editor_visibility)
        view_menu.addAction(action_extra)
        
        # -- Maintenance Menu --
        maintenance_menu = menubar.addMenu(self.tr("&Maintenance"))
        
        orphans_action = QAction(self.tr("Check Integrity (Orphans/Ghosts)"), self)
        orphans_action.triggered.connect(self.open_maintenance_slot)
        maintenance_menu.addAction(orphans_action)
        
        duplicates_action = QAction(self.tr("Find Duplicates"), self)
        duplicates_action.triggered.connect(self.find_duplicates_slot)
        maintenance_menu.addAction(duplicates_action)

        # -- Config Menu --
        config_menu = menubar.addMenu(self.tr("&Config"))
        
        action_settings = QAction(self.tr("&Settings..."), self)
        action_settings.triggered.connect(self.open_settings_slot)
        config_menu.addAction(action_settings)
        
        # -- Help Menu --
        help_menu = menubar.addMenu(self.tr("&Help"))
        
        action_about = QAction(self.tr("&About"), self)
        action_about.triggered.connect(self.show_about_dialog)
        help_menu.addAction(action_about)

    def on_document_selected(self, uuids: list):
        """Handle document selection (single or batch)."""
        if not self.db_manager or not uuids:
            self.editor_widget.clear()
            self.pdf_viewer.clear()
            return

        docs = []
        for uuid in uuids:
            d = self.db_manager.get_document_by_uuid(uuid)
            if d: docs.append(d)
            
        if not docs:
             self.editor_widget.clear()
             self.pdf_viewer.clear()
             return
             
        # Update Editor (Batch aware)
        self.editor_widget.display_documents(docs)
        
        # Update PDF Viewer
        # If single, show it. If multiple, show first? Or show simple "Multiple Selected" message?
        # Viewer usually only supports one file.
        if len(docs) == 1:
            if self.pipeline and self.pipeline.vault:
                path = self.pipeline.vault.get_file_path(docs[0].uuid)
                if path:
                    self.pdf_viewer.load_document(path, uuid=docs[0].uuid)
                else:
                     self.pdf_viewer.clear()
        else:
            # Maybe clear viewer or show placeholder?
            # self.pdf_viewer.clear() 
            # Or just keep showing the last one (confusing).
            # Best: Show first one but indicate multiple?
            # Let's clear for clarity or show the first one to allow "comparison"?
            # User wants to batch edit metadata. 
            # If viewer shows Doc A, and user edits "Sender" -> applies to A, B, C.
            # It's fine to show Doc A as reference.
            if self.pipeline and self.pipeline.vault:
                path = self.pipeline.vault.get_file_path(docs[0].uuid)
                if path: self.pdf_viewer.load_document(path, uuid=docs[0].uuid)

    def delete_selected_slot(self):
        """Handle deletion via Menu."""
        # Logic to get selected item from list widget needs to be exposed
        # For now, simplistic approach: check if list has connection, or if we can track current selection
        QMessageBox.information(self, self.tr("Info"), self.tr("Please use the context menu on the list to delete specific items."))

    def delete_document_slot(self, uuid: str):
        """Handle delete request from List."""
        # Confirm deletion
        reply = QMessageBox.question(self, self.tr("Confirm Delete"), 
                                   self.tr("Are you sure you want to delete this document?"),
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            if self.db_manager and self.pipeline:
                doc = self.db_manager.get_document_by_uuid(uuid)
                if doc:
                    self.pipeline.vault.delete_document(doc)
                    self.db_manager.delete_document(uuid)
                    
                    self.list_widget.refresh_list()
                    self.editor_widget.clear()
                    self.pdf_viewer.clear()
                    
    def reprocess_document_slot(self, uuids: list):
        """Re-run pipeline for list of documents."""
        if not self.pipeline:
            return
            
        success_count = 0
        from PyQt6.QtWidgets import QProgressDialog
        
        count = len(uuids)
        if count == 0: return

        progress = QProgressDialog(self.tr("Reprocessing..."), self.tr("Cancel"), 0, count, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0) # Show immediately
        progress.forceShow() # Ensure visibility
        progress.setValue(0)
        
        # Ensure it paints
        from PyQt6.QtCore import QCoreApplication
        QCoreApplication.processEvents()

        # Loop
        # Worker Setup
        from gui.workers import ReprocessWorker
        
        # Disable main window interaction? Or just modal dialog.
        # Dialog is already modal.
        
        uuid_to_restore = None
        if self.pdf_viewer and self.pdf_viewer.current_uuid in uuids:
             uuid_to_restore = self.pdf_viewer.current_uuid
             self.pdf_viewer.unload()
             
        self.reprocess_worker = ReprocessWorker(self.pipeline, uuids)
        
        # Connect Signals
        self.reprocess_worker.progress.connect(
            lambda i, uid: (
                progress.setLabelText(self.tr(f"Reprocessing {i+1} of {count}...")),
                progress.setValue(i)
            )
        )
        
        # Capture UUID to restore if any
        # We assume self.pdf_viewer.current_uuid was just unloaded so it's None NOW if we called unload.
        # But we called unload above.
        # So we need to capture it BEFORE unload.
        # Wait, I need to restructure the slot to capture it before unload.
        # See correction below (I will use a local var captured in closure).
        
        self.reprocess_worker.finished.connect(
            lambda success, total, processed_uuids: self._on_reprocess_finished(success, total, processed_uuids, uuids, progress, uuid_to_restore)
        )
        
        progress.canceled.connect(self.reprocess_worker.cancel)
        
        self.reprocess_worker.start()

    def _on_reprocess_finished(self, success_count, total, processed_uuids, original_uuids, progress_dialog, uuid_to_restore=None):
        progress_dialog.close()
        self.reprocess_worker = None # Cleanup ref
        
        # Refresh Editor logic
        if self.editor_widget:
            intersect = set(processed_uuids) & set(self.editor_widget.current_uuids)
            if intersect:
                 docs_to_refresh = []
                 for uid in self.editor_widget.current_uuids:
                     d = self.db_manager.get_document_by_uuid(uid)
                     if d: docs_to_refresh.append(d)
                 if docs_to_refresh:
                     self.editor_widget.display_documents(docs_to_refresh)
                     
        # Reload PDF Viewer if active document was reprocessed
        if self.pdf_viewer and uuid_to_restore and uuid_to_restore in processed_uuids:
            doc = self.db_manager.get_document_by_uuid(uuid_to_restore)
            if doc:
                file_path = self.vault_manager.get_file_path(doc.uuid)
                if file_path:
                    self.pdf_viewer.load_document(str(file_path), uuid=doc.uuid)
                 

        self.list_widget.refresh_list()
        QMessageBox.information(self, self.tr("Reprocessed"), f"Reprocessed {success_count}/{total} documents.")

    def import_document_slot(self):
        """Handle import button click."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, self.tr("Select Document"), "", self.tr("PDF Files (*.pdf);;All Files (*)")
        )
        
        if file_path and self.pipeline:
            try:
                doc = self.pipeline.process_document(file_path)
                QMessageBox.information(
                    self, self.tr("Success"), self.tr("Document imported successfully!") + f"\nUUID: {doc.uuid}"
                )
                if self.list_widget:
                    self.list_widget.refresh_list()
            except Exception as e:
                QMessageBox.critical(
                    self, self.tr("Error"), self.tr("Failed to process document: {}").format(e)
                )
        elif not self.pipeline:
            # Fallback/Debug if pipeline is missing
            print(f"Selected: {file_path}, but no pipeline connected.")

    def open_scanner_slot(self):
        """Open scanner dialog and process result."""
        from gui.scanner_dialog import ScannerDialog
        dialog = ScannerDialog(self)
        if dialog.exec():
            path = dialog.get_scanned_file()
            if path and self.pipeline:
                try:
                    # Treat scanned file as a normal import
                    doc = self.pipeline.process_document(path)
                    QMessageBox.information(
                        self, self.tr("Success"), self.tr("Scanned document imported successfully!") + f"\nUUID: {doc.uuid}"
                    )
                    if self.list_widget:
                        self.list_widget.refresh_list()
                except Exception as e:
                    QMessageBox.critical(
                        self, self.tr("Error"), self.tr("Failed to process scanned document: {}").format(e)
                    )
            
            # Note: The temp file from scanner (path) is now in Vault (processed).
            # We can optionally delete the temp file if not handled by Scanner/Vault logic,
            # but Vault usually copies it. 
            # ScannerWorker creates a temp file. process_document stores it.
            # We should cleanup the original temp file? 
            # process_document reads from path, Vault stores it. 
            # Yes, Scanner generated a temp file. We should delete it after processing.
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except:
                    pass

    def refresh_list_slot(self):
        if self.list_widget:
            self.list_widget.refresh_list()

    def open_settings_slot(self):
        dialog = SettingsDialog(self)
        dialog.settings_changed.connect(self.on_settings_changed)
        dialog.exec()
        
    def on_settings_changed(self):
        # Handle dynamic updates if needed (e.g., changing language instantly)
        # For now, maybe just prompt restart if language changes
        # But OCR/Vault settings might take effect next time action is called.
        pass

    def merge_documents_slot(self, uuids: list[str]):
        """Handle merge request."""
        if not self.pipeline:
            return
            
        reply = QMessageBox.question(self, self.tr("Confirm Merge"),
                                   self.tr(f"Merge {len(uuids)} documents into a new file? Originals will be kept."),
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                                   
        if reply == QMessageBox.StandardButton.Yes:
            try:
                # Merge
                merged_doc = self.pipeline.merge_documents(uuids)
                if merged_doc:
                    QMessageBox.information(self, self.tr("Success"), self.tr("Documents merged successfully."))
                    self.list_widget.refresh_list()
                else:
                    QMessageBox.warning(self, self.tr("Error"), self.tr("Merge failed."))
            except Exception as e:
                QMessageBox.critical(self, self.tr("Error"), self.tr(f"Merge error: {e}"))

    def show_about_dialog(self):
        """Show the About dialog with system info."""
        qt_version = PyQt6.QtCore.QT_VERSION_STR
        py_version = sys.version.split()[0]
        platform_info = platform.system() + " " + platform.release()
        
        # Try to get KDE version
        kde_version = os.environ.get('KDE_FULL_SESSION', self.tr("Unknown"))
        if kde_version == 'true':
            # Try to fetch specific version if possible, otherwise just indicate KDE is present
            kde_version = self.tr("KDE Plasma (Detected)")
        else:
            kde_version = self.tr("Not Detected")

        QMessageBox.about(
            self,
            self.tr("About KPaperFlux"),
            self.tr(
                "<h3>KPaperFlux v1.0</h3>"
                "<p>A modern document management tool.</p>"
                "<hr>"
                "<p><b>Qt Version:</b> {qt_ver}</p>"
                "<p><b>Python:</b> {py_ver}</p>"
                "<p><b>System:</b> {sys_ver}</p>"
                "<p><b>Desktop Environment:</b> {kde_ver}</p>"
            ).format(
                qt_ver=qt_version,
                py_ver=py_version,
                sys_ver=platform_info,
                kde_ver=kde_version
            )
        )

    def find_duplicates_slot(self):
        """Open Duplicate Finder."""
        from core.similarity import SimilarityManager
        from gui.duplicate_dialog import DuplicateFinderDialog
        
        sim_manager = SimilarityManager(self.db_manager, self.pipeline.vault)
        duplicates = sim_manager.find_duplicates()
        
        if not duplicates:
             QMessageBox.information(self, self.tr("No Duplicates"), self.tr("No duplicates found with current threshold."))
             return

        dialog = DuplicateFinderDialog(duplicates, self.db_manager, self)
        dialog.exec()

    def open_maintenance_slot(self):
        """Open Maintenance Dialog."""
        from gui.maintenance_dialog import MaintenanceDialog
        from core.integrity import IntegrityManager
        
        if not self.pipeline or not self.db_manager:
            return
            
        dialog.exec()
        
        # Refresh list as documents might have been deleted/imported
        # regardless of how dialog was closed
        if self.list_widget:
            self.list_widget.refresh_list()

    def dragEnterEvent(self, event: QDragEnterEvent):
        """Handle Drag Enter: Check for PDFs."""
        if event.mimeData().hasUrls():
            # Check if any file is PDF
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith('.pdf'):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent):
        """Handle Drop: Extract files."""
        files = []
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                path = url.toLocalFile()
                if path.lower().endswith('.pdf') and os.path.exists(path):
                    files.append(path)
        
        if files:
            self.handle_dropped_files(files)
            event.acceptProposedAction()

    def handle_dropped_files(self, files: list[str]):
        """Confirm import and options."""
        if not self.pipeline:
            return

        # Custom Dialog for Options
        dialog = QDialog(self)
        dialog.setWindowTitle(self.tr("Import Dropped Files"))
        
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(self.tr(f"Import {len(files)} files into KPaperFlux?")))
        
        chk_move = QCheckBox(self.tr("Move files to Vault (Delete source)"))
        layout.addWidget(chk_move)
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            move_source = chk_move.isChecked()
            success_count = 0
            count = len(files)
            
            # Progress Dialog
            from PyQt6.QtWidgets import QProgressDialog
            from PyQt6.QtCore import QCoreApplication
            
            progress = QProgressDialog(self.tr("Importing..."), self.tr("Cancel"), 0, count, self)
            progress.setWindowModality(Qt.WindowModality.WindowModal)
            progress.setMinimumDuration(0)
            progress.forceShow()
            QCoreApplication.processEvents()
            
            # Worker Setup
            from gui.workers import ImportWorker
            
            self.import_worker = ImportWorker(self.pipeline, files, move_source=move_source)
            
            # Signals
            self.import_worker.progress.connect(
                lambda i, fname: (
                    progress.setLabelText(self.tr(f"Importing {os.path.basename(fname)}...")),
                    progress.setValue(i)
                )
            )
            
            self.import_worker.finished.connect(
                lambda success, total, err: self._on_import_finished(success, total, err, len(files), progress)
            )
            
            progress.canceled.connect(self.import_worker.cancel)
            
            self.import_worker.start()

    def _on_import_finished(self, success_count, total, error_msg, original_total, progress_dialog):
        progress_dialog.close()
        self.import_worker = None
        
        if error_msg:
             # Just print/log, assuming partial success is common or handled individually
             print(f"Worker finished with error signal: {error_msg}")

        QMessageBox.information(self, self.tr("Import Complete"),
                              self.tr(f"Successfully imported {success_count} of {total} files."))
        
        if self.list_widget:
            self.list_widget.refresh_list()

    def export_documents_slot(self, uuids: list[str]):
        """Export selected documents to a folder."""
        if not uuids or not self.pipeline:
            return
            
        target_dir = QFileDialog.getExistingDirectory(self, self.tr("Select Export Directory"))
        if not target_dir:
            return
            
        count = 0
        for uuid in uuids:
            # Get vault path
            src_path = self.pipeline.vault.get_file_path(uuid)
            if src_path and os.path.exists(src_path):
                # Determine filename: uuid.pdf or original_filename?
                # User prefers readable names.
                # Get doc from DB to find original filename?
                doc = self.db_manager.get_document_by_uuid(uuid)
                filename = doc.original_filename if doc else f"{uuid}.pdf"
                
                # Check collision
                dst_path = os.path.join(target_dir, filename)
                if os.path.exists(dst_path):
                    # Append uuid to unique
                    base, ext = os.path.splitext(filename)
                    dst_path = os.path.join(target_dir, f"{base}_{uuid[:8]}{ext}")
                    
                try:
                    shutil.copy2(src_path, dst_path)
                    count += 1
                except Exception as e:
                    print(f"Export error {uuid}: {e}")
                    
        QMessageBox.information(self, self.tr("Export"), self.tr(f"Exported {count} documents to {target_dir}."))

    def stamp_document_slot(self, uuid: str):
        """Stamp a document."""
        if not self.pipeline:
            return
            
        src_path = self.pipeline.vault.get_file_path(uuid)
        if not src_path or not os.path.exists(src_path):
            return

        from gui.stamper_dialog import StamperDialog
        dialog = StamperDialog(self)
        
        # Check for existing stamps
        stamper = DocumentStamper()
        existing_stamps = stamper.get_stamps(src_path)
        
        dialog.populate_stamps(existing_stamps)
        
        if dialog.exec():
            action, text, pos, color, rotation, remove_id = dialog.get_data()
            try:
                base, ext = os.path.splitext(src_path)
                
                if action == "remove":
                    removed = stamper.remove_stamp(src_path, stamp_id=remove_id)
                    if removed:
                        QMessageBox.information(self, self.tr("Success"), self.tr("Stamp removed."))
                    else:
                        QMessageBox.information(self, self.tr("Info"), self.tr("Failed to remove stamp."))
                else:
                    # APPLY
                    # Note: We use tmp path to ensure safe write, then move back.
                    # apply_stamp uses pikepdf default open, so saving to same file might need allow_overwriting_input.
                    # The tmp file approach is safe.
                    tmp_path = f"{base}_stamped{ext}"
                    stamper.apply_stamp(src_path, tmp_path, text, position=pos, color=color, rotation=rotation)
                    
                    # Move back
                    shutil.move(tmp_path, src_path)
                    
                    QMessageBox.information(self, self.tr("Success"), self.tr("Stamp applied."))
                
                # Refresh viewer if this doc is selected
                # self.detail_widget.display_document(doc) -> triggers reload
                # Or just emit selection again
                # Fix: Signal expects list[str]
                self.list_widget.document_selected.emit([uuid])
                
            except Exception as e:
                QMessageBox.critical(self, self.tr("Error"), self.tr(f"Stamping operation failed: {e}"))

    def manage_tags_slot(self, uuids: list[str]):
        """Open dialog to add/remove tags for selected documents."""
        if not uuids: return
        
        from gui.batch_tag_dialog import BatchTagDialog
        dialog = BatchTagDialog(self)
        if dialog.exec():
            add_tags, remove_tags = dialog.get_data()
            
            # Iterate
            count = 0
            for uuid in uuids:
                doc = self.db_manager.get_document_by_uuid(uuid)
                if not doc: continue
                
                # Split current tags by comma
                current_tags_list = [t.strip() for t in (doc.tags or "").split(",") if t.strip()]
                
                # Add
                for t in add_tags:
                    # Check case insensitive existence? Or exact? 
                    # Let's assume exact for now, but case-insesitive check is better UX.
                    if t not in current_tags_list:
                        current_tags_list.append(t)
                        
                # Remove
                # remove_tags also exact match
                current_tags_list = [t for t in current_tags_list if t not in remove_tags]
                
                new_tags_str = ", ".join(current_tags_list)
                
                # Update if changed
                if new_tags_str != (doc.tags or ""):
                    # Avoid updating creation date etc? update_metadata keeps valid columns
                    success = self.db_manager.update_document_metadata(uuid, {'tags': new_tags_str})
                    if success:
                        count += 1
                    
            if count > 0:
                self.list_widget.refresh_list()
                QMessageBox.information(self, self.tr("Tags Updated"), self.tr(f"Updated tags for {count} documents."))

    def toggle_editor_visibility(self, checked: bool):
        """Toggle the visibility of the metadata editor widget."""
        self.editor_widget.setVisible(checked)
        
    def update_status_bar(self, visible_count: int, total_count: int):
        """Update status bar with document counts."""
        self.statusBar().showMessage(self.tr(f"Documents: {visible_count} (Total: {total_count})"))

    def closeEvent(self, event: QCloseEvent):
        """Save state before closing."""
        if self.list_widget:
            self.list_widget.save_state()
        event.accept()
