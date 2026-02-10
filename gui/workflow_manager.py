
import os
import json
import logging
import re
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QTextEdit, QLabel, QMessageBox, QSplitter, QFrame,
    QLineEdit, QFormLayout, QTableWidget, QTableWidgetItem, QHeaderView,
    QTabWidget, QCheckBox, QToolButton, QDialog, QComboBox, QInputDialog
)
from PyQt6.QtCore import Qt, pyqtSignal, QSignalBlocker
from core.workflow import WorkflowRegistry, WorkflowPlaybook, WorkflowState, WorkflowTransition, WorkflowCondition
from gui.widgets.semantic_selector import SemanticVariableSelector
from typing import Dict, List, Any, Optional

logger = logging.getLogger("KPaperFlux.Workflow")

class WorkflowFormEditor(QWidget):
    """Structured editor for a single Workflow Playbook."""
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
        self.current_pb = None
        self._lock_signals = False

    def _init_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Metadata Header (Always visible)
        self.meta_frame = QFrame()
        self.meta_frame.setObjectName("AgentMetaFrame")
        self.meta_frame.setStyleSheet("""
            QFrame#AgentMetaFrame {
                background: #fdfdfd; 
                border: 1px solid #e0e0e0; 
                border-radius: 6px;
                margin-bottom: 15px;
            }
        """)
        meta_inner_layout = QVBoxLayout(self.meta_frame)
        
        gen_layout = QFormLayout()
        gen_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        gen_layout.setSpacing(10)
        
        self.edit_name = QLineEdit()
        self.edit_name.setPlaceholderText(self.tr("Enter agent name..."))
        self.edit_desc = QTextEdit()
        self.edit_desc.setPlaceholderText(self.tr("What does this agent do?"))
        self.edit_desc.setMaximumHeight(60)
        self.edit_triggers = QLineEdit()
        self.edit_triggers.setPlaceholderText("INVOICE, TELEKOM, ...")
        
        self.edit_name.textChanged.connect(self._on_changed)
        self.edit_desc.textChanged.connect(self._on_changed)
        self.edit_triggers.textChanged.connect(self._on_changed)
        
        gen_layout.addRow(self.tr("Display Name:"), self.edit_name)
        gen_layout.addRow(self.tr("Description:"), self.edit_desc)
        gen_layout.addRow(self.tr("Auto-Trigger Tags:"), self.edit_triggers)
        
        meta_inner_layout.addLayout(gen_layout)
        self.main_layout.addWidget(self.meta_frame)
        
        # Tabs only for logic (States/Transitions)
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("QTabWidget::pane { border: 1px solid #e0e0e0; background: white; }")
        
        # 2. States Tab
        self.states_tab = QWidget()
        states_layout = QVBoxLayout(self.states_tab)
        
        self.states_table = QTableWidget(0, 3)
        self.states_table.setHorizontalHeaderLabels(["State ID", "Label", "Final?"])
        self.states_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.states_table.itemChanged.connect(self._on_changed)
        states_layout.addWidget(self.states_table)
        
        btn_s_layout = QHBoxLayout()
        self.btn_add_state = QPushButton("+ Add State")
        self.btn_add_state.clicked.connect(self._add_state_row)
        self.btn_del_state = QPushButton("- Remove State")
        self.btn_del_state.clicked.connect(self._remove_selected_state)
        
        self.btn_state_up = QToolButton()
        self.btn_state_up.setText("▲")
        self.btn_state_up.setToolTip("Move State Up")
        self.btn_state_up.clicked.connect(lambda: self._move_row(self.states_table, -1))
        
        self.btn_state_down = QToolButton()
        self.btn_state_down.setText("▼")
        self.btn_state_down.setToolTip("Move State Down")
        self.btn_state_down.clicked.connect(lambda: self._move_row(self.states_table, 1))
        
        btn_s_layout.addWidget(self.btn_add_state)
        btn_s_layout.addWidget(self.btn_del_state)
        btn_s_layout.addStretch()
        btn_s_layout.addWidget(self.btn_state_up)
        btn_s_layout.addWidget(self.btn_state_down)
        states_layout.addLayout(btn_s_layout)
        
        self.tabs.addTab(self.states_tab, "States")
        
        # 3. Transitions Tab
        self.trans_tab = QWidget()
        trans_layout = QVBoxLayout(self.trans_tab)
        
        self.trans_table = QTableWidget(0, 6)
        self.trans_table.setHorizontalHeaderLabels(["From State", "Action", "Target State", "Required Fields", "UI?", "Conditions"])
        self.trans_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.trans_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive) # Conditions can be long
        self.trans_table.setColumnWidth(5, 200)
        self.trans_table.itemChanged.connect(self._on_changed)
        trans_layout.addWidget(self.trans_table)
        
        btn_t_layout = QHBoxLayout()
        self.btn_add_trans = QPushButton("+ Add Transition")
        self.btn_add_trans.clicked.connect(self._add_trans_row)
        self.btn_del_trans = QPushButton("- Remove Transition")
        self.btn_del_trans.clicked.connect(self._remove_selected_trans)
        
        self.btn_trans_up = QToolButton()
        self.btn_trans_up.setText("▲")
        self.btn_trans_up.clicked.connect(lambda: self._move_row(self.trans_table, -1))
        
        self.btn_trans_down = QToolButton()
        self.btn_trans_down.setText("▼")
        self.btn_trans_down.clicked.connect(lambda: self._move_row(self.trans_table, 1))
        
        btn_t_layout.addWidget(self.btn_add_trans)
        btn_t_layout.addWidget(self.btn_del_trans)
        btn_t_layout.addStretch()
        btn_t_layout.addWidget(self.btn_trans_up)
        btn_t_layout.addWidget(self.btn_trans_down)
        trans_layout.addLayout(btn_t_layout)
        
        self.tabs.addTab(self.trans_tab, "Transitions")

        # 4. Semantic Variable Assistant (Floating/Popup)
        self.var_selector = SemanticVariableSelector(self)
        self.var_selector.setWindowFlags(Qt.WindowType.Popup)
        self.var_selector.variable_selected.connect(self._on_variable_selected)
        self.var_selector.hide()

        # Connect double-click on conditions column
        self.trans_table.cellDoubleClicked.connect(self._on_trans_cell_double_clicked)

        self.main_layout.addWidget(self.tabs)

    def _on_changed(self):
        if not self._lock_signals:
            self.changed.emit()

    def _on_trans_cell_double_clicked(self, row, col):
        """Show variable assistant for conditions column."""
        if col == 5: # Conditions Column
            pos = self.trans_table.mapToGlobal(self.trans_table.visualItemRect(self.trans_table.item(row, col)).bottomLeft())
            self.var_selector.move(pos)
            self.var_selector.show()
            self.var_selector.search_bar.setFocus()

    def _on_variable_selected(self, var_id):
        """Inserts the selected variable into the currently edited cell."""
        row = self.trans_table.currentRow()
        col = self.trans_table.currentColumn()
        if row >= 0 and col == 5:
            item = self.trans_table.item(row, col)
            if item:
                current_text = item.text().strip()
                # Append or insert (simple append for now)
                new_text = f"{current_text} {var_id}" if current_text else var_id
                item.setText(new_text.strip())
                self._on_changed()

    def load_playbook(self, pb: WorkflowPlaybook):
        self._lock_signals = True
        self.current_pb = pb
        self.edit_name.setText(pb.name)
        self.edit_desc.setPlainText(pb.description)
        
        triggers = pb.triggers.get("type_tags", [])
        self.edit_triggers.setText(", ".join(triggers))
        
        # Load States
        self.states_table.setRowCount(0)
        for s_id, s_data in pb.states.items():
            row = self.states_table.rowCount()
            self.states_table.insertRow(row)
            self.states_table.setItem(row, 0, QTableWidgetItem(s_id))
            self.states_table.setItem(row, 1, QTableWidgetItem(s_data.label))
            
            chk = QCheckBox()
            chk.setChecked(s_data.final)
            chk.stateChanged.connect(self._on_changed)
            self.states_table.setCellWidget(row, 2, chk)
            
        # Load Transitions
        self.trans_table.setRowCount(0)
        for s_id, s_data in pb.states.items():
            for t in s_data.transitions:
                row = self.trans_table.rowCount()
                self.trans_table.insertRow(row)
                self.trans_table.setItem(row, 0, QTableWidgetItem(s_id))
                self.trans_table.setItem(row, 1, QTableWidgetItem(t.action))
                self.trans_table.setItem(row, 2, QTableWidgetItem(t.target))
                self.trans_table.setItem(row, 3, QTableWidgetItem(", ".join(t.required_fields)))
                
                chk_ui = QCheckBox()
                chk_ui.setChecked(t.user_interaction)
                chk_ui.stateChanged.connect(self._on_changed)
                self.trans_table.setCellWidget(row, 4, chk_ui)
                
                # Conditions (Phase 112)
                cond_str = "; ".join([f"{c.field} {c.op} {c.value}" for c in t.conditions])
                self.trans_table.setItem(row, 5, QTableWidgetItem(cond_str))
                
        self._lock_signals = False

    def get_playbook(self) -> WorkflowPlaybook:
        pb_id = self.current_pb.id if self.current_pb else "new_agent"
        name = self.edit_name.text().strip()
        desc = self.edit_desc.toPlainText().strip()
        triggers = [t.strip() for t in self.edit_triggers.text().split(",") if t.strip()]
        
        states = {}
        # 1. First Pass: Create States
        for r in range(self.states_table.rowCount()):
            item_id = self.states_table.item(r, 0)
            if not item_id: continue
            s_id = item_id.text().strip()
            if not s_id: continue
            
            label_item = self.states_table.item(r, 1)
            label = label_item.text().strip() if label_item else s_id
            
            final_widget = self.states_table.cellWidget(r, 2)
            final = final_widget.isChecked() if isinstance(final_widget, QCheckBox) else False
            
            states[s_id] = WorkflowState(label=label, final=final, transitions=[])
            
        # 2. Second Pass: Add Transitions
        for r in range(self.trans_table.rowCount()):
            from_item = self.trans_table.item(r, 0)
            if not from_item: continue
            from_s = from_item.text().strip()
            if from_s not in states: continue
            
            action_item = self.trans_table.item(r, 1)
            action = action_item.text().strip() if action_item else "unnamed_action"
            
            target_item = self.trans_table.item(r, 2)
            target = target_item.text().strip() if target_item else from_s
            
            req_item = self.trans_table.item(r, 3)
            req_str = req_item.text().strip() if req_item else ""
            req = [f.strip() for f in req_str.split(",") if f.strip()]
            
            ui_widget = self.trans_table.cellWidget(r, 4)
            ui = ui_widget.isChecked() if isinstance(ui_widget, QCheckBox) else False
            
            # Conditions parsing (Phase 112)
            cond_item = self.trans_table.item(r, 5)
            cond_str = cond_item.text().strip() if cond_item else ""
            conditions = []
            if cond_str:
                for chunk in cond_str.split(";"):
                    chunk = chunk.strip()
                    if not chunk: continue
                    # regex to split field, op, value securely
                    parts = re.split(r'\s*([>=<!]+)\s*', chunk, 1)
                    if len(parts) == 3:
                        conditions.append(WorkflowCondition(
                            field=parts[0].strip(),
                            op=parts[1].strip(),
                            value=parts[2].strip()
                        ))
            
            trans = WorkflowTransition(action=action, target=target, required_fields=req, user_interaction=ui, conditions=conditions)
            states[from_s].transitions.append(trans)
            
        return WorkflowPlaybook(id=pb_id, name=name, description=desc, states=states, triggers={"type_tags": triggers})

    def _add_state_row(self):
        self._lock_signals = True
        row = self.states_table.rowCount()
        self.states_table.insertRow(row)
        self.states_table.setItem(row, 0, QTableWidgetItem(f"STATE_{row}"))
        self.states_table.setItem(row, 1, QTableWidgetItem("New State"))
        chk = QCheckBox()
        chk.stateChanged.connect(self._on_changed)
        self.states_table.setCellWidget(row, 2, chk)
        self._lock_signals = False
        self._on_changed()

    def _remove_selected_state(self):
        row = self.states_table.currentRow()
        if row >= 0:
            self.states_table.removeRow(row)
            self._on_changed()

    def _add_trans_row(self):
        self._lock_signals = True
        row = self.trans_table.rowCount()
        self.trans_table.insertRow(row)
        from_val = "NEW"
        selected_states = self.states_table.selectedItems()
        if selected_states:
            from_val = self.states_table.item(selected_states[0].row(), 0).text()
            
        self.trans_table.setItem(row, 0, QTableWidgetItem(from_val))
        self.trans_table.setItem(row, 1, QTableWidgetItem("action"))
        self.trans_table.setItem(row, 2, QTableWidgetItem("TARGET"))
        self.trans_table.setItem(row, 3, QTableWidgetItem(""))
        chk = QCheckBox()
        chk.stateChanged.connect(self._on_changed)
        self.trans_table.setCellWidget(row, 4, chk)
        
        self.trans_table.setItem(row, 5, QTableWidgetItem(""))
        self._lock_signals = False
        self._on_changed()

    def _remove_selected_trans(self):
        row = self.trans_table.currentRow()
        if row >= 0:
            self.trans_table.removeRow(row)
            self._on_changed()

    def _move_row(self, table: QTableWidget, direction: int):
        """Move selected row up (-1) or down (1)."""
        row = table.currentRow()
        if row < 0: return
        
        target = row + direction
        if target < 0 or target >= table.rowCount():
            return

        self._lock_signals = True
        # Swap row contents
        for col in range(table.columnCount()):
            # Item swap
            item = table.takeItem(row, col)
            target_item = table.takeItem(target, col)
            table.setItem(row, col, target_item)
            table.setItem(target, col, item)
            
            # Widget swap (for CheckBoxes)
            widget = table.cellWidget(row, col)
            target_widget = table.cellWidget(target, col)
            
            # Re-creating widgets is safer in Qt than re-setting them if they lose context
            # But let's try simple swap first
            if widget or target_widget:
                table.setCellWidget(row, col, None)
                table.setCellWidget(target, col, None)
                if widget: table.setCellWidget(target, col, widget)
                if target_widget: table.setCellWidget(row, col, target_widget)

        table.setCurrentCell(target, 0)
        self._lock_signals = False
        self._on_changed()

