from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QHeaderView, QMessageBox, QInputDialog, QAbstractItemView,
    QLabel, QLineEdit, QGroupBox
)
from PyQt6.QtCore import Qt

# Core Imports
try:
    from core.database import DatabaseManager
except ImportError:
    class DatabaseManager: pass

# Hilfsfunktion für Message Boxen (Fallback)
try:
    from gui.utils import show_selectable_message_box, show_notification
except ImportError:
    def show_selectable_message_box(parent, title, text, icon=QMessageBox.Icon.Information, buttons=QMessageBox.StandardButton.Ok):
        msg = QMessageBox(parent)
        msg.setWindowTitle(title)
        msg.setText(text)
        msg.setIcon(icon)
        msg.setStandardButtons(buttons)
        return msg.exec()

    def show_notification(parent, title, text, duration=3000):
        print(f"[Fallback-Notification] {title}: {text}")

class TagManagerDialog(QDialog):
    def __init__(self, db_manager: DatabaseManager, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.setWindowTitle(self.tr("Tag Manager"))
        self.resize(600, 700) # Slightly larger
        self._init_ui()
        self.refresh_tags()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # 1. Search Bar
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel(self.tr("Filter:")))
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText(self.tr("Search tags..."))
        self.txt_search.textChanged.connect(self.filter_table)
        search_layout.addWidget(self.txt_search)
        layout.addLayout(search_layout)

        # 2. Table
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels([self.tr("Tag Name"), self.tr("Usage Count")])

        # Column Styling
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)

        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setAlternatingRowColors(True) # Visual Polish
        self.table.setSortingEnabled(True) # Enable sorting

        layout.addWidget(self.table)

        # 3. Action Group
        action_group = QGroupBox(self.tr("Actions"))
        action_layout = QHBoxLayout(action_group)

        self.btn_rename = QPushButton(self.tr("Rename"))
        self.btn_rename.clicked.connect(self.rename_selected)
        action_layout.addWidget(self.btn_rename)

        self.btn_merge = QPushButton(self.tr("Merge Selected"))
        self.btn_merge.clicked.connect(self.merge_selected)
        action_layout.addWidget(self.btn_merge)

        self.btn_delete = QPushButton(self.tr("Delete"))
        self.btn_delete.clicked.connect(self.delete_selected)
        # Style Delete button slightly destructive (optional, pure Qt css later)
        action_layout.addWidget(self.btn_delete)

        layout.addWidget(action_group)

        # 4. Footer (Close)
        footer_layout = QHBoxLayout()
        footer_layout.addStretch()
        self.btn_close = QPushButton(self.tr("Close"))
        self.btn_close.clicked.connect(self.accept)
        footer_layout.addWidget(self.btn_close)

        layout.addLayout(footer_layout)

    def refresh_tags(self):
        self.table.setSortingEnabled(False) # Disable sorting while populating
        self.table.setRowCount(0)
        if self.db_manager:
            tags = self.db_manager.get_all_tags_with_counts()
        else:
            tags = {}

        sorted_tags = sorted(tags.items(), key=lambda item: item[0].lower())

        self.table.setRowCount(len(sorted_tags))
        for row, (tag, count) in enumerate(sorted_tags):
            # Name
            item_name = QTableWidgetItem(tag)
            item_name.setFlags(item_name.flags() ^ Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, item_name)

            # Count
            # Use setData(DisplayRole) allows numeric sorting if using integer
            item_count = QTableWidgetItem()
            item_count.setData(Qt.ItemDataRole.DisplayRole, count)
            item_count.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_count.setFlags(item_count.flags() ^ Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 1, item_count)

        self.table.setSortingEnabled(True)
        self.filter_table() # Re-apply filter if any

    def filter_table(self):
        query = self.txt_search.text().lower().strip()
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            visible = True
            if query:
                if query not in item.text().lower():
                    visible = False
            self.table.setRowHidden(row, not visible)

    def rename_selected(self):
        selected_rows = self._get_selected_rows()
        if len(selected_rows) != 1:
            show_selectable_message_box(self, self.tr("Rename"), self.tr("Please select exactly one tag to rename."), icon=QMessageBox.Icon.Warning)
            return

        old_tag = self.table.item(selected_rows[0], 0).text()

        new_tag, ok = QInputDialog.getText(self, self.tr("Rename Tag"), self.tr("New Name:"), text=old_tag)
        if ok and new_tag and new_tag != old_tag:
            count = self.db_manager.rename_tag(old_tag, new_tag)
            show_notification(self, self.tr("Result"), self.tr(f"Updated {count} document(s)."))
            self.refresh_tags()

    def merge_selected(self):
        selected_rows = self._get_selected_rows()
        if len(selected_rows) < 2:
            show_selectable_message_box(self, self.tr("Merge"), self.tr("Please select at least two tags to merge."), icon=QMessageBox.Icon.Warning)
            return

        tags = [self.table.item(row, 0).text() for row in selected_rows]

        # Ask for target name
        target_tag, ok = QInputDialog.getItem(
            self,
            self.tr("Merge Tags"),
            self.tr(f"Merge {len(tags)} tags into:"),
            tags,
            0,
            True
        )

        if ok and target_tag:
            count = self.db_manager.merge_tags(tags, target_tag)
            show_notification(self, self.tr("Result"), self.tr(f"Merged tags. Updated {count} document(s)."))
            self.refresh_tags()

    def delete_selected(self):
        selected_rows = self._get_selected_rows()
        if not selected_rows: return

        tags = [self.table.item(row, 0).text() for row in selected_rows]

        confirm = show_selectable_message_box(
            self,
            self.tr("Delete Tags"),
            self.tr(f"Are you sure you want to remove these {len(tags)} tags from ALL documents?\n\n{', '.join(tags)}"),
            icon=QMessageBox.Icon.Question,
            buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if confirm == QMessageBox.StandardButton.Yes:
            total = 0
            for tag in tags:
                total += self.db_manager.delete_tag(tag)
            show_notification(self, self.tr("Result"), self.tr(f"Removed tags from {total} document(s)."))
            self.refresh_tags()

    def _get_selected_rows(self):
        """Helper to get unique selected rows handling hidden rows properly."""
        selection = self.table.selectionModel().selectedRows()
        # Filter out hidden rows (if selection persisted implicitly?)
        # Only consider visible rows
        rows = [idx.row() for idx in selection if not self.table.isRowHidden(idx.row())]
        return sorted(rows)
