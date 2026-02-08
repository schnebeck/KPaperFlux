from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QTabWidget, QWidget, QListWidget,
    QPushButton, QHBoxLayout, QMessageBox, QLabel, QListWidgetItem
)
from PyQt6.QtCore import Qt
import os
from pathlib import Path

# Core Imports
from core.integrity import IntegrityManager, IntegrityReport
from core.pipeline import PipelineProcessor

# Hilfsfunktion für Message Boxen (Fallback)
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

class MaintenanceDialog(QDialog):
    def __init__(self, parent, integrity_manager: IntegrityManager, pipeline: PipelineProcessor):
        super().__init__(parent)
        self.manager = integrity_manager
        self.pipeline = pipeline
        self.report = None

        self.setWindowTitle(self.tr("Database Maintenance"))
        self.resize(600, 500)

        layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Orphans Tab
        self.orphan_widget = QWidget()
        self.setup_orphan_tab()
        self.tabs.addTab(self.orphan_widget, self.tr("Missing Files (Orphans)"))

        # Ghosts Tab
        self.ghost_widget = QWidget()
        self.setup_ghost_tab()
        self.tabs.addTab(self.ghost_widget, self.tr("Unknown Files (Ghosts)"))

        # Refresh Button
        btn_refresh = QPushButton(self.tr("Rescan"))
        btn_refresh.clicked.connect(self.scan)
        layout.addWidget(btn_refresh)

        # Initial Scan
        self.scan()

    def setup_orphan_tab(self):
        layout = QVBoxLayout(self.orphan_widget)
        layout.addWidget(QLabel(self.tr("Entries in Database but file missing in Vault:")))

        self.list_orphans = QListWidget()
        self.list_orphans.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        layout.addWidget(self.list_orphans)

        btn_layout = QHBoxLayout()
        btn_delete = QPushButton(self.tr("Delete Selected Entries"))
        btn_delete.clicked.connect(self.delete_selected_orphans)
        btn_layout.addWidget(btn_delete)
        layout.addLayout(btn_layout)

    def setup_ghost_tab(self):
        layout = QVBoxLayout(self.ghost_widget)
        layout.addWidget(QLabel(self.tr("Files in Vault but missing in Database:")))

        self.list_ghosts = QListWidget()
        self.list_ghosts.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        layout.addWidget(self.list_ghosts)

        btn_layout = QHBoxLayout()
        btn_import = QPushButton(self.tr("Import Selected Files"))
        btn_import.clicked.connect(self.import_selected_ghosts)
        btn_layout.addWidget(btn_import)

        btn_delete = QPushButton(self.tr("Delete Selected Files"))
        btn_delete.clicked.connect(self.delete_selected_ghosts)
        btn_layout.addWidget(btn_delete)

        layout.addLayout(btn_layout)

    def scan(self):
        self.list_orphans.clear()
        self.list_ghosts.clear()

        try:
            self.report = self.manager.check_integrity()

            # Populate Orphans
            for doc in self.report.orphans:
                item = QListWidgetItem(f"{doc.uuid} ({doc.original_filename})")
                item.setData(Qt.ItemDataRole.UserRole, doc)
                self.list_orphans.addItem(item)

            # Populate Ghosts
            for path in self.report.ghosts:
                item = QListWidgetItem(path.name)
                item.setData(Qt.ItemDataRole.UserRole, str(path))
                self.list_ghosts.addItem(item)

            self.tabs.setTabText(0, self.tr(f"Missing Files ({len(self.report.orphans)})"))
            self.tabs.setTabText(1, self.tr(f"Unknown Files ({len(self.report.ghosts)})"))

        except Exception as e:
            show_selectable_message_box(self, self.tr("Error"), self.tr(f"Scan failed: {e}"), icon=QMessageBox.Icon.Critical)

    def delete_selected_orphans(self):
        items = self.list_orphans.selectedItems()
        if not items:
            return

        # Syntax corrected: logic moved outside function call arguments
        reply = show_selectable_message_box(
            self,
            self.tr("Confirm"),
            self.tr(f"Delete {len(items)} database entries?"),
            icon=QMessageBox.Icon.Question,
            buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        for item in items:
            doc = item.data(Qt.ItemDataRole.UserRole)
            self.manager.logic_repo.delete_by_uuid(doc.uuid)

        self.scan()

    def delete_selected_ghosts(self):
        items = self.list_ghosts.selectedItems()
        if not items:
            return

        # Syntax corrected
        reply = show_selectable_message_box(
            self,
            self.tr("Confirm"),
            self.tr(f"Permanently delete {len(items)} files?"),
            icon=QMessageBox.Icon.Question,
            buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        for item in items:
            path_str = item.data(Qt.ItemDataRole.UserRole)
            path = Path(path_str)
            if path.exists():
                path.unlink()

        self.scan()

    def import_selected_ghosts(self):
        items = self.list_ghosts.selectedItems()
        if not items:
            return

        for item in items:
            path_str = item.data(Qt.ItemDataRole.UserRole)
            try:
                self.pipeline.process_document(path_str, move_source=True)
            except Exception as e:
                print(f"Error importing ghost {path_str}: {e}")

        self.scan()
