from typing import Optional
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QPushButton, QLabel, QFileDialog, 
    QMessageBox, QSplitter, QMenuBar, QMenu, QCheckBox, QDialog, QDialogButtonBox
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
from gui.document_detail import DocumentDetailWidget
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
        
        # Central Widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main Layout
        layout = QVBoxLayout(central_widget)
        
        # Toolbar / Header (Optional, keeping Import button for ease of access)
        # self.label = QLabel(self.tr("KPaperFlux v1.0"))
        # layout.addWidget(self.label)
        
        # Filter Widget
        self.filter_widget = FilterWidget()
        layout.addWidget(self.filter_widget)
        
        # Master-Detail Splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)
        
        # Document List (Master)
        if self.db_manager:
            self.list_widget = DocumentListWidget(self.db_manager)
            self.list_widget.document_selected.connect(self.on_document_selected)
            self.list_widget.delete_requested.connect(self.delete_document_slot)
            self.list_widget.delete_requested.connect(self.delete_document_slot)
            self.list_widget.reprocess_requested.connect(self.reprocess_document_slot)
            self.list_widget.merge_requested.connect(self.merge_documents_slot)
            self.list_widget.export_requested.connect(self.export_documents_slot)
            self.list_widget.stamp_requested.connect(self.stamp_document_slot)
            
            # Connect Filter
            self.filter_widget.filter_changed.connect(self.list_widget.apply_filter)
            
            splitter.addWidget(self.list_widget)
            self.list_widget.refresh_list()
        else:
            self.list_widget = None
        
        # Document Detail (Detail)
        # Document Detail (Detail)
        vault = self.pipeline.vault if self.pipeline else None
        self.detail_widget = DocumentDetailWidget(self.db_manager, vault)
        splitter.addWidget(self.detail_widget)
        
        # Set initial sizes (List=40%, Detail=60%)
        splitter.setSizes([400, 600])

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
        action_extra.setCheckable(True)
        # Placeholder for toggling columns or detail pane details
        view_menu.addAction(action_extra)
        
        # -- Config Menu --
        config_menu = menubar.addMenu(self.tr("&Config"))
        
        action_settings = QAction(self.tr("&Settings..."), self)
        action_settings.triggered.connect(self.open_settings_slot)
        config_menu.addAction(action_settings)
        
        action_maintenance = QAction(self.tr("&Maintenance..."), self)
        action_maintenance.triggered.connect(self.open_maintenance_slot)
        config_menu.addAction(action_maintenance)

        # -- Help Menu --
        help_menu = menubar.addMenu(self.tr("&Help"))
        
        action_about = QAction(self.tr("&About"), self)
        action_about.triggered.connect(self.show_about_dialog)
        help_menu.addAction(action_about)

    def on_document_selected(self, uuid: str):
        """Handle document selection."""
        if self.db_manager:
            doc = self.db_manager.get_document_by_uuid(uuid)
            if doc:
                self.detail_widget.display_document(doc)
            else:
                self.detail_widget.clear_display()

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
                    self.detail_widget.clear_display()
                    
    def reprocess_document_slot(self, uuid: str):
        """Handle reprocess request."""
        if self.pipeline:
            updated_doc = self.pipeline.reprocess_document(uuid)
            if updated_doc:
                QMessageBox.information(self, self.tr("Success"), self.tr("Document reprocessed successfully."))
                self.detail_widget.display_document(updated_doc)
            else:
                QMessageBox.warning(self, self.tr("Error"), self.tr("Failed to reprocess document."))

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

    def open_maintenance_slot(self):
        """Open Maintenance Dialog."""
        from gui.maintenance_dialog import MaintenanceDialog
        from core.integrity import IntegrityManager
        
        if not self.pipeline or not self.db_manager:
            return
            
        # Ensure vault is available
        vault = self.pipeline.vault
        if not vault:
            return
            
        integrity_manager = IntegrityManager(self.db_manager, vault)
        dialog = MaintenanceDialog(self, integrity_manager, self.pipeline)
        
        # Execute dialog (blocking)
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
            
            for fpath in files:
                try:
                    self.pipeline.process_document(fpath, move_source=move_source)
                    success_count += 1
                except Exception as e:
                    print(f"Error importing {fpath}: {e}")
            
            QMessageBox.information(self, self.tr("Import Complete"),
                                  self.tr(f"Successfully imported {success_count} of {len(files)} files."))
            
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
        if dialog.exec():
            text, pos, color = dialog.get_data()
            stamper = DocumentStamper()
            try:
                # Modify in place? or tmp and move?
                # PikePDF save to same file sometimes issues?
                # Better safe: temp output, then move.
                base, ext = os.path.splitext(src_path)
                tmp_path = f"{base}_stamped{ext}"
                
                stamper.apply_stamp(src_path, tmp_path, text, position=pos, color=color)
                
                # Move back
                shutil.move(tmp_path, src_path)
                
                QMessageBox.information(self, self.tr("Success"), self.tr("Stamp applied."))
                
                # Refresh viewer if this doc is selected
                # self.detail_widget.display_document(doc) -> triggers reload
                # Or just emit selection again
                self.list_widget.document_selected.emit(uuid)
                
            except Exception as e:
                QMessageBox.critical(self, self.tr("Error"), self.tr(f"Stamping failed: {e}"))

    def closeEvent(self, event: QCloseEvent):
        """Save state before closing."""
        if self.list_widget:
            self.list_widget.save_state()
        event.accept()
