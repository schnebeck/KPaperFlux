from typing import Optional
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QPushButton, QLabel, QFileDialog, 
    QMessageBox, QSplitter, QMenuBar, QMenu
)
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtCore import Qt
import sys
import platform
import os
import PyQt6.QtCore
from core.pipeline import PipelineProcessor
from core.database import DatabaseManager
from gui.document_list import DocumentListWidget
from gui.document_detail import DocumentDetailWidget
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
        
        self.create_menu_bar()
        
        # Central Widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main Layout
        layout = QVBoxLayout(central_widget)
        
        # Toolbar / Header (Optional, keeping Import button for ease of access)
        # self.label = QLabel(self.tr("KPaperFlux v1.0"))
        # layout.addWidget(self.label)
        
        # Master-Detail Splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)
        
        # Document List (Master)
        if self.db_manager:
            self.list_widget = DocumentListWidget(self.db_manager)
            self.list_widget.document_selected.connect(self.on_document_selected)
            self.list_widget.delete_requested.connect(self.delete_document_slot)
            self.list_widget.reprocess_requested.connect(self.reprocess_document_slot)
            
            splitter.addWidget(self.list_widget)
            self.list_widget.refresh_list()
        else:
            self.list_widget = None
        
        # Document Detail (Detail)
        self.detail_widget = DocumentDetailWidget()
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
        action_scan.setEnabled(False) # Placeholder
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
