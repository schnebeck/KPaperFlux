import json
from typing import Optional, List
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, 
                             QTableWidgetItem, QPushButton, QHeaderView, 
                             QMessageBox, QDialogButtonBox, QLabel, QLineEdit, 
                             QCheckBox, QSpinBox, QFrame, QProgressDialog, QWidget)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from core.database import DatabaseManager
from core.rules_engine import TaggingRule, RulesEngine
from gui.widgets.filter_group import FilterGroupWidget

class RuleEditorDialog(QDialog):
    """
    Phase 106: Editor for a single Auto-Tagging Rule.
    Wraps the FilterGroupWidget and adds the "Condition -> Action" logic.
    """
    def __init__(self, rule: Optional[TaggingRule] = None, db_manager: Optional[DatabaseManager] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Tagging Rule" if rule else "New Tagging Rule")
        self.resize(800, 600)
        self.db_manager = db_manager
        
        # 1. Initialize Metadata for Filter Engine
        self.extra_keys = []
        self.available_tags = []
        if db_manager:
            self.extra_keys = db_manager.get_available_extra_keys()
            if hasattr(db_manager, "get_available_tags"):
                self.available_tags = db_manager.get_available_tags()

        self._init_ui()
        
        if rule:
            self.set_rule(rule)
        else:
            # Default state
            pass

    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        # --- Header Section (Metadata) ---
        header_frame = QFrame()
        header_layout = QHBoxLayout(header_frame)
        
        header_layout.addWidget(QLabel("Rule Name:"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. Mark High Priority Invoices")
        header_layout.addWidget(self.name_edit, 1)
        
        header_layout.addWidget(QLabel("Order:"))
        self.order_spin = QSpinBox()
        self.order_spin.setRange(0, 1000)
        header_layout.addWidget(self.order_spin)
        
        self.enabled_chk = QCheckBox("Enabled")
        self.enabled_chk.setChecked(True)
        header_layout.addWidget(self.enabled_chk)
        
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

    def set_rule(self, rule: TaggingRule):
        self.name_edit.setText(rule.name)
        self.order_spin.setValue(rule.execution_order)
        self.enabled_chk.setChecked(rule.is_enabled)
        self.filter_group.set_query(rule.filter_conditions)
        self.tags_add_edit.setText(", ".join(rule.tags_to_add))
        self.tags_rem_edit.setText(", ".join(rule.tags_to_remove))

    def get_rule(self) -> TaggingRule:
        tags_add = [t.strip() for t in self.tags_add_edit.text().split(",") if t.strip()]
        tags_rem = [t.strip() for t in self.tags_rem_edit.text().split(",") if t.strip()]
        
        return TaggingRule(
            name=self.name_edit.text().strip() or "Unnamed Rule",
            filter_conditions=self.filter_group.get_query(),
            tags_to_add=tags_add,
            tags_to_remove=tags_rem,
            is_enabled=self.enabled_chk.isChecked(),
            execution_order=self.order_spin.value()
        )

class RuleManagerWidget(QWidget):
    """
    Phase 106: Reusable widget to manage all Auto-Tagging Rules.
    Can be used in a tab or a dialog.
    """
    def __init__(self, db_manager: DatabaseManager, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self._init_ui()
        self.load_rules()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Help text
        help_label = QLabel(self.tr("Rules are applied automatically after AI analysis or can be triggered manually."))
        help_label.setStyleSheet("color: #666; font-style: italic;")
        layout.addWidget(help_label)
        
        # Table
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([
            self.tr("Order"), 
            self.tr("Name"), 
            self.tr("Add Tags"), 
            self.tr("Enabled"), 
            self.tr("Actions")
        ])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(2, 150)
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
        cursor = self.db_manager.connection.cursor()
        cursor.execute("SELECT id, name, filter_conditions, tags_to_add, tags_to_remove, is_enabled, execution_order FROM tagging_rules ORDER BY execution_order ASC")
        rows = cursor.fetchall()
        
        self.table.setRowCount(0)
        for row in rows:
            rule = TaggingRule.from_row(row)
            r = self.table.rowCount()
            self.table.insertRow(r)
            
            self.table.setItem(r, 0, QTableWidgetItem(str(rule.execution_order)))
            self.table.setItem(r, 1, QTableWidgetItem(rule.name))
            self.table.setItem(r, 2, QTableWidgetItem(", ".join(rule.tags_to_add)))
            self.table.setItem(r, 3, QTableWidgetItem("Yes" if rule.is_enabled else "No"))
            
            # Action Buttons
            btn_container = QWidget()
            bl = QHBoxLayout(btn_container)
            bl.setContentsMargins(2, 2, 2, 2)
            
            edit_btn = QPushButton(self.tr("Edit"))
            edit_btn.clicked.connect(lambda checked, rule_id=rule.id: self.on_edit_rule(rule_id))
            bl.addWidget(edit_btn)
            
            del_btn = QPushButton(self.tr("Delete"))
            del_btn.clicked.connect(lambda checked, rule_id=rule.id: self.on_delete_rule(rule_id))
            bl.addWidget(del_btn)
            
            self.table.setCellWidget(r, 4, btn_container)

    def on_add_rule(self):
        dlg = RuleEditorDialog(db_manager=self.db_manager, parent=self)
        if dlg.exec():
            rule = dlg.get_rule()
            self._save_rule(rule)
            self.load_rules()

    def on_edit_rule(self, rule_id):
        cursor = self.db_manager.connection.cursor()
        cursor.execute("SELECT id, name, filter_conditions, tags_to_add, tags_to_remove, is_enabled, execution_order FROM tagging_rules WHERE id = ?", (rule_id,))
        row = cursor.fetchone()
        if not row: return
        
        rule = TaggingRule.from_row(row)
        dlg = RuleEditorDialog(rule=rule, db_manager=self.db_manager, parent=self)
        if dlg.exec():
            updated_rule = dlg.get_rule()
            updated_rule.id = rule_id
            self._save_rule(updated_rule)
            self.load_rules()

    def on_delete_rule(self, rule_id):
        if QMessageBox.question(self, "Delete Rule", "Are you sure you want to delete this rule?") == QMessageBox.StandardButton.Yes:
            with self.db_manager.connection:
                self.db_manager.connection.execute("DELETE FROM tagging_rules WHERE id = ?", (rule_id,))
            self.load_rules()

    def _save_rule(self, rule: TaggingRule):
        sql = ""
        params = (rule.name, json.dumps(rule.filter_conditions), 
                  json.dumps(rule.tags_to_add), json.dumps(rule.tags_to_remove),
                  1 if rule.is_enabled else 0, rule.execution_order)
        
        if rule.id:
            sql = "UPDATE tagging_rules SET name=?, filter_conditions=?, tags_to_add=?, tags_to_remove=?, is_enabled=?, execution_order=? WHERE id=?"
            params += (rule.id,)
        else:
            sql = "INSERT INTO tagging_rules (name, filter_conditions, tags_to_add, tags_to_remove, is_enabled, execution_order) VALUES (?, ?, ?, ?, ?, ?)"
            
        with self.db_manager.connection:
            self.db_manager.connection.execute(sql, params)

    def on_apply_all(self):
        """Retroactive tagging: Batch process all documents in background."""
        reply = QMessageBox.question(self, "Apply All Rules", 
                                     "This will scan the entire database and apply all enabled tagging rules to every document. Continue?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            from gui.workers import BatchTaggingWorker
            
            self.progress = QProgressDialog("Applying rules to database...", "Cancel", 0, 100, self)
            self.progress.setWindowModality(Qt.WindowModality.WindowModal)
            
            self.worker = BatchTaggingWorker(self.db_manager)
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
    """
    Phase 106: Dialog to manage all Auto-Tagging Rules.
    (Keeping for backward compatibility or specialized use, but now wraps RuleManagerWidget)
    """
    def __init__(self, db_manager: DatabaseManager, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Auto-Tagging Rule Manager")
        self.resize(800, 600)
        
        layout = QVBoxLayout(self)
        self.widget = RuleManagerWidget(db_manager, self)
        layout.addWidget(self.widget)
        
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
