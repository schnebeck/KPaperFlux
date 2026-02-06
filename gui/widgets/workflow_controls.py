
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel, QVBoxLayout
from PyQt6.QtCore import pyqtSignal, Qt
from core.workflow import WorkflowRegistry, WorkflowEngine
from typing import Dict, Any, Optional

class WorkflowControlsWidget(QWidget):
    """Dynamic UI component for document workflow transitions."""
    transition_triggered = pyqtSignal(str, str) # action, target_state
    playbook_changed = pyqtSignal(str) # new playbook_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.registry = WorkflowRegistry()
        self.playbook_id = None
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
        self.btn_change.setToolTip("Change/Assign Workflow Agent")
        self.btn_change.setFixedWidth(30)
        self.btn_change.setStyleSheet("background: #f5f5f5; border: 1px solid #ccc;")
        self.btn_change.clicked.connect(self._show_assignment_menu)
        self.layout.addWidget(self.btn_change)

        self.layout.addStretch()

    def update_workflow(self, playbook_id: Optional[str], current_step: str, document_data: Dict[str, Any]):
        """Refreshes the control buttons based on current state and data."""
        self.playbook_id = playbook_id
        self.current_step = current_step
        self.document_data = document_data
        
        # Clear existing buttons
        for i in reversed(range(self.buttons_layout.count())): 
            self.buttons_layout.itemAt(i).widget().setParent(None)
            
        if not self.playbook_id:
            self.status_lbl.setText("No Agent")
            return

        playbook = self.registry.get_playbook(self.playbook_id)
        if not playbook:
            self.status_lbl.setText(f"Agent '{self.playbook_id}' missing")
            return

        engine = WorkflowEngine(playbook)
        state_def = playbook.states.get(self.current_step)
        
        label = state_def.label if state_def else self.current_step
        self.status_lbl.setText(f"Step: {label}")

        if state_def:
            for trans in state_def.transitions:
                btn = QPushButton(trans.action.capitalize().replace("_", " "))
                
                # Check prerequisites
                can_run = engine.can_transition(self.current_step, trans.action, self.document_data)
                
                if can_run:
                    btn.setStyleSheet("background-color: #2e7d32; color: white; font-weight: bold; padding: 4px 10px;")
                    btn.setEnabled(True)
                else:
                    btn.setEnabled(False)
                    # Tooltip for why it's disabled
                    missing = [f for f in trans.required_fields if f not in self.document_data or self.document_data[f] is None]
                    if missing:
                        btn.setToolTip(f"Missing fields: {', '.join(missing)}")
                
                btn.clicked.connect(lambda checked, a=trans.action, t=trans.target: self.transition_triggered.emit(a, t))
                self.buttons_layout.addWidget(btn)
        
        if state_def and state_def.final:
            self.status_lbl.setText(f"✓ {label}")
            self.status_lbl.setStyleSheet("font-weight: bold; color: #2e7d32;")
        else:
             self.status_lbl.setStyleSheet("font-weight: bold; color: #1976d2;")

    def _show_assignment_menu(self):
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        
        playbooks = self.registry.list_playbooks()
        
        none_action = menu.addAction("None")
        none_action.triggered.connect(lambda: self.playbook_changed.emit(""))
        menu.addSeparator()
        
        for pb in playbooks:
            # Use Name if available, otherwise ID. Don't show both.
            label = pb.name or pb.id
            action = menu.addAction(label)
            action.triggered.connect(lambda checked, pid=pb.id: self.playbook_changed.emit(pid))
            
        menu.exec(self.btn_change.mapToGlobal(self.btn_change.rect().bottomLeft()))

