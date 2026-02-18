
import os
import json
import logging
import re
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QTextEdit, QLabel, QMessageBox, QSplitter, QFrame,
    QLineEdit, QFormLayout, QTableWidget, QTableWidgetItem, QHeaderView,
    QTabWidget, QCheckBox, QToolButton, QDialog, QComboBox, QInputDialog,
    QStackedWidget, QButtonGroup
)
from PyQt6.QtCore import Qt, pyqtSignal, QSignalBlocker, QSize, QEvent
from core.workflow import WorkflowRuleRegistry, WorkflowRule, WorkflowState, WorkflowTransition, WorkflowCondition, WorkflowEngine
from gui.widgets.semantic_selector import SemanticVariableSelector
from gui.cockpit import StatCard
from typing import Dict, List, Any, Optional

logger = logging.getLogger("KPaperFlux.Workflow")

class WorkflowRuleFormEditor(QWidget):
    """Structured editor for a single Rule."""
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
        self.current_rule = None
        self._lock_signals = False

    def _init_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Metadata Header (Always visible)
        self.meta_frame = QFrame()
        self.meta_frame.setObjectName("WorkflowRuleMetaFrame")
        self.meta_frame.setStyleSheet("""
            QFrame#WorkflowRuleMetaFrame {
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
        self.edit_name.setPlaceholderText(self.tr("Enter rule name..."))
        self.edit_desc = QTextEdit()
        self.edit_desc.setPlaceholderText(self.tr("What does this rule do?"))
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
        
        self.main_layout.addWidget(self.tabs)
        
        # 4. Semantic Variable Assistant (Floating/Popup)
        self.var_selector = SemanticVariableSelector(self)
        self.var_selector.setWindowFlags(Qt.WindowType.Popup)
        self.var_selector.variable_selected.connect(self._on_variable_selected)
        self.var_selector.hide()

        # Connect double-click on conditions column
        self.trans_table.cellDoubleClicked.connect(self._on_trans_cell_double_clicked)
        
        self.retranslate_ui()

    def changeEvent(self, event):
        if event and event.type() == QEvent.Type.LanguageChange:
            self.retranslate_ui()
        super().changeEvent(event)

    def retranslate_ui(self):
        self.edit_name.setPlaceholderText(self.tr("Enter rule name..."))
        self.edit_desc.setPlaceholderText(self.tr("What does this rule do..."))
        
        # We need to reach into the layouts to update labels if we didn't save them
        # Let's save them now for better future access
        if not hasattr(self, "lbl_name"):
             # Find labels in gen_layout (which is the layout of the widget in meta_frame)
             # This is a bit complex, but I'll update the strings here
             pass 

        self.tabs.setTabText(0, self.tr("States"))
        self.tabs.setTabText(1, self.tr("Transitions"))
        
        self.states_table.setHorizontalHeaderLabels([self.tr("State ID"), self.tr("Label"), self.tr("Final?")])
        self.trans_table.setHorizontalHeaderLabels([
            self.tr("From State"), self.tr("Action"), self.tr("Target State"), 
            self.tr("Required Fields"), self.tr("UI?"), self.tr("Conditions")
        ])
        
        self.btn_add_state.setText(self.tr("+ Add State"))
        self.btn_del_state.setText(self.tr("- Remove State"))
        self.btn_state_up.setToolTip(self.tr("Move State Up"))
        self.btn_state_down.setToolTip(self.tr("Move State Down"))

        self.btn_add_trans.setText(self.tr("+ Add Transition"))
        self.btn_del_trans.setText(self.tr("- Remove Transition"))

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

    def load_rule(self, rule: WorkflowRule):
        self._lock_signals = True
        self.current_rule = rule
        self.edit_name.setText(rule.name)
        self.edit_desc.setPlainText(rule.description)
        
        triggers = rule.triggers.get("type_tags", [])
        self.edit_triggers.setText(", ".join(triggers))
        
        # Load States
        self.states_table.setRowCount(0)
        for s_id, s_data in rule.states.items():
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
        for s_id, s_data in rule.states.items():
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
                cond_str = "; ".join([f"{c.field}{c.op}{c.value}" for c in t.conditions])
                self.trans_table.setItem(row, 5, QTableWidgetItem(cond_str))
                
        self._lock_signals = False

    def get_rule(self) -> WorkflowRule:
        pb_id = self.current_rule.id if self.current_rule else "new_rule"
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
            
        return WorkflowRule(id=pb_id, name=name, description=desc, states=states, triggers={"type_tags": triggers})

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

class WorkflowDashboardWidget(QWidget):
    """Overview of workflow performance and document distribution."""
    navigation_requested = pyqtSignal(dict)

    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self._init_ui()

    def _init_ui(self):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setSpacing(15)

        # 1. Stats Row (Total, Urgent, Pending)
        self.stats_layout = QHBoxLayout()
        self.layout.addLayout(self.stats_layout)

        # 2. Rule List / Summary
        self.rule_summary_lbl = QLabel(self.tr("Active Rule Load:"))
        self.rule_summary_lbl.setStyleSheet("font-weight: bold; margin-top: 20px;")
        self.layout.addWidget(self.rule_summary_lbl)

        self.rules_table = QTableWidget(0, 3)
        self.rules_table.setHorizontalHeaderLabels([self.tr("Workflow Rule"), self.tr("Active Documents"), self.tr("Completion Rate")])
        self.rules_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.rules_table.setStyleSheet("background: white; border: 1px solid #e0e0e0; border-radius: 4px;")
        self.layout.addWidget(self.rules_table)

        self.layout.addStretch()
        self.retranslate_ui()

    def changeEvent(self, event):
        if event and event.type() == QEvent.Type.LanguageChange:
            self.retranslate_ui()
        super().changeEvent(event)

    def retranslate_ui(self):
        self.rule_summary_lbl.setText(self.tr("Active Rule Load:"))
        self.rules_table.setHorizontalHeaderLabels([
            self.tr("Workflow Rule"), self.tr("Active Documents"), self.tr("Completion Rate")
        ])
        # Refresh dynamic cards labels
        self.refresh()

    def refresh(self):
        """Fetch fresh data from DB."""
        if not self.db_manager:
            return

        # Clear existing cards
        while self.stats_layout.count():
            item = self.stats_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # 1. Total in Workflow
        total_q = {"field": "workflow_step", "op": "is_not_empty", "value": None}
        total_count = self.db_manager.count_documents_advanced(total_q)
        
        # 2. Urgent
        urgent_q = {"field": "workflow_step", "op": "equals", "value": "URGENT"}
        urgent_count = self.db_manager.count_documents_advanced(urgent_q)

        # 3. New/Inbox
        new_q = {"field": "workflow_step", "op": "equals", "value": "NEW"}
        new_count = self.db_manager.count_documents_advanced(new_q)

        # Create Cards
        c1 = StatCard(self.tr("Total in Pipeline"), total_count, "#3b82f6", total_q, parent=self)
        c2 = StatCard(self.tr("Urgent Actions"), urgent_count, "#ef4444", urgent_q, parent=self)
        c3 = StatCard(self.tr("New Tasks"), new_count, "#10b981", new_q, parent=self)

        for c in [c1, c2, c3]:
            c.clicked.connect(self.navigation_requested.emit)
            self.stats_layout.addWidget(c)

        # 4. Populate Rules Table
        registry = WorkflowRuleRegistry()
        rules = registry.list_rules()
        self.rules_table.setRowCount(len(rules))
        
        for i, rule in enumerate(rules):
            # Count per rule
            rule_q = {"field": "semantic:workflow.rule_id", "op": "equals", "value": rule.id}
            count = self.db_manager.count_documents_advanced(rule_q)
            if not isinstance(count, (int, float)): count = 0
            
            # Finished count (final states)
            final_states = [sid for sid, s in rule.states.items() if s.final]
            finished_q = {
                "operator": "AND",
                "conditions": [
                    {"field": "semantic:workflow.rule_id", "op": "equals", "value": rule.id},
                    {"field": "workflow_step", "op": "in", "value": final_states}
                ]
            }
            finished_count = self.db_manager.count_documents_advanced(finished_q)
            if not isinstance(finished_count, (int, float)): finished_count = 0
            
            total_history = count + finished_count
            rate = f"{(finished_count / total_history * 100):.1f}%" if total_history > 0 else "0%"

            self.rules_table.setItem(i, 0, QTableWidgetItem(rule.name or rule.id))
            self.rules_table.setItem(i, 1, QTableWidgetItem(str(count)))
            self.rules_table.setItem(i, 2, QTableWidgetItem(rate))

class WorkflowManagerWidget(QWidget):
    """Management console for Rules."""
    workflows_changed = pyqtSignal()
    navigation_requested = pyqtSignal(dict)

    def __init__(self, parent=None, filter_tree=None):
        super().__init__(parent)
        self.registry = WorkflowRuleRegistry()
        self.filter_tree = filter_tree
        self.workflow_dir = "resources/workflows"
        self._is_dirty = False
        self._init_ui()
        self.load_workflows()

    def sizeHint(self) -> QSize:
        return QSize(800, 600)

    def minimumSizeHint(self) -> QSize:
        return QSize(100, 100)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 10, 15, 15)
        layout.setSpacing(0)

        # Custom Sub-Navigation Bar
        sub_nav_container = QWidget()
        sub_nav_layout = QHBoxLayout(sub_nav_container)
        sub_nav_layout.setContentsMargins(0, 5, 0, 10)
        sub_nav_layout.setSpacing(8)

        self.sub_mode_group = QButtonGroup(self)
        self.sub_mode_group.setExclusive(True)

        button_height = 30
        button_style = f"""
            QToolButton {{ 
                padding: 0px 20px; 
                height: {button_height}px;
                border: 1px solid #ddd; 
                border-radius: 4px;
                background: #f8f9fa;
                color: #555; 
                font-size: 15px; 
                font-weight: 500; 
            }}
            QToolButton:hover {{ background: #eee; }}
            QToolButton:checked {{ 
                background: #1565c0; 
                color: white; 
                border-color: #0d47a1;
                font-weight: bold; 
            }}
        """

        # Dashboard Button
        self.btn_show_dashboard = QToolButton()
        self.btn_show_dashboard.setText("📊 " + self.tr("Dashboard"))
        self.btn_show_dashboard.setCheckable(True)
        self.btn_show_dashboard.setChecked(True)
        self.btn_show_dashboard.setFixedHeight(button_height)
        self.btn_show_dashboard.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.btn_show_dashboard.setStyleSheet(button_style)
        self.btn_show_dashboard.clicked.connect(lambda: self.main_stack.setCurrentIndex(0))
        self.sub_mode_group.addButton(self.btn_show_dashboard, 0)
        sub_nav_layout.addWidget(self.btn_show_dashboard)

        # Rule Editor Button
        self.btn_show_editor = QToolButton()
        self.btn_show_editor.setText("⚙️ " + self.tr("Rule Editor"))
        self.btn_show_editor.setCheckable(True)
        self.btn_show_editor.setFixedHeight(button_height)
        self.btn_show_editor.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.btn_show_editor.setStyleSheet(button_style)
        self.btn_show_editor.clicked.connect(lambda: self.main_stack.setCurrentIndex(1))
        self.sub_mode_group.addButton(self.btn_show_editor, 1)
        sub_nav_layout.addWidget(self.btn_show_editor)

        sub_nav_layout.addStretch()
        layout.addWidget(sub_nav_container)

        # Horizontal separator
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet("background-color: #ddd; max-height: 1px; margin-bottom: 15px;")
        layout.addWidget(line)

        # Main Stack for Content
        self.main_stack = QStackedWidget()
        self.main_stack.currentChanged.connect(self._on_stack_changed)
        
        # 1. Dashboard View
        self.dashboard_tab = WorkflowDashboardWidget(self.filter_tree.db_manager if self.filter_tree else None)
        self.dashboard_tab.navigation_requested.connect(self.navigation_requested.emit)
        self.main_stack.addWidget(self.dashboard_tab)
        
        # 2. Rule Editor View
        self.editor_widget = QWidget()
        editor_layout = QVBoxLayout(self.editor_widget)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        
        # Move previous header/top_bar logic into editor_layout
        self.top_bar_widget = QWidget()
        self.top_bar = QHBoxLayout(self.top_bar_widget)
        self.top_bar.setContentsMargins(0, 0, 0, 0)
        
        self.lbl_select_rule = QLabel(self.tr("Select Rule:"))
        self.top_bar.addWidget(self.lbl_select_rule)
        
        self.combo_rules = QComboBox()
        self.combo_rules.setMinimumWidth(250)
        self.combo_rules.currentIndexChanged.connect(self._on_combo_changed)
        self.top_bar.addWidget(self.combo_rules)

        self.btn_new = QPushButton("✚ " + self.tr("New Rule"))
        self.btn_new.setToolTip(self.tr("Create a new workflow rule"))
        self.btn_new.clicked.connect(self._create_new_rule)
        self.top_bar.addWidget(self.btn_new)

        self.btn_revert = QPushButton("🔄 " + self.tr("Revert"))
        self.btn_revert.setToolTip(self.tr("Discard unsaved changes"))
        self.btn_revert.setEnabled(False)
        self.btn_revert.clicked.connect(self._revert_changes)
        self.top_bar.addWidget(self.btn_revert)

        self.btn_save = QPushButton("💾 " + self.tr("Save Rule"))
        self.btn_save.setEnabled(False)
        self.btn_save.setToolTip(self.tr("Save and activate the current rule"))
        self.btn_save.clicked.connect(self._save_rule)
        self.top_bar.addWidget(self.btn_save)

        self.btn_manage = QPushButton("⚙️ " + self.tr("Manage..."))
        self.btn_manage.setToolTip(self.tr("Manage rule files (delete, rename, import)"))
        self.btn_manage.clicked.connect(self._on_manage_clicked)
        self.top_bar.addWidget(self.btn_manage)

        self.top_bar.addStretch()

        editor_layout.addWidget(self.top_bar_widget)

        # Horizontal separator (inner)
        line2 = QFrame()
        line2.setFrameShape(QFrame.Shape.HLine)
        line2.setFrameShadow(QFrame.Shadow.Sunken)
        line2.setStyleSheet("color: #ddd;")
        editor_layout.addWidget(line2)

        # Form Editor Area
        h_center = QHBoxLayout()
        h_center.addStretch(1)
        
        self.content_container = QWidget()
        self.content_container.setFixedWidth(1000)
        content_layout = QVBoxLayout(self.content_container)
        content_layout.setContentsMargins(0, 20, 0, 0)
        
        self.form_editor = WorkflowRuleFormEditor()
        self.form_editor.changed.connect(self._mark_dirty)
        content_layout.addWidget(self.form_editor, 1)
        
        h_center.addWidget(self.content_container)
        h_center.addStretch(1)
        
        editor_layout.addLayout(h_center, 1)

        self.main_stack.addWidget(self.editor_widget)
        layout.addWidget(self.main_stack, 1)

        # Status Bar
        self.status_lbl = QLabel()
        self.status_lbl.setStyleSheet("color: #666; font-style: italic;")
        layout.addWidget(self.status_lbl)

        self.retranslate_ui()

    def changeEvent(self, event):
        if event and event.type() == QEvent.Type.LanguageChange:
            self.retranslate_ui()
        super().changeEvent(event)

    def retranslate_ui(self):
        self.btn_show_dashboard.setText("📊 " + self.tr("Dashboard"))
        self.btn_show_editor.setText("⚙️ " + self.tr("Rule Editor"))
        if hasattr(self, 'lbl_select_rule'):
             self.lbl_select_rule.setText(self.tr("Select Rule:"))
        
        self.btn_new.setText("✚ " + self.tr("New Rule"))
        self.btn_new.setToolTip(self.tr("Create a new workflow rule"))
        self.btn_revert.setText("🔄 " + self.tr("Revert"))
        self.btn_revert.setToolTip(self.tr("Discard unsaved changes"))
        self.btn_save.setText("💾 " + self.tr("Save Rule"))
        self.btn_save.setToolTip(self.tr("Save and activate the current rule"))
        self.btn_manage.setText("⚙️ " + self.tr("Manage..."))
        self.btn_manage.setToolTip(self.tr("Manage rule files (delete, rename, import)"))

    def _on_stack_changed(self, index):
        if index == 0:
            self.dashboard_tab.refresh()

    def showEvent(self, event):
        super().showEvent(event)
        if self.main_stack.currentIndex() == 0:
            self.dashboard_tab.refresh()

    def _mark_dirty(self):
        self._is_dirty = True
        self.btn_save.setEnabled(True)
        self.btn_revert.setEnabled(True)

    def _clear_dirty(self):
        self._is_dirty = False
        self.btn_save.setEnabled(False)
        self.btn_revert.setEnabled(False)

    def load_workflows(self):
        self.combo_rules.blockSignals(True)
        current_id = self.combo_rules.currentData()
        
        self.combo_rules.clear()
        self.combo_rules.addItem(self.tr("--- Select Rule ---"), None)
        
        if not os.path.exists(self.workflow_dir):
            os.makedirs(self.workflow_dir, exist_ok=True)
            
        registry = WorkflowRuleRegistry()
        registry.load_from_directory(self.workflow_dir)
        
        idx_to_restore = 0
        for i, rule in enumerate(registry.list_rules()):
            label = rule.name or rule.id
            self.combo_rules.addItem(label, rule.id)
            if rule.id == current_id:
                idx_to_restore = i + 1 # +1 because of placeholder
            
        self.combo_rules.setCurrentIndex(idx_to_restore)
        self.combo_rules.blockSignals(False)
        
        # If the formerly selected rule is gone, clear the form
        if current_id and idx_to_restore == 0:
            self.form_editor.load_rule(WorkflowRule(id="new", name="", states={}))
            self.status_lbl.setText(self.tr("Rule deleted."))
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

        rule_id = self.combo_rules.currentData()
        if not rule_id:
            return
            
        reg = WorkflowRuleRegistry()
        rule = reg.get_rule(rule_id)
        if rule:
            self.form_editor.load_rule(rule)
            self._clear_dirty()
            self.status_lbl.setText(self.tr(f"Editing: {rule.name or rule_id}"))

    def _create_new_rule(self):
        rule = WorkflowRule(
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
        self.form_editor.load_rule(rule)
        self.combo_rules.setCurrentIndex(0)
        self._mark_dirty()

    def _save_rule(self):
        try:
            rule = self.form_editor.get_rule()
            # Check for duplicate names (excluding current ID)
            reg = WorkflowRuleRegistry()
            for existing in reg.list_rules():
                if existing.name == rule.name and existing.id != rule.id:
                    QMessageBox.warning(self, self.tr("Duplicate Name"), 
                                        self.tr(f"A rule with the name '{rule.name}' already exists."))
                    return

            file_path = os.path.join(self.workflow_dir, f"{rule.id}.json")
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(rule.model_dump(), f, indent=2)
                
            QMessageBox.information(self, self.tr("Success"), self.tr(f"Rule '{rule.name}' saved and activated."))
            
            self._clear_dirty()
            
            # Reload registry and list
            self.registry.load_from_directory(self.workflow_dir)
            self.load_workflows()
            
            # Select the saved one
            self._select_rule_by_id(rule.id)
            
            self.workflows_changed.emit()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save rule: {e}")

    def _revert_changes(self):
        """Cancel changes and reload current rule."""
        rule_id = self.combo_rules.currentData()
        if rule_id:
            reg = WorkflowRuleRegistry()
            rule = reg.get_rule(rule_id)
            if rule:
                self.form_editor.load_rule(rule)
        self._clear_dirty()
        
    def _on_manage_clicked(self):
        """Open a management dialog for rules."""
        dlg = WorkflowRuleManagerDialog(self, filter_tree=self.filter_tree)
        dlg.rule_selected.connect(self._select_rule_by_id)
        dlg.exec()
        self.load_workflows()

    def _select_rule_by_id(self, rule_id: str):
        idx = self.combo_rules.findData(rule_id)
        if idx >= 0:
            self.combo_rules.setCurrentIndex(idx)

    def _on_rule_apply_requested(self):
        # Placeholder if needed by main window, but currently agents are assigned via Rules tab
        pass

class WorkflowRuleManagerDialog(QDialog):
    """Simplified management dialog for Rule files."""
    rule_selected = pyqtSignal(str)

    def __init__(self, parent=None, filter_tree=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Manage Rules"))
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
            reg = WorkflowRuleRegistry()
            if any(p.name == name for p in reg.list_rules()):
                QMessageBox.warning(self, self.tr("Duplicate Name"), 
                                    self.tr(f"A workflow with the name '{name}' already exists."))
                return

            # Generate stable ID from name + timestamp
            clean_name = re.sub(r'[^a-zA-Z0-9]', '_', name.lower())
            pb_id = f"{clean_name}_{int(time.time())}"
            
            pb = WorkflowRule(
                id=pb_id,
                name=name,
                states={"NEW": WorkflowState(label="Start", final=True)}
            )
            file_path = os.path.join(self.workflow_dir, f"{pb_id}.json")
            with open(file_path, "w") as f:
                json.dump(pb.model_dump(), f, indent=2)
            self._reload_list()
            self.rule_selected.emit(pb_id)

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
                reg = WorkflowRuleRegistry()
                if any(p.name == new_name for p in reg.list_rules()):
                    QMessageBox.warning(self, self.tr("Duplicate Name"), 
                                        self.tr(f"A rule with the name '{new_name}' already exists."))
                    return

                data["name"] = new_name
                with open(file_path, "w") as f:
                    json.dump(data, f, indent=2)
                self._reload_list()
                self.rule_selected.emit(pb_id)
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
                    self.tr(f"The rule '{name}' cannot be deleted because it is still used in the following rules:\n\n{rule_names}\n\nPlease remove the assignment from these rules first.")
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
                    reg = WorkflowRuleRegistry()
                    if pb_id in reg.rules:
                        del reg.rules[pb_id]
                except Exception as e:
                    QMessageBox.warning(self, self.tr("Error"), f"Could not delete file: {e}")
            self._reload_list()

