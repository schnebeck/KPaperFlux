
import json
from typing import Optional, List
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, 
                             QTableWidgetItem, QPushButton, QHeaderView, 
                             QMessageBox, QDialogButtonBox, QLabel, QLineEdit, 
                             QCheckBox, QSpinBox, QFrame, QProgressDialog, QWidget)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from core.database import DatabaseManager
from core.filter_tree import FilterTree, FilterNode, NodeType
from gui.widgets.filter_group import FilterGroupWidget

class RuleEditorDialog(QDialog):
    """
    Phase 106: Editor for a single Auto-Tagging Rule.
    Now works with FilterNode objects from the FilterTree.
    """
    def __init__(self, node: Optional[FilterNode] = None, filter_tree: Optional[FilterTree] = None, db_manager: Optional[DatabaseManager] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Tagging Rule" if node else "New Tagging Rule")
        self.resize(800, 600)
        self.db_manager = db_manager
        self.filter_tree = filter_tree
        self.node = node
        
        # 1. Initialize Metadata for Filter Engine
        self.extra_keys = []
        self.available_tags = []
        if db_manager:
            self.extra_keys = db_manager.get_available_extra_keys()
            if hasattr(db_manager, "get_available_tags"):
                self.available_tags = db_manager.get_available_tags()

        self._init_ui()
        
        if node:
            self.set_node(node)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        # --- Header Section (Metadata) ---
        header_frame = QFrame()
        header_layout = QHBoxLayout(header_frame)
        
        header_layout.addWidget(QLabel("Rule Name:"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. Mark High Priority Invoices")
        header_layout.addWidget(self.name_edit, 1)
        
        self.enabled_chk = QCheckBox("Enabled")
        self.enabled_chk.setChecked(True)
        header_layout.addWidget(self.enabled_chk)
        
        self.auto_chk = QCheckBox("Auto-Apply")
        self.auto_chk.setChecked(True)
        header_layout.addWidget(self.auto_chk)
        
        layout.addWidget(header_frame)
        
        # --- Middle Section (Condition) ---
        layout.addWidget(QLabel("<b>IF</b> these conditions match:"))
        self.filter_group = FilterGroupWidget(extra_keys=self.extra_keys, 
                                              available_tags=self.available_tags, 
                                              is_root=True)
        layout.addWidget(self.filter_group, 1)
        
        # --- Bottom Section (Action) ---
        action_frame = QFrame()
        action_frame.setFrameShape(QFrame.Shape.StyledPanel)
        action_layout = QVBoxLayout(action_frame)
        
        action_layout.addWidget(QLabel("<b>THEN</b> apply these changes:"))
        
        # Tags to add
        add_layout = QHBoxLayout()
        add_layout.addWidget(QLabel("Add Tags:"))
        self.tags_add_edit = QLineEdit()
        self.tags_add_edit.setPlaceholderText("Comma separated list, e.g. HIGH_PRIO, REVIEW")
        add_layout.addWidget(self.tags_add_edit)
        action_layout.addLayout(add_layout)
        
        # Tags to remove
        rem_layout = QHBoxLayout()
        rem_layout.addWidget(QLabel("Remove Tags:"))
        self.tags_rem_edit = QLineEdit()
        self.tags_rem_edit.setPlaceholderText("Optional, e.g. NEW, UNPROCESSED")
        rem_layout.addWidget(self.tags_rem_edit)
        action_layout.addLayout(rem_layout)
        
        layout.addWidget(action_frame)
        
        # Buttons
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def set_node(self, node: FilterNode):
        self.name_edit.setText(node.name)
        self.enabled_chk.setChecked(node.is_enabled)
        self.auto_chk.setChecked(node.auto_apply)
        self.filter_group.set_query(node.data)
        self.tags_add_edit.setText(", ".join(node.tags_to_add))
        self.tags_rem_edit.setText(", ".join(node.tags_to_remove))

    def save_to_node(self, node: FilterNode):
        node.name = self.name_edit.text().strip() or "Unnamed Rule"
        node.data = self.filter_group.get_query()
        node.tags_to_add = [t.strip() for t in self.tags_add_edit.text().split(",") if t.strip()]
        node.tags_to_remove = [t.strip() for t in self.tags_rem_edit.text().split(",") if t.strip()]
        node.is_enabled = self.enabled_chk.isChecked()
        node.auto_apply = self.auto_chk.isChecked()

class RuleManagerWidget(QWidget):
    """
    Phase 106: Reusable widget to manage all Auto-Tagging Rules from the FilterTree.
    """
    def __init__(self, db_manager: DatabaseManager, filter_tree: FilterTree, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.filter_tree = filter_tree
        self._init_ui()
        self.load_rules()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Help text
        help_label = QLabel(self.tr("Rules are integrated into the FilterTree structure."))
        help_label.setStyleSheet("color: #666; font-style: italic;")
        layout.addWidget(help_label)
        
        # Table
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([
            self.tr("Type"), 
            self.tr("Name"), 
            self.tr("Add Tags"), 
            self.tr("Active"), 
            self.tr("Actions")
        ])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.table)
        
        # Buttons
        btn_layout = QHBoxLayout()
        self.btn_add = QPushButton(self.tr("Add New Rule"))
        self.btn_add.clicked.connect(self.on_add_rule)
        btn_layout.addWidget(self.btn_add)
        
        btn_layout.addStretch()
        
        self.btn_apply_all = QPushButton(self.tr("Apply All Rules to Database"))
        self.btn_apply_all.setStyleSheet("background-color: #e1f5fe;")
        self.btn_apply_all.clicked.connect(self.on_apply_all)
        btn_layout.addWidget(self.btn_apply_all)
        
        layout.addLayout(btn_layout)

    def load_rules(self):
        rules = self.filter_tree.get_active_rules(only_auto=False)
        
        self.table.setRowCount(0)
        for node in rules:
            r = self.table.rowCount()
            self.table.insertRow(r)
            
            self.table.setItem(r, 0, QTableWidgetItem("Rule"))
            self.table.setItem(r, 1, QTableWidgetItem(node.name))
            self.table.setItem(r, 2, QTableWidgetItem(", ".join(node.tags_to_add)))
            self.table.setItem(r, 3, QTableWidgetItem("Yes" if node.is_enabled else "No"))
            
            # Action Buttons
            btn_container = QWidget()
            bl = QHBoxLayout(btn_container)
            bl.setContentsMargins(2, 2, 2, 2)
            
            edit_btn = QPushButton(self.tr("Edit"))
            edit_btn.clicked.connect(lambda checked, n=node: self.on_edit_rule(n))
            bl.addWidget(edit_btn)
            
            del_btn = QPushButton(self.tr("Delete"))
            del_btn.clicked.connect(lambda checked, n=node: self.on_delete_rule(n))
            bl.addWidget(del_btn)
            
            self.table.setCellWidget(r, 4, btn_container)

    def _get_rules_parent(self):
        # Find/Ensure "Auto-Tagging Rules" folder
        parent = self.filter_tree.root
        for child in self.filter_tree.root.children:
            if child.name == "Auto-Tagging Rules":
                return child
        # Not found? Create it
        from core.filter_tree import NodeType
        folder = FilterNode("Auto-Tagging Rules", NodeType.FOLDER)
        self.filter_tree.root.add_child(folder)
        return folder

    def on_add_rule(self):
        dlg = RuleEditorDialog(filter_tree=self.filter_tree, db_manager=self.db_manager, parent=self)
        if dlg.exec():
            parent = self._get_rules_parent()
            new_node = self.filter_tree.add_filter(parent, "New Rule", {})
            dlg.save_to_node(new_node)
            self._notify_change()
            self.load_rules()

    def on_edit_rule(self, node: FilterNode):
        dlg = RuleEditorDialog(node=node, filter_tree=self.filter_tree, db_manager=self.db_manager, parent=self)
        if dlg.exec():
            dlg.save_to_node(node)
            self._notify_change()
            self.load_rules()

    def on_delete_rule(self, node: FilterNode):
        if QMessageBox.question(self, "Delete Rule", f"Are you sure you want to delete '{node.name}'?") == QMessageBox.StandardButton.Yes:
            if node.parent:
                node.parent.remove_child(node)
                self._notify_change()
                self.load_rules()

    def _notify_change(self):
        # Trigger persistence if possible
        # Check if parent (AdvancedFilterWidget) has a save_callback
        p = self.parent()
        while p:
            if hasattr(p, "save_callback") and p.save_callback:
                p.save_callback()
                break
            p = p.parent()

    def on_apply_all(self):
        """Retroactive tagging: Batch process all documents in background."""
        reply = QMessageBox.question(self, "Apply All Rules", 
                                     "This will scan the entire database and apply all enabled tagging rules to every document. Continue?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            from gui.workers import BatchTaggingWorker
            
            self.progress = QProgressDialog("Applying rules to database...", "Cancel", 0, 100, self)
            self.progress.setWindowModality(Qt.WindowModality.WindowModal)
            
            self.worker = BatchTaggingWorker(self.db_manager, self.filter_tree)
            self.worker.progress.connect(self._on_worker_progress)
            self.worker.finished.connect(self._on_worker_finished)
            
            self.progress.canceled.connect(self.worker.cancel)
            
            self.worker.start()
            self.progress.show()

    def _on_worker_progress(self, current, total):
        self.progress.setMaximum(total)
        self.progress.setValue(current)
        self.progress.setLabelText(f"Processing document {current} of {total}...")

    def _on_worker_finished(self, modified_count):
        self.progress.close()
        QMessageBox.information(self, "Auto-Tagging Complete", 
                                f"Finished processing database.\n\n{modified_count} documents were modified.")

class RuleManagerDialog(QDialog):
    def __init__(self, db_manager: DatabaseManager, filter_tree: FilterTree, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Auto-Tagging Rule Manager")
        self.resize(800, 600)
        
        layout = QVBoxLayout(self)
        self.widget = RuleManagerWidget(db_manager, filter_tree, self)
        layout.addWidget(self.widget)
        
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
