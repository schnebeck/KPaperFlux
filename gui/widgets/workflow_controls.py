import logging
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel, QVBoxLayout
from PyQt6.QtCore import pyqtSignal, Qt
from core.workflow import WorkflowRuleRegistry, WorkflowEngine, WorkflowState
from typing import Dict, Any, Optional

logger = logging.getLogger("KPaperFlux.WorkflowUI")

class WorkflowControlsWidget(QWidget):
    """Dynamic UI component for document workflow transitions."""
    transition_triggered = pyqtSignal(str, str, bool) # action, target_state, is_auto
    rule_changed = pyqtSignal(str) # new rule_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.registry = WorkflowRuleRegistry()
        self.rule_id = None
        self.current_step = "NEW"
        self.document_data = {}
        self._init_ui()

    def _init_ui(self):
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(8)
        
        self.status_lbl = QLabel()
        self.status_lbl.setStyleSheet("font-weight: bold; color: #1976d2;")
        self.layout.addWidget(self.status_lbl)
        
        self.buttons_container = QWidget()
        self.buttons_layout = QHBoxLayout(self.buttons_container)
        self.buttons_layout.setSpacing(5)
        self.layout.addWidget(self.buttons_container)

        self.btn_change = QPushButton("⚙️")
        self.btn_change.setToolTip(self.tr("Change/Assign Rule"))
        self.btn_change.setFixedWidth(32)
        self.btn_change.setFixedHeight(28)
        self.btn_change.setStyleSheet("""
            QPushButton { 
                background: #f8f9fa; 
                border: 1px solid #ccc; 
                border-radius: 4px;
                color: #555;
                font-size: 14px;
            }
            QPushButton:hover { background: #eee; border-color: #bbb; }
        """)
        self.btn_change.clicked.connect(self._show_assignment_menu)
        self.layout.addWidget(self.btn_change)

        self.layout.addStretch()

    def update_workflow(self, rule_id: Optional[str], current_step: str, document_data: Dict[str, Any]):
        """Refreshes the control buttons based on current state and data."""
        self.rule_id = rule_id
        self.current_step = current_step
        self.document_data = document_data
        
        # Clear existing buttons
        for i in reversed(range(self.buttons_layout.count())): 
            self.buttons_layout.itemAt(i).widget().setParent(None)
            
        if not self.rule_id:
            self.status_lbl.setText(self.tr("No Workflow"))
            return

        rule = self.registry.get_rule(self.rule_id)
        if not rule:
            self.status_lbl.setText(self.tr("Rule '%s' missing") % self.rule_id)
            return

        engine = WorkflowEngine(rule)
        
        # 113: Auto-Transition Check
        auto_target = engine.get_auto_transition(self.current_step, self.document_data)
        if auto_target:
            # Find the action name for the auto-transition
            state_def = rule.states.get(self.current_step)
            auto_action = next((t.action for t in state_def.transitions if t.auto and t.target == auto_target), "auto")
            logger.info(f"[Workflow-UI] Triggering auto-transition '{auto_action}' to {auto_target}")
            self.transition_triggered.emit(auto_action, auto_target, True)
            return

        state_def = rule.states.get(self.current_step)
        
        label = state_def.label if state_def else self.current_step
        self.status_lbl.setText(f"{label}")
        
        # Apply Status Color
        color = self._get_status_color(self.current_step, state_def)
        self.status_lbl.setFixedHeight(28)
        self.status_lbl.setStyleSheet(f"""
            font-weight: bold; 
            font-size: 13px; 
            color: white; 
            background: {color}; 
            padding: 0px 15px; 
            border-radius: 14px;
            border: 1px solid {color};
        """)

        if state_def:
            for trans in state_def.transitions:
                if trans.auto: continue # Skip auto-transitions in UI
                
                text = trans.action.capitalize().replace("_", " ")
                if trans.icon:
                    btn = QPushButton(f"{trans.icon} {text}")
                else:
                    btn = QPushButton(text)
                
                # Check prerequisites
                can_run = engine.can_transition(self.current_step, trans.action, self.document_data)
                
                if can_run:
                    btn.setFixedHeight(28)
                    btn.setStyleSheet(f"""
                        QPushButton {{
                            background-color: #ffffff; 
                            color: #555; 
                            border: 1px solid #ccc;
                            font-weight: 500; 
                            font-size: 14px;
                            padding: 0px 15px;
                            border-radius: 4px;
                        }}
                        QPushButton:hover {{
                            background-color: #f8f9fa;
                            border-color: #bbb;
                        }}
                    """)
                    btn.setEnabled(True)
                else:
                    btn.setEnabled(False)
                    btn.setFixedHeight(28)
                    btn.setStyleSheet("""
                        QPushButton {
                            background-color: #f8f9fa; 
                            color: #aaa; 
                            border: 1px solid #eee;
                            font-size: 14px;
                            padding: 0px 15px;
                            border-radius: 4px;
                        }
                    """)
                    # Tooltip for why it's disabled
                    missing = [f for f in trans.required_fields if f not in self.document_data or self.document_data[f] is None]
                    if missing:
                        btn.setToolTip(self.tr("Missing fields: %s") % ", ".join(missing))
                
                btn.clicked.connect(lambda checked, a=trans.action, t=trans.target: self.transition_triggered.emit(a, t, False))
                self.buttons_layout.addWidget(btn)
        
        if state_def and state_def.final:
            self.status_lbl.setText(f"✓ {label}")
            # Final states are typically green-ish
            self.status_lbl.setFixedHeight(28)
            self.status_lbl.setStyleSheet("font-weight: bold; color: white; background: #2e7d32; padding: 0px 15px; border-radius: 14px;")
            
    def _get_status_color(self, step: str, state_def: Optional[WorkflowState]) -> str:
        """Returns a harmonized color for the status badge."""
        if state_def and state_def.final:
            return "#2e7d32" # Emerald
        
        # Semantic mapping
        step_lower = step.lower()
        if "new" in step_lower: return "#1565c0" # Blue
        if "pending" in step_lower or "wait" in step_lower: return "#f57c00" # Orange
        if "urgent" in step_lower or "error" in step_lower: return "#c62828" # Red
        if "review" in step_lower or "check" in step_lower: return "#7b1fa2" # Purple
        
        return "#607d8b" # Blue Grey default

    def _show_assignment_menu(self):
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        
        rules = self.registry.list_rules()
        
        none_action = menu.addAction(self.tr("None"))
        none_action.triggered.connect(lambda: self.rule_changed.emit(""))
        menu.addSeparator()
        
        for rule in rules:
            # Use Name if available, otherwise ID. Don't show both.
            label = rule.name or rule.id
            action = menu.addAction(label)
            action.triggered.connect(lambda checked, rid=rule.id: self.rule_changed.emit(rid))
            
        menu.exec(self.btn_change.mapToGlobal(self.btn_change.rect().bottomLeft()))