class WorkflowManagerWidget(QWidget):
    """Management console for Workflow Playbooks."""
    workflows_changed = pyqtSignal()

    def __init__(self, parent=None, filter_tree=None):
        super().__init__(parent)
        self.registry = WorkflowRegistry()
        self.filter_tree = filter_tree
        self.workflow_dir = "resources/workflows"
        self._is_dirty = False
        self._init_ui()
        self.load_workflows()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        # Header Title
        title_lbl = QLabel(self.tr("Manage Agents"))
        title_lbl.setStyleSheet("font-size: 18px; font-weight: bold; color: #1565c0;")
        layout.addWidget(title_lbl)

        # Harmonized Top Bar
        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel(self.tr("Select Agent:")))
        
        self.combo_agents = QComboBox()
        self.combo_agents.currentIndexChanged.connect(self._on_combo_changed)
        top_bar.addWidget(self.combo_agents, 1)

        self.btn_revert = QPushButton(self.tr("Revert"))
        self.btn_revert.setEnabled(False)
        self.btn_revert.clicked.connect(self._revert_changes)
        top_bar.addWidget(self.btn_revert)

        self.btn_save = QPushButton(self.tr("Save Agent"))
        self.btn_save.setEnabled(False)
        self.btn_save.setStyleSheet("background-color: #2e7d32; color: white; font-weight: bold;")
        self.btn_save.clicked.connect(self._save_playbook)
        top_bar.addWidget(self.btn_save)

        self.btn_manage = QPushButton(self.tr("Manage..."))
        self.btn_manage.clicked.connect(self._on_manage_clicked)
        top_bar.addWidget(self.btn_manage)

        layout.addLayout(top_bar)

        # Horizontal separator
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet("color: #ddd;")
        layout.addWidget(line)

        # Form Editor Area
        # Centered Content Wrapper
        h_center = QHBoxLayout()
        h_center.addStretch(1)
        
        self.content_container = QWidget()
        self.content_container.setFixedWidth(1000) # Balanced width for FHD screens
        content_layout = QVBoxLayout(self.content_container)
        content_layout.setContentsMargins(0, 0, 0, 0)
        
        self.form_editor = WorkflowFormEditor()
        self.form_editor.changed.connect(self._mark_dirty)
        content_layout.addWidget(self.form_editor, 1)
        
        h_center.addWidget(self.content_container)
        h_center.addStretch(1)
        
        layout.addLayout(h_center, 1)

        # Status Bar
        self.status_lbl = QLabel()
        self.status_lbl.setStyleSheet("color: #666; font-style: italic;")
        layout.addWidget(self.status_lbl)

    def _mark_dirty(self):
        self._is_dirty = True
        self.btn_save.setEnabled(True)
        self.btn_revert.setEnabled(True)

    def _clear_dirty(self):
        self._is_dirty = False
        self.btn_save.setEnabled(False)
        self.btn_revert.setEnabled(False)

    def load_workflows(self):
        self.combo_agents.blockSignals(True)
        current_id = self.combo_agents.currentData()
        
        self.combo_agents.clear()
        self.combo_agents.addItem(self.tr("--- Select Agent ---"), None)
        
        if not os.path.exists(self.workflow_dir):
            os.makedirs(self.workflow_dir, exist_ok=True)
            
        registry = WorkflowRegistry()
        registry.load_from_directory(self.workflow_dir)
        
        idx_to_restore = 0
        for i, pb in enumerate(registry.list_playbooks()):
            label = pb.name or pb.id
            self.combo_agents.addItem(label, pb.id)
            if pb.id == current_id:
                idx_to_restore = i + 1 # +1 because of placeholder
            
        self.combo_agents.setCurrentIndex(idx_to_restore)
        self.combo_agents.blockSignals(False)
        
        # If the formerly selected agent is gone, clear the form
        if current_id and idx_to_restore == 0:
            self.form_editor.load_playbook(WorkflowPlaybook(id="new", name="", states={}))
            self.status_lbl.setText(self.tr("Agent deleted."))
            self._clear_dirty()

    def _on_combo_changed(self, index):
        if self._is_dirty:
            reply = QMessageBox.question(
                self, self.tr("Unsaved Changes"),
                self.tr("You have unsaved changes. Discard them?"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                # Revert selection
                self.load_workflows() # Quick fix to reset selection
                return

        pb_id = self.combo_agents.currentData()
        if not pb_id:
            return
            
        reg = WorkflowRegistry()
        pb = reg.get_playbook(pb_id)
        if pb:
            self.form_editor.load_playbook(pb)
            self._clear_dirty()
            self.status_lbl.setText(self.tr(f"Editing: {pb.name or pb_id}"))

    def _create_new_playbook(self):
        pb = WorkflowPlaybook(
            id="new_workflow",
            name="New Workflow",
            description="Generated via GUI",
            states={
                "NEW": WorkflowState(label="Start", transitions=[
                    WorkflowTransition(action="verify", target="DONE")
                ]),
                "DONE": WorkflowState(label="Done", final=True)
            },
            triggers={"type_tags": ["NEW_TAG"]}
        )
        self.form_editor.load_playbook(pb)
        self.combo_agents.setCurrentIndex(0)
        self._mark_dirty()

    def _save_playbook(self):
        try:
            pb = self.form_editor.get_playbook()
            # Check for duplicate names (excluding current ID)
            reg = WorkflowRegistry()
            for existing in reg.list_playbooks():
                if existing.name == pb.name and existing.id != pb.id:
                    QMessageBox.warning(self, self.tr("Duplicate Name"), 
                                        self.tr(f"An agent with the name '{pb.name}' already exists."))
                    return

            file_path = os.path.join(self.workflow_dir, f"{pb.id}.json")
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(pb.model_dump(), f, indent=2)
                
            QMessageBox.information(self, self.tr("Success"), self.tr(f"Agent '{pb.name}' saved and activated."))
            
            self._clear_dirty()
            
            # Reload registry and list
            self.registry.load_from_directory(self.workflow_dir)
            self.load_workflows()
            
            # Select the saved one
            self._select_agent_by_id(pb.id)
            
            self.workflows_changed.emit()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save playbook: {e}")

    def _revert_changes(self):
        """Cancel changes and reload current agent."""
        pb_id = self.combo_agents.currentData()
        if pb_id:
            reg = WorkflowRegistry()
            pb = reg.get_playbook(pb_id)
            if pb:
                self.form_editor.load_playbook(pb)
        self._clear_dirty()
        
    def _on_manage_clicked(self):
        """Open a management dialog for agents."""
        dlg = AgentManagerDialog(self, filter_tree=self.filter_tree)
        dlg.agent_selected.connect(self._select_agent_by_id)
        dlg.exec()
        self.load_workflows()

    def _select_agent_by_id(self, pb_id: str):
        idx = self.combo_agents.findData(pb_id)
        if idx >= 0:
            self.combo_agents.setCurrentIndex(idx)

    def _on_rule_apply_requested(self):
        # Placeholder if needed by main window, but currently agents are assigned via Rules tab
        pass

class AgentManagerDialog(QDialog):
    """Simplified management dialog for Agent files."""
    agent_selected = pyqtSignal(str)

    def __init__(self, parent=None, filter_tree=None):
        super().__init__(parent)
        self.setWindowTitle("Manage Agents")
        self.resize(400, 500)
        self.workflow_dir = "resources/workflows"
        self.filter_tree = filter_tree
        self._init_ui()
        self._reload_list()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget)
        
        btn_row = QHBoxLayout()
        self.btn_new = QPushButton(self.tr("New..."))
        self.btn_new.clicked.connect(self._create_new)
        
        self.btn_rename = QPushButton(self.tr("Rename..."))
        self.btn_rename.setToolTip(self.tr("Change display name only (ID remains fixed)"))
        self.btn_rename.clicked.connect(self._rename_display_name)
        
        self.btn_delete = QPushButton(self.tr("Delete"))
        self.btn_delete.clicked.connect(self._delete_selected)
        
        btn_row.addWidget(self.btn_new)
        btn_row.addWidget(self.btn_rename)
        btn_row.addWidget(self.btn_delete)
        layout.addLayout(btn_row)
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    def _reload_list(self):
        self.list_widget.clear()
        if os.path.exists(self.workflow_dir):
            for f in sorted(os.listdir(self.workflow_dir)):
                if f.endswith(".json"):
                    file_path = os.path.join(self.workflow_dir, f)
                    try:
                        with open(file_path, "r") as jf:
                            data = json.load(jf)
                            pb_id = data.get("id", f.replace(".json", ""))
                            name = data.get("name", pb_id)
                            item = QListWidgetItem(name)
                            item.setData(Qt.ItemDataRole.UserRole, pb_id)
                            self.list_widget.addItem(item)
                    except:
                        self.list_widget.addItem(f.replace(".json", ""))

    def _create_new(self):
        import time, re
        name, ok = QInputDialog.getText(self, self.tr("New Workflow"), self.tr("Enter display name:"))
        if ok and name:
            name = name.strip()
            # Check for duplicates
            reg = WorkflowRegistry()
            if any(p.name == name for p in reg.list_playbooks()):
                QMessageBox.warning(self, self.tr("Duplicate Name"), 
                                    self.tr(f"A workflow with the name '{name}' already exists."))
                return

            # Generate stable ID from name + timestamp
            clean_name = re.sub(r'[^a-zA-Z0-9]', '_', name.lower())
            pb_id = f"{clean_name}_{int(time.time())}"
            
            pb = WorkflowPlaybook(
                id=pb_id,
                name=name,
                states={"NEW": WorkflowState(label="Start", final=True)}
            )
            file_path = os.path.join(self.workflow_dir, f"{pb_id}.json")
            with open(file_path, "w") as f:
                json.dump(pb.model_dump(), f, indent=2)
            self._reload_list()
            self.agent_selected.emit(pb_id)

    def _rename_display_name(self):
        item = self.list_widget.currentItem()
        if not item: return
        pb_id = item.data(Qt.ItemDataRole.UserRole)
        
        file_path = os.path.join(self.workflow_dir, f"{pb_id}.json")
        try:
            with open(file_path, "r") as f:
                data = json.load(f)
                old_name = data.get("name", pb_id)
                
            new_name, ok = QInputDialog.getText(self, self.tr("Rename Workflow"), self.tr("New display name:"), QLineEdit.EchoMode.Normal, old_name)
            if ok and new_name:
                new_name = new_name.strip()
                if new_name == old_name: return
                
                # Duplicate check
                reg = WorkflowRegistry()
                if any(p.name == new_name for p in reg.list_playbooks()):
                    QMessageBox.warning(self, self.tr("Duplicate Name"), 
                                        self.tr(f"An agent with the name '{new_name}' already exists."))
                    return

                data["name"] = new_name
                with open(file_path, "w") as f:
                    json.dump(data, f, indent=2)
                self._reload_list()
                self.agent_selected.emit(pb_id)
        except Exception as e:
            QMessageBox.critical(self, self.tr("Error"), str(e))

    def _delete_selected(self):
        item = self.list_widget.currentItem()
        if not item: return
        pb_id = item.data(Qt.ItemDataRole.UserRole)
        name = item.text()
        
        # Safety Check: Is this agent still used in any rules?
        if self.filter_tree:
            usages = self.filter_tree.find_workflow_usages(pb_id)
            if usages:
                rule_names = ", ".join([node.name for node in usages])
                QMessageBox.critical(
                    self, self.tr("Workflow in Use"),
                    self.tr(f"The agent '{name}' cannot be deleted because it is still used in the following rules:\n\n{rule_names}\n\nPlease remove the assignment from these rules first.")
                )
                return

        reply = QMessageBox.question(self, self.tr("Delete Workflow"), self.tr(f"Are you sure you want to delete the workflow '{name}'?"), 
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            file_path = os.path.join(self.workflow_dir, f"{pb_id}.json")
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    # Also remove from registry if active
                    reg = WorkflowRegistry()
                    if pb_id in reg.playbooks:
                        del reg.playbooks[pb_id]
                except Exception as e:
                    QMessageBox.warning(self, self.tr("Error"), f"Could not delete file: {e}")
            self._reload_list()

